from datetime import time, timedelta

from .fixture_store import FixtureStore
from .models import (
    CanonicalToolResult,
    EngineerMatch,
    EngineerTrace,
    ToolQuery,
)

SUPPORTED = {"网络", "硬件", "软件", "数据库", "紧急级别", "常规级别"}
GENERIC_PREFERENCES = {"售后服务"}
ALIASES = {
    "网络售后服务": "网络",
    "硬件售后服务": "硬件",
    "软件售后服务": "软件",
    "数据库售后服务": "数据库",
    "紧急": "紧急级别",
    "高优先级": "紧急级别",
    "尽快处理": "紧急级别",
    "普通": "常规级别",
    "常规": "常规级别",
    "非紧急": "常规级别",
}


class FindEngineersExecutor:
    def __init__(self, store: FixtureStore) -> None:
        self.store = store

    def find(self, query: ToolQuery) -> CanonicalToolResult:
        end = query.start_time + timedelta(minutes=query.duration_minutes)
        dates = {
            window.start.date()
            for engineer in self.store.engineers()
            for window in engineer.availability
        }
        if (
            query.duration_minutes <= 0
            or query.start_time.date() != end.date()
            or query.start_time.date() not in dates
            or query.start_time.time() < time(9)
            or end.time() > time(21)
        ):
            return self._result(
                query, "mock_coverage_miss", (), (), "查询超出 Demo 日历范围", "unsupported_time"
            )
        preference_pairs = tuple(
            (original, ALIASES.get(original, original))
            for original in query.preferences
            if original not in GENERIC_PREFERENCES
        )
        normalized_preferences = tuple(normalized for _, normalized in preference_pairs)
        unsupported = tuple(
            original
            for original, normalized in preference_pairs
            if normalized not in SUPPORTED
        )
        if unsupported:
            return self._result(
                query,
                "mock_coverage_miss",
                (),
                (),
                f"未建模偏好：{'、'.join(unsupported)}",
                "unsupported_preferences",
            )
        engineers = self.store.engineers()
        named = next((tech for tech in engineers if tech.name == query.engineer_name), None)
        if query.engineer_name and named is None:
            traces = tuple(
                EngineerTrace(tech.name, False, False, ("姓名不匹配",)) for tech in engineers
            )
            return self._result(query, "not_found", (), traces, "指定工程师不存在")
        traces = []
        matches = []
        for engineer in engineers:
            considered = query.engineer_name is None or engineer.name == query.engineer_name
            reasons = []
            if not considered:
                reasons.append("姓名不匹配")
            if (
                considered
                and query.engineer_level_preference
                and engineer.level != query.engineer_level_preference
            ):
                reasons.append("能力等级不匹配")
            missing = [
                original
                for original, normalized in preference_pairs
                if normalized not in engineer.specialties
            ]
            if considered and missing:
                reasons.append(f"缺少专长：{'、'.join(missing)}")
            if considered and not any(
                window.contains(query.start_time, end) for window in engineer.availability
            ):
                reasons.append("时间不可用")
            matched = considered and not reasons
            traces.append(EngineerTrace(engineer.name, considered, matched, tuple(reasons)))
            if matched:
                matches.append(EngineerMatch(engineer.name, engineer.level))
        if query.engineer_name:
            status = "available" if matches else "unavailable"
        elif len(matches) == 1:
            status = "matched"
        elif len(matches) == 0:
            status = "no_match"
        else:
            return self._result(
                query,
                "mock_coverage_miss",
                tuple(matches),
                tuple(traces),
                "查询命中多个候选，Demo 不静默选择",
                "ambiguous_candidates",
            )
        return self._result(query, status, tuple(matches), tuple(traces), f"匹配结果：{status}")

    @staticmethod
    def _result(query, status, candidates, trace, explanation, error_code=None):
        return CanonicalToolResult(status, query, candidates, trace, explanation, error_code)
