import pytest

from db.models import InvocationEvent
from db.repositories import HandoffRepository, InvocationRepository, SessionRepository
from services.recovery import RecoveryService


@pytest.mark.integration
def test_handoff_is_consumed_exactly_once(db):
    session = SessionRepository(db).create("u-handoff")
    invocations = InvocationRepository(db)
    trace = invocations.create_trace(session.id)
    source = invocations.create(session.id, trace.id, "supervisor_agent", "request")
    repository = HandoffRepository(db)
    handoff, created = repository.create_or_get(source.id, "supervisor_agent", "appointment_agent", "appointment", "dedupe-1", {"what": "book", "why": "route", "next_action": "extract"})
    assert created is True
    _, target, consumed = repository.consume_once_and_start(handoff.id, session.id, trace.id, "request")
    assert consumed is True
    assert target is not None
    _, same_target, consumed_again = repository.consume_once_and_start(handoff.id, session.id, trace.id, "request")
    assert consumed_again is False
    assert same_target.id == target.id


@pytest.mark.integration
def test_restart_recovery_closes_active_truth_rows(db):
    session = SessionRepository(db).create("u-recovery")
    repository = InvocationRepository(db)
    trace = repository.create_trace(session.id)
    invocation = repository.create(session.id, trace.id, "supervisor_agent", "request")
    result = RecoveryService(db).reconcile()
    assert result["invocations_failed"] == 1
    assert invocation.status == "failed"
    assert trace.status == "failed"
    assert db.query(InvocationEvent).filter(InvocationEvent.event_type == "invocation.ended").count() == 1

