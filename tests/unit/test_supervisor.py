import pytest

from agents.contracts import AgentIntent
from agents.supervisor import AgentLoopError, LoopGuard, SupervisorPlanner


@pytest.mark.unit
@pytest.mark.parametrize(
    "message,expected",
    [
        ("保修政策怎么规定？", AgentIntent.CONSULT),
        ("预约明天下午上门维修", AgentIntent.APPOINTMENT),
        ("查看我的服务偏好画像", AgentIntent.BEHAVIOR),
        ("写一首诗", AgentIntent.UNSUPPORTED),
    ],
)
def test_supervisor_routes_enterprise_intents(message, expected):
    assert SupervisorPlanner().decide(message).intent == expected


@pytest.mark.unit
def test_loop_guard_blocks_repeated_tool_signature():
    guard = LoopGuard(max_steps=6)
    guard.observe("query_knowledge_hub", {"q": "same"})
    with pytest.raises(AgentLoopError, match="repeated_tool_signature"):
        guard.observe("query_knowledge_hub", {"q": "same"})


@pytest.mark.unit
def test_loop_guard_enforces_step_budget():
    guard = LoopGuard(max_steps=2)
    guard.observe("a", {"n": 1})
    guard.observe("b", {"n": 2})
    with pytest.raises(AgentLoopError, match="max_agent_steps_exceeded"):
        guard.observe("c", {"n": 3})

