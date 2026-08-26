from __future__ import annotations

from typing import Any, Dict

from agents.contracts import WorkflowPhase
from db.models import Invocation
from db.repositories import InvocationRepository


class WorkflowEvidenceError(ValueError):
    pass


class FivePhaseWorkflow:
    ORDER = [
        WorkflowPhase.DISCUSS,
        WorkflowPhase.IMPLEMENT,
        WorkflowPhase.REVIEW,
        WorkflowPhase.DELIVER,
        WorkflowPhase.DONE,
    ]
    REQUIRED = {
        WorkflowPhase.DISCUSS: {"route", "goal"},
        WorkflowPhase.IMPLEMENT: {"tool_calls"},
        WorkflowPhase.REVIEW: {"validation", "safety"},
        WorkflowPhase.DELIVER: {"response_digest"},
        WorkflowPhase.DONE: {"terminal_status", "trace_id"},
    }

    def __init__(self, repository: InvocationRepository):
        self.repository = repository

    def transition(self, invocation_id: str, phase: WorkflowPhase, evidence: Dict[str, Any]) -> None:
        missing = self.REQUIRED[phase] - set(evidence)
        if missing:
            raise WorkflowEvidenceError("missing_evidence:" + ",".join(sorted(missing)))
        invocation = self.repository.db.get(Invocation, invocation_id)
        if invocation is None:
            raise LookupError("invocation_not_found")
        current_index = self.ORDER.index(WorkflowPhase(invocation.phase))
        next_index = self.ORDER.index(phase)
        if next_index < current_index or next_index > current_index + 1:
            raise WorkflowEvidenceError("invalid_phase_transition")
        self.repository.transition(invocation_id, phase.value, evidence)
