import json
from types import SimpleNamespace

import pytest

from services.slot_extraction import ENTERPRISE_SLOT_SCHEMA, SlotExtractorAdapter


class FakePostTrainingBackend:
    def __init__(self):
        self.params = None

    def generate(self, messages, params):
        self.params = params
        return SimpleNamespace(
            text=json.dumps(
                {
                    "service_type": "remote_support",
                    "issue_category": "software",
                    "start_time": "2030-01-01 10:00",
                    "duration_minutes": 60,
                    "engineer_name": None,
                    "required_skills": ["software"],
                    "location": None,
                    "contact": None,
                    "confirmation": False,
                }
            )
        )


@pytest.mark.unit
def test_post_training_backend_is_reused_through_enterprise_schema(settings):
    adapter = SlotExtractorAdapter(settings)
    adapter.backend = FakePostTrainingBackend()
    slots = adapter.extract("安排远程支持")
    assert slots.source == "post_training_backend_adapter"
    assert slots.service_type == "remote_support"
    assert adapter.backend.params.response_schema == ENTERPRISE_SLOT_SCHEMA

