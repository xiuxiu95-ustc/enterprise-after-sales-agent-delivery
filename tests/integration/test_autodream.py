from datetime import timedelta

import pytest

from db.models import AutoDreamJob, ConversationSession, Memory, UserPreference, utcnow
from db.repositories import BehaviorRepository, SessionRepository
from services.autodream import AutoDreamService


@pytest.mark.integration
def test_autodream_threshold_checkpoint_and_conflict_downrank(db, settings):
    now = utcnow()
    for index in range(5):
        session = SessionRepository(db).create("u-dream")
        session.status = "closed"
        session.closed_at = now - timedelta(hours=5 - index)
    BehaviorRepository(db).record("u-dream", "preference.observed", {"preference": {"key": "service_mode", "value": "remote"}}, "dream-event-1")
    BehaviorRepository(db).record("u-dream", "preference.observed", {"preference": {"key": "service_mode", "value": "onsite"}}, "dream-event-2")
    db.flush()
    result = AutoDreamService(db, settings).run("u-dream", now=now)
    assert result.status == "completed"
    assert result.scanned_events == 2
    assert db.query(Memory).filter(Memory.user_id == "u-dream").count() == 2
    preferences = db.query(UserPreference).filter(UserPreference.user_id == "u-dream").all()
    assert len(preferences) == 2
    assert any(item.conflict_score > 0 for item in preferences)
    again = AutoDreamService(db, settings).run("u-dream", now=now + timedelta(hours=1))
    assert again.status == "not_due"
    assert again.reason == "minimum_interval"


@pytest.mark.integration
def test_autodream_respects_active_lock(db, settings):
    now = utcnow()
    db.add(AutoDreamJob(user_id="u-lock", status="running", lock_token="owner", locked_until=now + timedelta(minutes=5)))
    db.flush()
    result = AutoDreamService(db, settings).run("u-lock", force=True, now=now)
    assert result.status == "locked"

