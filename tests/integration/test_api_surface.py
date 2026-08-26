import pytest


@pytest.mark.integration
def test_api_has_more_than_sixteen_business_endpoints(client):
    paths = {
        path
        for path in client.get("/openapi.json").json()["paths"]
        if path.startswith("/api/v1")
    }
    assert len(paths) >= 16
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["storage"] == "sqlite"


@pytest.mark.integration
def test_high_risk_admin_endpoint_is_denied_to_customer(client):
    response = client.post(
        "/api/v1/engineers",
        json={"employee_code": "X", "name": "非法写入", "skills": ["network"], "service_regions": []},
    )
    assert response.status_code == 403
