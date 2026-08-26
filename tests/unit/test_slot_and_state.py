from datetime import datetime

import pytest

from services.appointment import AppointmentStateMachine
from services.slot_extraction import SlotExtractorAdapter


@pytest.mark.unit
def test_enterprise_slot_fallback_extracts_and_merges(settings):
    extractor = SlotExtractorAdapter(settings)
    first = extractor.extract(
        "预约明天下午2点上门维修网络，2小时，地址北京",
        now=datetime(2026, 8, 26, 10, 0),
    )
    assert first.service_type == "onsite_repair"
    assert first.issue_category == "network"
    assert first.start_time == "2026-08-27 14:00"
    assert first.duration_minutes == 120
    assert first.location == "北京"
    assert first.missing_info == []
    confirmed = extractor.extract("确认预约", first.__dict__, now=datetime(2026, 8, 26, 10, 1))
    assert confirmed.confirmation is True
    assert confirmed.service_type == "onsite_repair"


@pytest.mark.unit
def test_appointment_state_machine_rejects_illegal_jump():
    assert AppointmentStateMachine.transition("collecting", "awaiting_confirmation") == "awaiting_confirmation"
    with pytest.raises(ValueError, match="invalid_appointment_state_transition"):
        AppointmentStateMachine.transition("collecting", "completed")

