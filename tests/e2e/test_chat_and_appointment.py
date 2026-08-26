from datetime import datetime, timedelta

import pytest


@pytest.mark.e2e
def test_grounded_consultation_and_sse_terminal_event(client):
    response = client.post("/api/v1/chat", json={"user_id": "u-chat", "message": "保修上门费用怎么规定？"})
    assert response.status_code == 200
    body = response.json()
    assert "企业知识库" in body["message"]
    assert body["result"]["status"] == "completed"
    stream = client.post("/api/v1/chat/stream", json={"user_id": "u-stream", "message": "SLA 响应时间怎么规定？"})
    assert stream.status_code == 200
    assert "event: run.completed" in stream.text
    assert "event: citation" in stream.text


@pytest.mark.e2e
def test_multi_turn_appointment_confirmation_is_idempotent(client):
    session = client.post("/api/v1/sessions", json={"user_id": "u-book"}).json()
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    first = client.post(
        "/api/v1/chat",
        json={"user_id": "u-book", "session_id": session["id"], "message": f"预约{tomorrow} 14:00上门维修网络，2小时，地址北京，指定张伟工程师"},
    )
    assert first.status_code == 200
    assert first.json()["result"]["appointment_state"] == "awaiting_confirmation"
    second = client.post(
        "/api/v1/chat",
        json={"user_id": "u-book", "session_id": session["id"], "message": "确认预约", "idempotency_key": "e2e-booking-key-001"},
    )
    assert second.status_code == 200
    body = second.json()
    assert body["result"]["appointment_state"] == "confirmed"
    appointment_id = body["result"]["resource_id"]
    rows = client.get("/api/v1/appointments", params={"user_id": "u-book"}).json()
    assert [item["id"] for item in rows] == [appointment_id]

