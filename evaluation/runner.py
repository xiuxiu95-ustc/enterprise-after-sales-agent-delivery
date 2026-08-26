from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from agents.supervisor import SupervisorPlanner
from config.settings import Settings, get_settings
from db.models import EvaluationFailure, KnowledgeDocument, utcnow
from db.repositories import KnowledgeRepository
from services.security import ToolPolicy
from services.slot_extraction import SlotExtractorAdapter


CASES_PATH = Path(__file__).with_name("cases.json")


def percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    index = min(len(values) - 1, max(0, int((len(values) * p) + 0.999999) - 1))
    return values[index]


class EvaluationRunner:
    """EDD runner for routing, slots, RAG, tools, trajectory and safety gates."""

    def __init__(self, settings: Settings, db: Session):
        self.settings = settings
        self.db = db
        self.dataset = json.loads(CASES_PATH.read_text(encoding="utf-8"))

    def run(self, layers: Optional[Iterable[str]] = None) -> Dict[str, Any]:
        selected = set(layers or [])
        cases = [case for case in self.dataset["cases"] if not selected or case["layer"] in selected]
        results = []
        timings = []
        for case in cases:
            started = time.perf_counter()
            actual = self._evaluate(case)
            elapsed = (time.perf_counter() - started) * 1000.0
            timings.append(elapsed)
            passed = bool(actual.pop("passed"))
            result = {"case_id": case["id"], "layer": case["layer"], "passed": passed, "elapsed_ms": round(elapsed, 3), "actual": actual}
            results.append(result)
            if not passed:
                self._record_failure(case, actual)
        passed_count = sum(1 for result in results if result["passed"])
        safety = [result for result in results if result["layer"] == "safety"]
        thresholds = self.dataset["thresholds"]
        success_rate = passed_count / max(1, len(results))
        safety_rate = sum(1 for result in safety if result["passed"]) / max(1, len(safety))
        p95 = percentile(timings, 0.95)
        gate = {
            "task_success_rate": success_rate >= thresholds["task_success_rate"],
            "safety_pass_rate": safety_rate >= thresholds["safety_pass_rate"],
            "p95_ms": p95 <= thresholds["p95_ms"],
            "max_agent_steps": self.settings.max_agent_steps <= thresholds["max_agent_steps"],
        }
        self.db.commit()
        return {
            "dataset_version": self.dataset["version"],
            "cases": len(results),
            "passed": passed_count,
            "failed": len(results) - passed_count,
            "task_success_rate": round(success_rate, 6),
            "safety_pass_rate": round(safety_rate, 6),
            "p95_ms": round(p95, 3),
            "gate": gate,
            "gate_passed": all(gate.values()),
            "results": results,
        }

    def _evaluate(self, case: Dict[str, Any]) -> Dict[str, Any]:
        layer = case["layer"]
        expected = case["expected"]
        if layer == "routing":
            decision = SupervisorPlanner().decide(case["input"])
            return {"passed": decision.intent.value == expected["intent"], "intent": decision.intent.value}
        if layer == "slot":
            slots = SlotExtractorAdapter(self.settings).extract(case["input"], case.get("state", {}))
            if "confirmation" in expected:
                passed = slots.confirmation is expected["confirmation"]
            else:
                passed = all(name not in slots.missing_info for name in expected["missing_excludes"])
            return {"passed": passed, "missing_info": slots.missing_info, "confirmation": slots.confirmation, "source": slots.source}
        if layer == "rag":
            rows = KnowledgeRepository(self.db).search_local(case["input"], self.settings.rag_collection, 5)
            return {"passed": len(rows) >= expected["min_candidates"], "candidate_count": len(rows)}
        if layer == "tool":
            decision = SupervisorPlanner().decide(case["input"])
            policy = ToolPolicy(self.settings.allowed_tools)
            ok = True
            for tool in decision.tools:
                try:
                    policy.require(tool)
                except PermissionError:
                    ok = False
            return {"passed": ok is expected["all_whitelisted"], "tools": decision.tools}
        if layer == "trajectory":
            decision = SupervisorPlanner().decide(case["input"])
            steps = len(decision.tools)
            return {"passed": steps <= expected["max_steps"], "steps": steps}
        if layer == "safety":
            decision = SupervisorPlanner().decide(case["input"])
            if "intent" in expected:
                passed = decision.intent.value == expected["intent"] and expected["forbidden_tool"] not in decision.tools
                return {"passed": passed, "intent": decision.intent.value, "tools": decision.tools}
            slots = SlotExtractorAdapter(self.settings).extract(case["input"])
            return {"passed": slots.confirmation is expected["confirmation"], "confirmation": slots.confirmation}
        return {"passed": False, "error": "unknown_evaluation_layer"}

    def _record_failure(self, case: Dict[str, Any], actual: Dict[str, Any]) -> None:
        digest = hashlib.sha256(case["input"].encode("utf-8")).hexdigest()
        row = self.db.query(EvaluationFailure).filter(
            EvaluationFailure.case_id == case["id"],
            EvaluationFailure.layer == case["layer"],
            EvaluationFailure.input_digest == digest,
        ).one_or_none()
        if row is None:
            self.db.add(EvaluationFailure(case_id=case["id"], layer=case["layer"], input_digest=digest, expected=case["expected"], actual=actual))
        else:
            row.actual = actual
            row.occurrences += 1
            row.last_seen_at = utcnow()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail-on-gate", action="store_true")
    parser.add_argument("--layers", default="")
    args = parser.parse_args()
    from db.session import build_session_factory, init_db, make_engine
    from services.bootstrap import seed_reference_data

    settings = get_settings()
    engine = make_engine(settings.database_url)
    init_db(engine)
    factory = build_session_factory(engine)
    db = factory()
    try:
        seed_reference_data(db, settings)
        report = EvaluationRunner(settings, db).run([item for item in args.layers.split(",") if item])
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if args.fail_on_gate and not report["gate_passed"] else 0
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())

