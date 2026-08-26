from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import (
    Appointment,
    AppointmentReservation,
    AuditLog,
    BehaviorEvent,
    ConversationSession,
    Engineer,
    EngineerShift,
    Handoff,
    Invocation,
    InvocationEvent,
    KnowledgeDocument,
    Memory,
    Message,
    Trace,
    TraceSpan,
    UserPreference,
    new_id,
    utcnow,
)


def digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def estimate_tokens(value: str) -> int:
    return max(1, math.ceil(len(value) / 3.2))


class SessionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, user_id: str) -> ConversationSession:
        item = ConversationSession(user_id=user_id)
        self.db.add(item)
        self.db.flush()
        return item

    def get(self, session_id: str) -> Optional[ConversationSession]:
        return self.db.get(ConversationSession, session_id)

    def require(self, session_id: str) -> ConversationSession:
        item = self.get(session_id)
        if item is None:
            raise LookupError("session_not_found")
        return item

    def add_message(self, session_id: str, role: str, content: str) -> Message:
        conversation = self.require(session_id)
        tokens = estimate_tokens(content)
        message = Message(
            session_id=session_id,
            role=role,
            content=content,
            content_digest=digest_text(content),
            token_count=tokens,
        )
        self.db.add(message)
        conversation.message_count += 1
        conversation.context_tokens += tokens
        conversation.updated_at = utcnow()
        self.db.flush()
        return message

    def list_messages(self, session_id: str, limit: int = 100, newest_first: bool = False) -> List[Message]:
        query = self.db.query(Message).filter(Message.session_id == session_id)
        query = query.order_by(Message.created_at.desc() if newest_first else Message.created_at.asc())
        return list(query.limit(limit).all())

    def close(self, session_id: str) -> ConversationSession:
        item = self.require(session_id)
        if item.status != "closed":
            item.status = "closed"
            item.closed_at = utcnow()
            item.updated_at = utcnow()
        self.db.flush()
        return item


class InvocationRepository:
    TERMINAL = {"completed", "failed", "aborted"}

    def __init__(self, db: Session):
        self.db = db

    def create_trace(self, session_id: str, input_tokens: int = 0) -> Trace:
        trace = Trace(session_id=session_id, input_tokens=input_tokens)
        self.db.add(trace)
        self.db.flush()
        return trace

    def create(
        self,
        session_id: str,
        trace_id: str,
        agent_name: str,
        input_text: str,
        parent_invocation_id: Optional[str] = None,
        source_handoff_id: Optional[str] = None,
    ) -> Invocation:
        item = Invocation(
            session_id=session_id,
            trace_id=trace_id,
            agent_name=agent_name,
            input_digest=digest_text(input_text),
            input_tokens=estimate_tokens(input_text),
            parent_invocation_id=parent_invocation_id,
            source_handoff_id=source_handoff_id,
        )
        self.db.add(item)
        self.db.flush()
        self.append_event(item.id, "invocation.started", {"agent": agent_name})
        return item

    def append_event(self, invocation_id: str, event_type: str, payload: Dict[str, Any]) -> InvocationEvent:
        current = (
            self.db.query(func.max(InvocationEvent.sequence))
            .filter(InvocationEvent.invocation_id == invocation_id)
            .scalar()
        )
        event = InvocationEvent(
            invocation_id=invocation_id,
            sequence=int(current or 0) + 1,
            event_type=event_type,
            payload=payload,
        )
        self.db.add(event)
        self.db.flush()
        return event

    def transition(self, invocation_id: str, phase: str, evidence: Dict[str, Any]) -> Invocation:
        item = self.db.get(Invocation, invocation_id)
        if item is None:
            raise LookupError("invocation_not_found")
        if item.status in self.TERMINAL:
            raise ValueError("terminal_invocation_cannot_transition")
        item.phase = phase
        self.append_event(invocation_id, "workflow.phase", {"phase": phase, "evidence": evidence})
        self.db.flush()
        return item

    def terminal(
        self,
        invocation_id: str,
        status: str,
        output_tokens: int = 0,
        error_code: Optional[str] = None,
    ) -> Invocation:
        if status not in self.TERMINAL:
            raise ValueError("invalid_invocation_terminal_status")
        item = self.db.get(Invocation, invocation_id)
        if item is None:
            raise LookupError("invocation_not_found")
        if item.status in self.TERMINAL:
            return item
        item.status = status
        item.output_tokens = output_tokens
        item.error_code = error_code
        item.ended_at = utcnow()
        self.append_event(
            invocation_id,
            "invocation.ended",
            {"status": status, "error_code": error_code, "output_tokens": output_tokens},
        )
        self.db.flush()
        return item

    def terminal_trace(
        self,
        trace_id: str,
        status: str,
        started_at: datetime,
        output_tokens: int = 0,
        agent_steps: int = 0,
        error_code: Optional[str] = None,
        incomplete: bool = False,
    ) -> Trace:
        trace = self.db.get(Trace, trace_id)
        if trace is None:
            raise LookupError("trace_not_found")
        if trace.status != "active":
            return trace
        ended = utcnow()
        trace.status = status
        trace.ended_at = ended
        trace.duration_ms = max(0.0, (ended - started_at).total_seconds() * 1000.0)
        trace.output_tokens = output_tokens
        trace.agent_steps = agent_steps
        trace.error_code = error_code
        trace.incomplete = incomplete
        self.db.flush()
        return trace

    def add_span(
        self,
        trace_id: str,
        invocation_id: Optional[str],
        name: str,
        status: str,
        duration_ms: float,
        attributes: Dict[str, Any],
    ) -> TraceSpan:
        span = TraceSpan(
            trace_id=trace_id,
            invocation_id=invocation_id,
            name=name,
            status=status,
            duration_ms=duration_ms,
            attributes=attributes,
        )
        self.db.add(span)
        self.db.flush()
        return span


class HandoffRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_or_get(
        self,
        source_invocation_id: str,
        from_agent: str,
        to_agent: str,
        intent: str,
        dedupe_key: str,
        packet: Dict[str, Any],
    ) -> Tuple[Handoff, bool]:
        existing = self.db.query(Handoff).filter(Handoff.dedupe_key == dedupe_key).one_or_none()
        if existing is not None:
            return existing, False
        item = Handoff(
            source_invocation_id=source_invocation_id,
            from_agent=from_agent,
            to_agent=to_agent,
            intent=intent,
            dedupe_key=dedupe_key,
            packet=packet,
        )
        self.db.add(item)
        self.db.flush()
        return item, True

    def consume_once_and_start(
        self,
        handoff_id: str,
        session_id: str,
        trace_id: str,
        input_text: str,
    ) -> Tuple[Handoff, Optional[Invocation], bool]:
        now = utcnow()
        changed = (
            self.db.query(Handoff)
            .filter(Handoff.id == handoff_id, Handoff.status == "pending")
            .update(
                {
                    Handoff.status: "started",
                    Handoff.enqueued_at: now,
                    Handoff.started_at: now,
                },
                synchronize_session=False,
            )
        )
        handoff = self.db.get(Handoff, handoff_id)
        if handoff is None:
            raise LookupError("handoff_not_found")
        if changed != 1:
            invocation = (
                self.db.get(Invocation, handoff.target_invocation_id)
                if handoff.target_invocation_id
                else None
            )
            return handoff, invocation, False
        invocation = InvocationRepository(self.db).create(
            session_id=session_id,
            trace_id=trace_id,
            agent_name=handoff.to_agent,
            input_text=input_text,
            parent_invocation_id=handoff.source_invocation_id,
            source_handoff_id=handoff.id,
        )
        handoff = self.db.get(Handoff, handoff_id)
        handoff.target_invocation_id = invocation.id
        self.db.flush()
        return handoff, invocation, True

    def complete(self, handoff_id: str, success: bool, failure_code: Optional[str] = None) -> Handoff:
        item = self.db.get(Handoff, handoff_id)
        if item is None:
            raise LookupError("handoff_not_found")
        if item.status in {"completed", "failed"}:
            return item
        item.status = "completed" if success else "failed"
        item.failure_code = failure_code
        item.completed_at = utcnow()
        self.db.flush()
        return item


