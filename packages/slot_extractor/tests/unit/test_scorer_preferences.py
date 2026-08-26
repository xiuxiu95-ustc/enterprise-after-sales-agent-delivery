from slot_extractor.evaluation.scorers.preferences import (
    PreferenceMatcher,
    PreferenceSemanticScorer,
)
from slot_extractor.schemas.results import GenerationResult
from slot_extractor.schemas.sample import Sample


class _FakeEmbedder:
    def __init__(self, scores: dict[tuple[str, str], float]) -> None:
        self.scores = scores

    def similarity(self, left: str, right: str) -> float:
        return self.scores.get((left, right), self.scores.get((right, left), 0.0))


def _sample(preferences: list[str]) -> Sample:
    return Sample(
        id="preference-case",
        output_kind="final",
        conversation_kind="single_turn",
        input={},
        expected={"action": "final", "preferences": preferences},
        assertions=[],
        tags=[],
    )


def _result(preferences: list[str]) -> GenerationResult:
    import json

    output = {
        "action": "final",
        "engineer_level_preference": None,
        "engineer_level": None,
        "start_time": None,
        "duration_minutes": None,
        "preferences": preferences,
        "engineer_name": None,
        "engineer_status": "not_checked",
        "confirmation": False,
        "info_complete": False,
        "unrelated": False,
        "missing_info": ["start_time", "duration_minutes"],
    }
    return GenerationResult(
        text=json.dumps(output, ensure_ascii=False),
        model="mock",
        prefill_ms=1,
        first_token_ms=1,
        total_ms=1,
    )


def test_preference_matcher_accepts_known_semantic_aliases() -> None:
    matcher = PreferenceMatcher()

    assert matcher.matches("网络", "网络故障") is True
    assert matcher.matches("软件", "软件支持") is True
    assert matcher.matches("常规", "常规一点") is True


def test_preference_matcher_rejects_opposite_meaning() -> None:
    matcher = PreferenceMatcher()

    assert matcher.matches("常规", "紧急一些") is False
    assert matcher.matches("喜欢硬件", "不要硬件") is False


def test_preference_matcher_uses_vector_fallback_for_unlisted_wording() -> None:
    matcher = PreferenceMatcher(
        embedder=_FakeEmbedder({("重点数据库故障", "数据库故障"): 0.88})
    )

    assert matcher.matches("重点数据库故障", "数据库故障") is True


def test_preference_matcher_accepts_embedding_equivalence_and_rejects_negation() -> None:
    matcher = PreferenceMatcher(
        embedder=_FakeEmbedder(
            {
                ("网络", "网络售后服务"): 0.84,
                ("软件", "软件售后服务"): 0.79,
                ("网络", "不要售后服务网络"): 0.90,
            }
        )
    )

    assert matcher.matches("网络", "网络售后服务") is True
    assert matcher.matches("软件", "软件售后服务") is True
    assert matcher.matches("网络", "不要售后服务网络") is False


def test_preference_scorer_uses_one_to_one_f1() -> None:
    scorer = PreferenceSemanticScorer()

    full = scorer.score(_sample(["网络", "常规"]), _result(["网络诊断", "常规一点"]))
    missing = scorer.score(_sample(["网络", "常规"]), _result(["网络诊断"]))
    extra = scorer.score(_sample(["网络"]), _result(["网络诊断", "软件"]))

    assert full.score == 1.0
    assert full.passed is True
    assert missing.score == 2 / 3
    assert extra.score == 2 / 3


def test_preference_scorer_empty_only_matches_empty() -> None:
    scorer = PreferenceSemanticScorer()

    assert scorer.score(_sample([]), _result([])).score == 1.0
    assert scorer.score(_sample([]), _result(["网络"])).score == 0.0
