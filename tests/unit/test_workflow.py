import pytest

from agents.contracts import WorkflowPhase
from db.repositories import InvocationRepository, SessionRepository
from services.workflow import FivePhaseWorkflow, WorkflowEvidenceError


@pytest.mark.unit
def test_five_phase_workflow_requires_versioned_evidence(db):
    session = SessionRepository(db).create("u-workflow")
    repository = InvocationRepository(db)
    trace = repository.create_trace(session.id)
    invocation = repository.create(session.id, trace.id, "supervisor_agent", "goal")
    workflow = FivePhaseWorkflow(repository)
    workflow.transition(invocation.id, WorkflowPhase.DISCUSS, {"route": "consultation_agent", "goal": "consult"})
    with pytest.raises(WorkflowEvidenceError, match="missing_evidence"):
        workflow.transition(invocation.id, WorkflowPhase.IMPLEMENT, {})
    workflow.transition(invocation.id, WorkflowPhase.IMPLEMENT, {"tool_calls": []})
    workflow.transition(invocation.id, WorkflowPhase.REVIEW, {"validation": "ok", "safety": "passed"})
    workflow.transition(invocation.id, WorkflowPhase.DELIVER, {"response_digest": "abc"})
    workflow.transition(invocation.id, WorkflowPhase.DONE, {"terminal_status": "completed", "trace_id": trace.id})
    assert invocation.phase == "done"

