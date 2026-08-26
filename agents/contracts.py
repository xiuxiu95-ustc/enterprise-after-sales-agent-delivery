from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AgentIntent(str, Enum):
    CONSULT = "consult"
    APPOINTMENT = "appointment"
    BEHAVIOR = "behavior"
    MIXED = "mixed"
    UNSUPPORTED = "unsupported"


class WorkflowPhase(str, Enum):
    DISCUSS = "discuss"
    IMPLEMENT = "implement"
    REVIEW = "review"
    DELIVER = "deliver"
    DONE = "done"


@dataclass
class AgentDecision:
    intent: AgentIntent
    target_agent: str
    tools: List[str] = field(default_factory=list)
    reason_code: str = "rule_route"


@dataclass
class ToolResult:
    tool_name: str
    ok: bool
    data: Dict[str, Any]
    error_code: Optional[str] = None


@dataclass
class Actor:
    actor_id: str
    role: str
    confirmed: bool = False

