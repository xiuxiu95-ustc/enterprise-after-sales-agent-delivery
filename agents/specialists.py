from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from agents.contracts import Actor, AgentDecision, AgentIntent
from config.settings import Settings
from db.models import ConversationSession, UserPreference
from db.repositories import BehaviorRepository
from services.appointment import AppointmentService, AppointmentStateMachine
from services.memory import MemoryService
from services.rag import Citation, RagGateway
from services.slot_extraction import SlotExtractorAdapter


@dataclass
class SpecialistOutcome:
    text: str
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    citations: List[Citation] = field(default_factory=list)
    candidate_count: int = 0
    rank_changes: List[Dict[str, Any]] = field(default_factory=list)
    safety: str = "passed"
    state: Optional[str] = None
    resource_id: Optional[str] = None


class ConsultationAgent:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    async def handle(self, user_id: str, query: str) -> SpecialistOutcome:
        memories = MemoryService(self.db).recall(user_id, query, top_k=5)
        rag = await RagGateway(self.db, self.settings).query(query, top_k=5)
        if not rag.answer_context.strip():
            text = "当前知识库没有找到足够可信的依据，我已停止生成结论。请补充产品型号、故障码或联系人工售后。"
        else:
            context = " ".join(rag.answer_context.split())[:1200]
            text = f"根据企业知识库检索结果：{context}"
            if rag.degraded:
                text += "\n\n当前使用本地开发检索降级链路；生产环境请启用 RAG MCP。"
        return SpecialistOutcome(
            text=text,
            tool_results=[
                {"tool": "memory_recall", "count": len(memories)},
                {"tool": "query_knowledge_hub", "source": rag.source, "count": rag.candidate_count},
            ],
            citations=rag.citations,
            candidate_count=rag.candidate_count,
            rank_changes=rag.rank_changes,
            safety="grounded" if rag.answer_context else "abstained",
        )


class AppointmentAgent:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings
        self.extractor = SlotExtractorAdapter(settings)

    async def handle(
        self,
        actor: Actor,
        user_id: str,
        session: ConversationSession,
        user_input: str,
        idempotency_key: Optional[str],
        trace_id: str,
    ) -> SpecialistOutcome:
        memories = MemoryService(self.db).recall(user_id, user_input, top_k=5)
        slots = self.extractor.extract(user_input, dict(session.slot_state or {}))
        state = AppointmentStateMachine.draft_state(slots)
        state_payload = asdict(slots)
        state_payload["state"] = state
        session.slot_state = state_payload
        self.db.flush()
        tools = [
            {"tool": "memory_recall", "count": len(memories)},
            {"tool": "extract_appointment_slots", "source": slots.source, "missing": slots.missing_info},
        ]
        if slots.missing_info:
            prompts = {
                "service_type": "需要上门维修、远程支持、安装、保养还是巡检？",
                "issue_category": "请描述产品类型、故障现象或故障码。",
                "start_time": "希望安排哪一天、几点？",
                "duration_minutes": "预计需要多长时间（以 30 分钟为单位）？",
                "location": "请提供服务区域或上门地址。",
            }
            questions = [prompts[item] for item in slots.missing_info]
            return SpecialistOutcome("还需要补充以下信息：" + " ".join(questions), tools, state=state)

        service = AppointmentService(self.db)
        matches = service.match_engineers(slots)
        tools.append({"tool": "find_available_engineers", "count": len(matches)})
        if not matches:
            return SpecialistOutcome(
                "当前时间段没有满足技能、排班和区域约束的工程师。请更换时间或放宽工程师偏好。",
                tools,
                state="awaiting_confirmation",
            )
        selected = matches[0]
        session.slot_state = {**state_payload, "selected_engineer_id": selected.engineer_id, "selected_engineer_name": selected.engineer_name}
        if not slots.confirmation:
            alternative = (
                f"您指定的 {selected.substitution_for} 当前不可用；按专长相似度推荐 "
                if selected.substitution_for
                else "可安排 "
            )
            text = (
                f"{alternative}{selected.engineer_name}，技能：{', '.join(selected.skills)}，"
                f"时间 {slots.start_time}，预计 {slots.duration_minutes} 分钟。请明确回复“确认预约”。"
            )
            return SpecialistOutcome(text, tools, state="awaiting_confirmation")

        confirmed_actor = Actor(actor.actor_id, actor.role, confirmed=True)
        appointment, created = service.create(
            confirmed_actor,
            user_id,
            session.id,
            slots,
            selected.engineer_id,
            idempotency_key,
            trace_id,
        )
        session.slot_state = {**dict(session.slot_state or {}), "state": "confirmed", "appointment_id": appointment.id}
        tools.append({"tool": "create_appointment", "created": created, "appointment_id": appointment.id})
        BehaviorRepository(self.db).record(
            user_id,
            "appointment.confirmed",
            {
                "appointment_id": appointment.id,
                "service_type": appointment.service_type,
                "issue_category": appointment.issue_category,
                "engineer_name": selected.engineer_name,
            },
            f"appointment-event:{appointment.id}",
            session.id,
        )
        text = (
            f"预约已确认：工单 {appointment.id}，工程师 {selected.engineer_name}，"
            f"服务时间 {slots.start_time}，预计 {slots.duration_minutes} 分钟。"
        )
        if not created:
            text += " 该请求命中幂等记录，未重复写入。"
        return SpecialistOutcome(text, tools, state="confirmed", resource_id=appointment.id)


class BehaviorAgent:
    def __init__(self, db: Session):
        self.db = db

    async def handle(self, user_id: str, session_id: str, query: str) -> SpecialistOutcome:
        memories = MemoryService(self.db).recall(user_id, query, top_k=5)
        preferences = (
            self.db.query(UserPreference)
            .filter(UserPreference.user_id == user_id)
            .order_by(UserPreference.confidence.desc())
            .limit(10)
            .all()
        )
        event_key = "behavior-query:" + hashlib.sha256(f"{session_id}:{query}".encode("utf-8")).hexdigest()
        BehaviorRepository(self.db).record(
            user_id, "profile.viewed", {"query_digest": hashlib.sha256(query.encode("utf-8")).hexdigest()}, event_key, session_id
        )
        preference_text = "；".join(
            f"{item.preference_key}={item.preference_value}(置信度{item.confidence:.2f})"
            for item in preferences
        ) or "暂无稳定偏好"
        return SpecialistOutcome(
            text=f"当前画像：{preference_text}。召回到 {len(memories)} 条相关长期记忆；冲突偏好已按置信度降权。",
            tool_results=[{"tool": "memory_recall", "count": len(memories)}, {"tool": "record_behavior", "recorded": True}],
        )


class SpecialistDispatcher:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    async def dispatch(
        self,
        decision: AgentDecision,
        actor: Actor,
        user_id: str,
        session: ConversationSession,
        user_input: str,
        idempotency_key: Optional[str],
        trace_id: str,
    ) -> SpecialistOutcome:
        if decision.intent in {AgentIntent.APPOINTMENT, AgentIntent.MIXED}:
            return await AppointmentAgent(self.db, self.settings).handle(
                actor, user_id, session, user_input, idempotency_key, trace_id
            )
        if decision.intent == AgentIntent.BEHAVIOR:
            return await BehaviorAgent(self.db).handle(user_id, session.id, user_input)
        if decision.intent == AgentIntent.CONSULT:
            return await ConsultationAgent(self.db, self.settings).handle(user_id, user_input)
        return SpecialistOutcome(
            "我可以处理企业售后知识咨询、故障排查、上门/远程服务预约和用户偏好分析。请补充产品、问题或预约需求。",
            safety="scope_guard",
        )