class AppointmentRepository:
    SLOT_MINUTES = 30

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def slot_starts(start_time: datetime, end_time: datetime) -> Iterable[datetime]:
        cursor = start_time.replace(second=0, microsecond=0)
        minute = 0 if cursor.minute < 30 else 30
        cursor = cursor.replace(minute=minute)
        while cursor < end_time:
            yield cursor
            cursor += timedelta(minutes=AppointmentRepository.SLOT_MINUTES)

    def find_by_idempotency_key(self, key: str) -> Optional[Appointment]:
        return self.db.query(Appointment).filter(Appointment.idempotency_key == key).one_or_none()

    def list_available_engineers(
        self,
        start_time: datetime,
        end_time: datetime,
        required_skills: Sequence[str],
        region: Optional[str] = None,
    ) -> List[Engineer]:
        candidates = self.db.query(Engineer).filter(Engineer.active.is_(True)).all()
        busy_ids = {
            row[0]
            for row in self.db.query(AppointmentReservation.engineer_id)
            .filter(
                AppointmentReservation.slot_start.in_(list(self.slot_starts(start_time, end_time)))
            )
            .all()
        }
        required = {value.lower() for value in required_skills}
        result = []
        for engineer in candidates:
            skills = {str(value).lower() for value in (engineer.skills or [])}
            regions = {str(value).lower() for value in (engineer.service_regions or [])}
            if engineer.id in busy_ids:
                continue
            if required and not required.intersection(skills):
                continue
            if region and regions and region.lower() not in regions:
                continue
            has_shift = (
                self.db.query(EngineerShift.id)
                .filter(
                    EngineerShift.engineer_id == engineer.id,
                    EngineerShift.status == "available",
                    EngineerShift.start_time <= start_time,
                    EngineerShift.end_time >= end_time,
                )
                .first()
                is not None
            )
            if has_shift:
                result.append(engineer)
        return result

    def create_reserved(
        self,
        user_id: str,
        session_id: str,
        engineer_id: str,
        slots: Dict[str, Any],
        start_time: datetime,
        end_time: datetime,
        idempotency_key: str,
    ) -> Tuple[Appointment, bool]:
        existing = self.find_by_idempotency_key(idempotency_key)
        if existing is not None:
            return existing, False
        appointment = Appointment(
            user_id=user_id,
            session_id=session_id,
            engineer_id=engineer_id,
            service_type=slots["service_type"],
            issue_category=slots["issue_category"],
            location=slots.get("location"),
            contact=slots.get("contact"),
            start_time=start_time,
            end_time=end_time,
            slots=slots,
            idempotency_key=idempotency_key,
        )
        self.db.add(appointment)
        self.db.flush()
        for slot_start in self.slot_starts(start_time, end_time):
            self.db.add(
                AppointmentReservation(
                    appointment_id=appointment.id,
                    engineer_id=engineer_id,
                    slot_start=slot_start,
                )
            )
        try:
            self.db.flush()
        except IntegrityError as exc:
            raise ValueError("appointment_time_conflict") from exc
        return appointment, True

    def cancel(self, appointment_id: str, expected_version: int) -> Appointment:
        changed = (
            self.db.query(Appointment)
            .filter(
                Appointment.id == appointment_id,
                Appointment.status == "confirmed",
                Appointment.version == expected_version,
            )
            .update(
                {Appointment.status: "cancelled", Appointment.version: expected_version + 1},
                synchronize_session=False,
            )
        )
        if changed != 1:
            raise ValueError("appointment_version_or_state_conflict")
        self.db.query(AppointmentReservation).filter(
            AppointmentReservation.appointment_id == appointment_id
        ).delete(synchronize_session=False)
        item = self.db.get(Appointment, appointment_id)
        self.db.refresh(item)
        return item


class BehaviorRepository:
    def __init__(self, db: Session):
        self.db = db

    def record(
        self,
        user_id: str,
        event_type: str,
        payload: Dict[str, Any],
        idempotency_key: str,
        session_id: Optional[str] = None,
    ) -> Tuple[BehaviorEvent, bool]:
        existing = (
            self.db.query(BehaviorEvent)
            .filter(BehaviorEvent.idempotency_key == idempotency_key)
            .one_or_none()
        )
        if existing is not None:
            return existing, False
        event = BehaviorEvent(
            user_id=user_id,
            session_id=session_id,
            event_type=event_type,
            payload=payload,
            idempotency_key=idempotency_key,
        )
        self.db.add(event)
        self.db.flush()
        return event, True


class AuditRepository:
    SECRET_KEYS = {"authorization", "token", "api_key", "contact", "phone", "email"}

    def __init__(self, db: Session):
        self.db = db

    @classmethod
    def redact(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        clean: Dict[str, Any] = {}
        for key, value in payload.items():
            if key.lower() in cls.SECRET_KEYS:
                clean[key] = "[REDACTED]"
            elif isinstance(value, dict):
                clean[key] = cls.redact(value)
            else:
                clean[key] = value
        return clean

    def record(
        self,
        actor_id: str,
        actor_role: str,
        action: str,
        resource_type: str,
        decision: str,
        risk_level: str,
        payload: Dict[str, Any],
        resource_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> AuditLog:
        item = AuditLog(
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            decision=decision,
            risk_level=risk_level,
            payload=self.redact(payload),
            trace_id=trace_id,
        )
        self.db.add(item)
        self.db.flush()
        return item


class KnowledgeRepository:
    def __init__(self, db: Session):
        self.db = db

    def search_local(self, query: str, collection: str, top_k: int) -> List[Tuple[KnowledgeDocument, float]]:
        docs = (
            self.db.query(KnowledgeDocument)
            .filter(KnowledgeDocument.collection == collection, KnowledgeDocument.active.is_(True))
            .all()
        )
        raw_terms = re.findall(r"[A-Za-z0-9_\-]+|[\u4e00-\u9fff]+", query.lower())
        terms = set(raw_terms)
        for term in raw_terms:
            if re.fullmatch(r"[\u4e00-\u9fff]+", term) and len(term) > 2:
                terms.update(term[index : index + 2] for index in range(len(term) - 1))
        scored: List[Tuple[KnowledgeDocument, float]] = []
        for doc in docs:
            haystack = f"{doc.title} {doc.content} {' '.join(doc.keywords or [])}".lower()
            overlap = sum(1 for term in terms if term in haystack)
            if overlap or (query and query.lower() in haystack):
                scored.append((doc, overlap / max(1, len(terms))))
        scored.sort(key=lambda pair: (-pair[1], pair[0].id))
        return scored[:top_k]
