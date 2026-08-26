from __future__ import annotations

from sqlalchemy.orm import Session

from db.models import Handoff, Invocation, Trace, utcnow
from db.repositories import InvocationRepository


class RecoveryService:
    """Close durable active states after an unclean process exit."""

    def __init__(self, db: Session):
        self.db = db

    def reconcile(self) -> dict:
        repository = InvocationRepository(self.db)
        active_invocations = self.db.query(Invocation).filter(Invocation.status == "active").all()
        for invocation in active_invocations:
            repository.terminal(invocation.id, "failed", error_code="process_restarted")
        pending_handoffs = self.db.query(Handoff).filter(Handoff.status.in_(["pending", "started"])).all()
        for handoff in pending_handoffs:
            handoff.status = "failed"
            handoff.failure_code = "process_restarted"
            handoff.completed_at = utcnow()
        active_traces = self.db.query(Trace).filter(Trace.status == "active").all()
        for trace in active_traces:
            trace.status = "failed"
            trace.error_code = "process_restarted"
            trace.incomplete = True
            trace.ended_at = utcnow()
            trace.duration_ms = max(0.0, (trace.ended_at - trace.started_at).total_seconds() * 1000.0)
        self.db.commit()
        return {
            "invocations_failed": len(active_invocations),
            "handoffs_failed": len(pending_handoffs),
            "traces_failed": len(active_traces),
        }

