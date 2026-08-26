from slot_extractor.data.coverage_audit import audit_semantic_coverage
from slot_extractor.data.raw_sample import RawSample


def _replacement_sample() -> RawSample:
    return RawSample(
        id="replace",
        output_kind="tool_call",
        conversation_kind="multi_turn",
        tags=("工具调用", "易混边界"),
        input={
            "history": [],
            "user_input": "换成李师傅",
            "current_time": "2026-08-01 10:00",
            "current_state": {
                "engineer_name": "王师傅",
                "engineer_level": "standard",
                "start_time": "2026-08-02 14:00",
                "duration_minutes": 60,
                "engineer_level_preference": None,
                "preferences": ["安静"],
            },
            "available_tools": ["find_engineers"],
        },
        expected={
            "action": "tool_call",
            "tool_name": "find_engineers",
            "arguments": {
                "engineer_name": "李师傅",
                "start_time": "2026-08-02 14:00",
                "duration_minutes": 60,
                "engineer_level_preference": None,
                "preferences": ["安静"],
            },
        },
        dpo_targets=("P6",),
    )


def test_audit_reports_all_missing_semantic_coverage() -> None:
    report = audit_semantic_coverage([])
    assert report.missing_statuses == {"unavailable", "not_found", "no_match"}
    assert "acknowledge_result" in report.missing_reply_types
    assert report.missing_confirmation_false
    assert report.missing_minimal_engineer_replacement


def test_audit_recognizes_minimal_engineer_replacement() -> None:
    report = audit_semantic_coverage([_replacement_sample()])
    assert not report.missing_minimal_engineer_replacement
