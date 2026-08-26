from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from sqlalchemy.orm import sessionmaker

from agents.contracts import Actor, WorkflowPhase
from agents.specialists import SpecialistDispatcher, SpecialistOutcome
from agents.supervisor import LoopGuard, SupervisorPlanner
from config.settings import Settings
from db.models import ConversationSession, Handoff, Invocation, Trace, utcnow
from db.repositories import (
    BehaviorRepository,
    HandoffRepository,
    InvocationRepository,
    SessionRepository,
    digest_text,
    estimate_tokens,
)
from services.context import ContextWindowService
from services.security import ToolPolicy
from services.workflow import FivePhaseWorkflow


@dataclass
class ChatCommand:
    user_id: str
    message: str
    session_id: Optional[str] = None
    idempotency_key: Optional[str] = None


class AgentOrchestrator:
    def __init__(self, session_factory: sessionmaker, settings: Settings):
        self.session_factory = session_factory
        self.settings = settings
        self.planner = SupervisorPlanner()
        self.tool_policy = ToolPolicy(settings.allowed_tools)

    async def stream(self, command: ChatCommand, actor: Actor) -> AsyncGenerator[Dict[str, Any], None]:
        db = self.session_factory()
        trace_id: Optional[str] = None
        invocation_id: Optional[str] = None
        trace_started: Optional[datetime] = None
        steps = 0
        sequence = 0

        def event(event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
            nonlocal sequence
            sequence += 1
            return {
                "id": sequence,
                "event": event_type,
                "data": {
                    **data,
                    "trace_id": trace_id,
                    "invocation_id": invocation_id,
                    "session_id": command.session_id,
                    "timestamp": utcnow().isoformat() + "Z",
                },
            }

        try:
            sessions = SessionRepository(db)
            conversation = sessions.get(command.session_id) if command.session_id else None
            if conversation is None:
                conversation = sessions.create(command.user_id)
                command.session_id = conversation.id
            elif conversation.user_id != command.user_id:
                raise PermissionError("session_user_mismatch")
            elif conversation.status != "active":
                raise ValueError("session_not_active")
            sessions.add_message(conversation.id, "user", command.message)
            context = ContextWindowService(db, self.settings).build(conversation.id)
            invocations = InvocationRepository(db)
            trace = invocations.create_trace(conversation.id, estimate_tokens(command.message))
            trace_id = trace.id
            trace_started = trace.started_at
            root = invocations.create(conversation.id, trace.id, "supervisor_agent", command.message)
            invocation_id = root.id
            db.commit()
            yield event("run.started", {"agent": "supervisor_agent", "context_summarized": context.summarized})

            decision = self.planner.decide(command.message)
            workflow = FivePhaseWorkflow(InvocationRepository(db))
            workflow.transition(
                root.id,
                WorkflowPhase.DISCUSS,
                {"route": decision.target_agent, "goal": decision.intent.value},
            )
            db.commit()
            yield event("progress", {"phase": "discuss", "route": decision.target_agent, "reason_code": decision.reason_code})

            packet = {
                "intent": decision.intent.value,
                "what": "handle enterprise after-sales turn",
                "why": decision.reason_code,
                "next_action": "execute whitelisted specialist tools",
                "evidence": [f"message_digest:{digest_text(command.message)}"],
                "context": {"recent_messages": len(context.messages), "has_summary": bool(context.summary)},
            }
            dedupe_key = hashlib.sha256(f"{root.id}:{decision.target_agent}:{decision.intent.value}".encode("utf-8")).hexdigest()
            handoffs = HandoffRepository(db)
            handoff, _created = handoffs.create_or_get(
                root.id, "supervisor_agent", decision.target_agent, decision.intent.value, dedupe_key, packet
            )
            handoff, child, consumed = handoffs.consume_once_and_start(
                handoff.id, conversation.id, trace.id, command.message
            )
            if not consumed or child is None:
                raise RuntimeError("handoff_duplicate_consumption")
            db.commit()
            yield event("handoff", {"handoff_id": handoff.id, "to": decision.target_agent, "status": "started"})

            guard = LoopGuard(self.settings.max_agent_steps)
            allowed_tools: List[str] = []
            for tool_name in decision.tools:
                self.tool_policy.require(tool_name)
                guard.observe(tool_name, {"session_id": conversation.id, "message_digest": digest_text(command.message)})
                allowed_tools.append(tool_name)
                steps += 1
                InvocationRepository(db).append_event(root.id, "tool.started", {"tool": tool_name})
                db.commit()
                yield event("tool.started", {"tool": tool_name, "step": steps})
            workflow = FivePhaseWorkflow(InvocationRepository(db))
            workflow.transition(root.id, WorkflowPhase.IMPLEMENT, {"tool_calls": allowed_tools})
            db.commit()
            dispatch_started = time.perf_counter()
            outcome = await SpecialistDispatcher(db, self.settings).dispatch(
                decision, actor, command.user_id, conversation, command.message, command.idempotency_key, trace.id
            )
            dispatch_ms = (time.perf_counter() - dispatch_started) * 1000.0
            InvocationRepository(db).add_span(
                trace.id,
                child.id,
                "specialist.dispatch",
                "completed",
                dispatch_ms,
                {"agent": decision.target_agent, "intent": decision.intent.value},
            )
            actual_tools = {str(result.get("tool")) for result in outcome.tool_results}
            for result in outcome.tool_results:
                InvocationRepository(db).append_event(root.id, "tool.finished", result)
                yield event("tool.finished", result)
            for tool_name in allowed_tools:
                if tool_name not in actual_tools:
                    skipped = {"tool": tool_name, "status": "skipped_by_state"}
                    InvocationRepository(db).append_event(root.id, "tool.finished", skipped)
                    yield event("tool.finished", skipped)
            InvocationRepository(db).terminal(child.id, "completed", estimate_tokens(outcome.text))
            HandoffRepository(db).complete(handoff.id, True)
            trace.candidate_count = outcome.candidate_count
            trace.rank_changes = outcome.rank_changes
            db.commit()

            validation = "non_empty_response" if outcome.text.strip() else "empty_response"
            workflow = FivePhaseWorkflow(InvocationRepository(db))
            workflow.transition(
                root.id,
                WorkflowPhase.REVIEW,
                {"validation": validation, "safety": outcome.safety},
            )
            db.commit()
            yield event("progress", {"phase": "review", "validation": validation, "safety": outcome.safety})

            workflow = FivePhaseWorkflow(InvocationRepository(db))
            workflow.transition(
                root.id,
                WorkflowPhase.DELIVER,
                {"response_digest": digest_text(outcome.text)},
            )
            InvocationRepository(db).append_event(root.id, "response.ready", {"characters": len(outcome.text)})
            db.commit()
            yield event("progress", {"phase": "deliver"})
            for offset in range(0, len(outcome.text), 48):
                yield event("text.delta", {"text": outcome.text[offset : offset + 48]})
                await asyncio.sleep(0)
            for citation in outcome.citations:
                yield event("citation", asdict(citation))

            sessions = SessionRepository(db)
            sessions.add_message(conversation.id, "assistant", outcome.text)
            conversation.completed_turns += 1
            BehaviorRepository(db).record(
                command.user_id,
                "consultation.completed",
                {"intent": decision.intent.value, "query_digest": digest_text(command.message)},
                f"turn:{root.id}",
                conversation.id,
            )
            workflow = FivePhaseWorkflow(InvocationRepository(db))
            workflow.transition(
                root.id,
                WorkflowPhase.DONE,
                {"terminal_status": "completed", "trace_id": trace.id},
            )
            output_tokens = estimate_tokens(outcome.text)
            InvocationRepository(db).terminal(root.id, "completed", output_tokens)
            InvocationRepository(db).terminal_trace(
                trace.id, "completed", trace_started, output_tokens, steps
            )
            db.commit()
            yield event(
                "run.completed",
                {
                    "status": "completed",
                    "phase": "done",
                    "steps": steps,
                    "resource_id": outcome.resource_id,
                    "appointment_state": outcome.state,
                },
            )
        except asyncio.CancelledError:
            db.rollback()
            self._close_failed(trace_id, invocation_id, trace_started, "aborted", "client_disconnected", steps)
            raise
        except Exception as exc:
            db.rollback()
            error_code = str(exc)[:120] or exc.__class__.__name__
            self._close_failed(trace_id, invocation_id, trace_started, "failed", error_code, steps)
            yield event("run.failed", {"status": "failed", "error_code": error_code})
        finally:
            db.close()

    def _close_failed(
        self,
        trace_id: Optional[str],
        invocation_id: Optional[str],
        trace_started: Optional[datetime],
        status: str,
        error_code: str,
        steps: int,
    ) -> None:
        if not trace_id or not invocation_id or trace_started is None:
            return
        db = self.session_factory()
        try:
            repository = InvocationRepository(db)
            repository.terminal(invocation_id, status, error_code=error_code)
            repository.terminal_trace(trace_id, status, trace_started, agent_steps=steps, error_code=error_code, incomplete=True)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    async def run(self, command: ChatCommand, actor: Actor) -> Dict[str, Any]:
        text_parts: List[str] = []
        final: Dict[str, Any] = {}
        events: List[Dict[str, Any]] = []
        async for item in self.stream(command, actor):
            events.append(item)
            if item["event"] == "text.delta":
                text_parts.append(item["data"]["text"])
            if item["event"] in {"run.completed", "run.failed"}:
                final = item["data"]
        return {"message": "".join(text_parts), "result": final, "events": events}
