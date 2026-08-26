from datetime import datetime, timedelta

import pytest

from agents.contracts import Actor
from db.models import Engineer, EngineerShift
from db.repositories import AppointmentRepository, SessionRepository
from services.appointment import AppointmentService
from services.memory import text_embedding
from services.slot_extraction import AppointmentSlots


def _engineer(db):
    engineer = Engineer(employee_code="T-1", name="并发工程师", skills=["network"], skill_embedding=text_embedding("network"), service_regions=["北京"])
    db.add(engineer)
    db.flush()
    now = datetime.now()
    db.add(EngineerShift(engineer_id=engineer.id, start_time=now, end_time=now + timedelta(days=3)))
    db.flush()
    return engineer


@pytest.mark.integration
def test_appointment_idempotency_and_overlap_guard(db):
    engineer = _engineer(db)
    session_a = SessionRepository(db).create("u-a")
    session_b = SessionRepository(db).create("u-b")
    start = (datetime.now() + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
    slots = AppointmentSlots(service_type="onsite_repair", issue_category="network", start_time=start.strftime("%Y-%m-%d %H:%M"), duration_minutes=60, required_skills=["network"], location="北京", confirmation=True)
    actor_a = Actor("u-a", "customer", True)
    first, created = AppointmentService(db).create(actor_a, "u-a", session_a.id, slots, engineer.id, "same-key-123")
    db.commit()
    duplicate, created_again = AppointmentService(db).create(actor_a, "u-a", session_a.id, slots, engineer.id, "same-key-123")
    assert duplicate.id == first.id
    assert created is True and created_again is False
    with pytest.raises(ValueError, match="appointment_time_conflict"):
        AppointmentService(db).create(Actor("u-b", "customer", True), "u-b", session_b.id, slots, engineer.id, "other-key-456")
    db.rollback()

