from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id() -> str:
    return str(uuid.uuid4())


Base = declarative_base()


class ConversationSession(Base):
    __tablename__ = "conversation_sessions"
    id = Column(String(36), primary_key=True, default=new_id)
    user_id = Column(String(128), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    message_count = Column(Integer, nullable=False, default=0)
    completed_turns = Column(Integer, nullable=False, default=0)
    context_tokens = Column(Integer, nullable=False, default=0)
    summary = Column(Text, nullable=True)
    summary_generation = Column(Integer, nullable=False, default=0)
    summary_message_count = Column(Integer, nullable=False, default=0)
    slot_state = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    closed_at = Column(DateTime, nullable=True)


class Message(Base):
    __tablename__ = "messages"
    id = Column(String(36), primary_key=True, default=new_id)
    session_id = Column(String(36), ForeignKey("conversation_sessions.id"), nullable=False, index=True)
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    content_digest = Column(String(64), nullable=False)
    token_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=utcnow, index=True)


class Trace(Base):
    __tablename__ = "traces"
    id = Column(String(36), primary_key=True, default=new_id)
    session_id = Column(String(36), ForeignKey("conversation_sessions.id"), nullable=False, index=True)
    status = Column(String(24), nullable=False, default="active", index=True)
    capture_policy = Column(String(32), nullable=False, default="structural-v1")
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    candidate_count = Column(Integer, nullable=False, default=0)
    rank_changes = Column(JSON, nullable=False, default=list)
    agent_steps = Column(Integer, nullable=False, default=0)
    incomplete = Column(Boolean, nullable=False, default=False)
    error_code = Column(String(64), nullable=True)
    started_at = Column(DateTime, nullable=False, default=utcnow)
    ended_at = Column(DateTime, nullable=True)
    duration_ms = Column(Float, nullable=True)


class Invocation(Base):
    __tablename__ = "invocations"
    id = Column(String(36), primary_key=True, default=new_id)
    session_id = Column(String(36), ForeignKey("conversation_sessions.id"), nullable=False, index=True)
    trace_id = Column(String(36), ForeignKey("traces.id"), nullable=False, index=True)
    parent_invocation_id = Column(String(36), ForeignKey("invocations.id"), nullable=True)
    source_handoff_id = Column(String(36), ForeignKey("handoffs.id"), nullable=True, unique=True)
    agent_name = Column(String(64), nullable=False, index=True)
    phase = Column(String(24), nullable=False, default="discuss")
    status = Column(String(24), nullable=False, default="active", index=True)
    input_digest = Column(String(64), nullable=False)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    error_code = Column(String(64), nullable=True)
    started_at = Column(DateTime, nullable=False, default=utcnow)
    ended_at = Column(DateTime, nullable=True)


class InvocationEvent(Base):
    __tablename__ = "invocation_events"
    __table_args__ = (UniqueConstraint("invocation_id", "sequence", name="uq_invocation_event_sequence"),)
    id = Column(String(36), primary_key=True, default=new_id)
    invocation_id = Column(String(36), ForeignKey("invocations.id"), nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    event_type = Column(String(48), nullable=False, index=True)
    payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class Handoff(Base):
    __tablename__ = "handoffs"
    id = Column(String(36), primary_key=True, default=new_id)
    source_invocation_id = Column(String(36), ForeignKey("invocations.id"), nullable=False, index=True)
    target_invocation_id = Column(String(36), ForeignKey("invocations.id"), nullable=True, unique=True)
    from_agent = Column(String(64), nullable=False)
    to_agent = Column(String(64), nullable=False)
    intent = Column(String(24), nullable=False)
    dedupe_key = Column(String(128), nullable=False, unique=True)
    packet = Column(JSON, nullable=False)
    status = Column(String(24), nullable=False, default="pending", index=True)
    attempted_at = Column(DateTime, nullable=False, default=utcnow)
    accepted_at = Column(DateTime, nullable=False, default=utcnow)
    enqueued_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    failure_code = Column(String(64), nullable=True)


class Memory(Base):
    __tablename__ = "memories"
    __table_args__ = (
        UniqueConstraint("user_id", "content_hash", name="uq_memory_user_content"),
        UniqueConstraint("source_event_id", name="uq_memory_source_event"),
    )
    id = Column(String(36), primary_key=True, default=new_id)
    user_id = Column(String(128), nullable=False, index=True)
    session_id = Column(String(36), ForeignKey("conversation_sessions.id"), nullable=True)
    source_event_id = Column(String(36), ForeignKey("behavior_events.id"), nullable=True)
    memory_type = Column(String(32), nullable=False, index=True)
    content = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False)
    embedding = Column(JSON, nullable=True)
    confidence = Column(Float, nullable=False, default=0.5)
    importance = Column(Float, nullable=False, default=0.5)
    occurred_at = Column(DateTime, nullable=False, default=utcnow)
    last_accessed_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)


