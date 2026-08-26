from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class AvailabilityWindow:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start >= self.end or self.start.date() != self.end.date():
            raise ValueError("availability window must be an increasing same-day interval")

    def contains(self, start: datetime, end: datetime) -> bool:
        return self.start <= start < end <= self.end


@dataclass(frozen=True)
class Engineer:
    name: str
    level: Literal["standard", "expert"]
    specialties: tuple[str, ...]
    availability: tuple[AvailabilityWindow, ...]


@dataclass(frozen=True)
class ToolQuery:
    engineer_name: str | None
    start_time: datetime
    duration_minutes: int
    engineer_level_preference: Literal["standard", "expert"] | None
    preferences: tuple[str, ...]


@dataclass(frozen=True)
class EngineerMatch:
    name: str
    level: Literal["standard", "expert"]


@dataclass(frozen=True)
class EngineerTrace:
    name: str
    considered: bool
    matched: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class CanonicalToolResult:
    status: str
    query: ToolQuery
    candidates: tuple[EngineerMatch, ...]
    trace: tuple[EngineerTrace, ...]
    explanation: str
    error_code: str | None = None


@dataclass(frozen=True)
class ToolLoopEvent:
    seq: int
    kind: Literal["start", "model_output", "tool_result", "reply", "error", "complete"]
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class CompareEvent:
    side: Literal["left", "right"]
    event: ToolLoopEvent
    comparable: bool
