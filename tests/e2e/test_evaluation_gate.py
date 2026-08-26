import pytest


@pytest.mark.e2e
def test_edd_gate_passes_and_failure_registry_is_queryable(client):
    headers = {"X-Role": "supervisor", "X-Actor-Id": "qa-lead"}
    response = client.post("/api/v1/evaluations/run", json={"layers": ["routing", "slot", "rag", "tool", "trajectory", "safety"]}, headers=headers)
    assert response.status_code == 200
    report = response.json()
    assert report["gate_passed"] is True
    failures = client.get("/api/v1/evaluations/failures", headers=headers)
    assert failures.status_code == 200

