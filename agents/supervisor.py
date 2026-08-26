from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Set

from .contracts import AgentDecision, AgentIntent


class AgentLoopError(RuntimeError):
    pass


class LoopGuard:
    def __init__(self, max_steps: int):
        self.max_steps = max_steps
        self.steps = 0
        self.signatures: Set[str] = set()

    def observe(self, tool_name: str, arguments: Dict[str, Any]) -> None:
        self.steps += 1
        if self.steps > self.max_steps:
            raise AgentLoopError("max_agent_steps_exceeded")
        canonical = json.dumps(arguments, ensure_ascii=False, sort_keys=True, default=str)
        signature = hashlib.sha256(f"{tool_name}:{canonical}".encode("utf-8")).hexdigest()
        if signature in self.signatures:
            raise AgentLoopError("repeated_tool_signature")
        self.signatures.add(signature)


class SupervisorPlanner:
    APPOINTMENT_WORDS = {"预约", "上门", "工程师", "师傅", "排期", "安装", "维修", "保养", "巡检"}
    CONSULT_WORDS = {"怎么", "如何", "政策", "保修", "价格", "费用", "说明书", "故障码", "知识", "咨询"}
    BEHAVIOR_WORDS = {"画像", "偏好", "行为分析", "我的历史", "推荐依据"}

    def decide(self, user_input: str) -> AgentDecision:
        appointment = any(word in user_input for word in self.APPOINTMENT_WORDS)
        consult = any(word in user_input for word in self.CONSULT_WORDS)
        behavior = any(word in user_input for word in self.BEHAVIOR_WORDS)
        explicit_booking = any(
            phrase in user_input
            for phrase in {"预约", "帮我安排", "我要上门", "安排工程师", "确认预约"}
        )
        if appointment and consult and not explicit_booking:
            return AgentDecision(
                intent=AgentIntent.CONSULT,
                target_agent="consultation_agent",
                tools=["memory_recall", "query_knowledge_hub"],
                reason_code="question_overrides_incidental_appointment_term",
            )
        if appointment and consult:
            return AgentDecision(
                intent=AgentIntent.MIXED,
                target_agent="appointment_agent",
                tools=["memory_recall", "query_knowledge_hub", "extract_appointment_slots", "find_available_engineers"],
                reason_code="appointment_with_consultation_context",
            )
        if appointment:
            return AgentDecision(
                intent=AgentIntent.APPOINTMENT,
                target_agent="appointment_agent",
                tools=["memory_recall", "extract_appointment_slots", "find_available_engineers", "create_appointment"],
            )
        if behavior:
            return AgentDecision(
                intent=AgentIntent.BEHAVIOR,
                target_agent="behavior_agent",
                tools=["memory_recall", "record_behavior"],
            )
        if consult or user_input.strip().endswith(("?", "？")):
            return AgentDecision(
                intent=AgentIntent.CONSULT,
                target_agent="consultation_agent",
                tools=["memory_recall", "query_knowledge_hub"],
            )
        return AgentDecision(
            intent=AgentIntent.UNSUPPORTED,
            target_agent="consultation_agent",
            tools=[],
            reason_code="unsupported_or_ambiguous",
        )