class UserPreference(Base):
    __tablename__ = "user_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "preference_key", "preference_value", name="uq_user_preference"),
    )
    id = Column(String(36), primary_key=True, default=new_id)
    user_id = Column(String(128), nullable=False, index=True)
    preference_key = Column(String(64), nullable=False)
    preference_value = Column(String(256), nullable=False)
    confidence = Column(Float, nullable=False, default=0.5)
    evidence_count = Column(Integer, nullable=False, default=1)
    conflict_score = Column(Float, nullable=False, default=0.0)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class BehaviorEvent(Base):
    __tablename__ = "behavior_events"
    id = Column(String(36), primary_key=True, default=new_id)
    user_id = Column(String(128), nullable=False, index=True)
    session_id = Column(String(36), ForeignKey("conversation_sessions.id"), nullable=True, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    payload = Column(JSON, nullable=False, default=dict)
    idempotency_key = Column(String(128), nullable=False, unique=True)
    occurred_at = Column(DateTime, nullable=False, default=utcnow, index=True)


class Engineer(Base):
    __tablename__ = "engineers"
    id = Column(String(36), primary_key=True, default=new_id)
    employee_code = Column(String(64), nullable=False, unique=True)
    name = Column(String(128), nullable=False)
    skills = Column(JSON, nullable=False, default=list)
    skill_embedding = Column(JSON, nullable=True)
    service_regions = Column(JSON, nullable=False, default=list)
    active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class EngineerShift(Base):
    __tablename__ = "engineer_shifts"
    id = Column(String(36), primary_key=True, default=new_id)
    engineer_id = Column(String(36), ForeignKey("engineers.id"), nullable=False, index=True)
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False, index=True)
    capacity = Column(Integer, nullable=False, default=1)
    status = Column(String(24), nullable=False, default="available")


class Appointment(Base):
    __tablename__ = "appointments"
    id = Column(String(36), primary_key=True, default=new_id)
    user_id = Column(String(128), nullable=False, index=True)
    session_id = Column(String(36), ForeignKey("conversation_sessions.id"), nullable=False, index=True)
    engineer_id = Column(String(36), ForeignKey("engineers.id"), nullable=False, index=True)
    service_type = Column(String(64), nullable=False)
    issue_category = Column(String(128), nullable=False)
    location = Column(String(256), nullable=True)
    contact = Column(String(128), nullable=True)
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False, index=True)
    status = Column(String(32), nullable=False, default="confirmed", index=True)
    slots = Column(JSON, nullable=False, default=dict)
    idempotency_key = Column(String(128), nullable=False, unique=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class AppointmentReservation(Base):
    __tablename__ = "appointment_reservations"
    __table_args__ = (
        UniqueConstraint("engineer_id", "slot_start", name="uq_engineer_slot"),
    )
    id = Column(String(36), primary_key=True, default=new_id)
    appointment_id = Column(String(36), ForeignKey("appointments.id"), nullable=False, index=True)
    engineer_id = Column(String(36), ForeignKey("engineers.id"), nullable=False, index=True)
    slot_start = Column(DateTime, nullable=False, index=True)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    id = Column(String(36), primary_key=True, default=new_id)
    collection = Column(String(128), nullable=False, default="enterprise_after_sales", index=True)
    title = Column(String(256), nullable=False)
    content = Column(Text, nullable=False)
    source_uri = Column(String(512), nullable=False)
    keywords = Column(JSON, nullable=False, default=list)
    active = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(String(36), primary_key=True, default=new_id)
    actor_id = Column(String(128), nullable=False)
    actor_role = Column(String(32), nullable=False)
    action = Column(String(128), nullable=False, index=True)
    resource_type = Column(String(64), nullable=False)
    resource_id = Column(String(128), nullable=True)
    decision = Column(String(24), nullable=False)
    risk_level = Column(String(16), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    trace_id = Column(String(36), ForeignKey("traces.id"), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=utcnow, index=True)


class TraceSpan(Base):
    __tablename__ = "trace_spans"
    id = Column(String(36), primary_key=True, default=new_id)
    trace_id = Column(String(36), ForeignKey("traces.id"), nullable=False, index=True)
    invocation_id = Column(String(36), ForeignKey("invocations.id"), nullable=True)
    name = Column(String(64), nullable=False)
    status = Column(String(24), nullable=False)
    duration_ms = Column(Float, nullable=False)
    attributes = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class AutoDreamJob(Base):
    __tablename__ = "autodream_jobs"
    user_id = Column(String(128), primary_key=True)
    status = Column(String(24), nullable=False, default="idle")
    lock_token = Column(String(64), nullable=True)
    locked_until = Column(DateTime, nullable=True)
    checkpoint_event_id = Column(String(36), nullable=True)
    checkpoint_closed_at = Column(DateTime, nullable=True)
    last_run_at = Column(DateTime, nullable=True)
    last_error = Column(String(512), nullable=True)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class EvaluationFailure(Base):
    __tablename__ = "evaluation_failures"
    id = Column(String(36), primary_key=True, default=new_id)
    case_id = Column(String(128), nullable=False, index=True)
    layer = Column(String(32), nullable=False, index=True)
    input_digest = Column(String(64), nullable=False)
    expected = Column(JSON, nullable=False, default=dict)
    actual = Column(JSON, nullable=False, default=dict)
    trace_id = Column(String(36), ForeignKey("traces.id"), nullable=True)
    first_seen_at = Column(DateTime, nullable=False, default=utcnow)
    last_seen_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    occurrences = Column(Integer, nullable=False, default=1)


Index("ix_appointment_engineer_window", Appointment.engineer_id, Appointment.start_time, Appointment.end_time)
Index("ix_memory_user_active", Memory.user_id, Memory.is_active, Memory.occurred_at)
