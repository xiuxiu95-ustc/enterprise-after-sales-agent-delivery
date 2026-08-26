from datetime import timedelta

import pytest

from agents.contracts import Actor
from db.models import Memory, utcnow
from db.repositories import SessionRepository, digest_text
from services.context import ContextWindowService
from services.memory import MemoryService, text_embedding
from services.security import AuthorizationService, ToolPolicy


@pytest.mark.unit
def test_context_keeps_latest_ten_and_rolls_summary(db, settings):
    conversation = SessionRepository(db).create("u-context")
    for index in range(14):
        SessionRepository(db).add_message(conversation.id, "user", f"第{index}轮：" + "网络故障" * 8)
    bundle = ContextWindowService(db, settings).build(conversation.id)
    assert bundle.summarized is True
    assert len(bundle.messages) == 10
    assert "第3轮" in bundle.summary


@pytest.mark.unit
def test_memory_recall_uses_weighted_top_five(db):
    now = utcnow()
    for index, content in enumerate(["偏好网络远程支持", "曾预约打印机上门", "咨询保修政策", "空调保养", "软件升级", "无关旧记录"]):
        db.add(
            Memory(
                user_id="u-memory",
                memory_type="preference",
                content=content,
                content_hash=digest_text(content),
                embedding=text_embedding(content),
                confidence=0.8,
                importance=0.9 if "网络" in content else 0.4,
                occurred_at=now - timedelta(days=index * 10),
            )
        )
    db.flush()
    hits = MemoryService(db).recall("u-memory", "网络远程", top_k=5, now=now)
    assert len(hits) == 5
    assert hits[0].content == "偏好网络远程支持"
    assert hits[0].score >= hits[-1].score


@pytest.mark.unit
def test_security_requires_confirmation_and_tool_whitelist():
    service = AuthorizationService()
    denied = service.authorize(Actor("u", "customer", False), "appointment:create")
    assert denied.allowed is False
    assert denied.reason == "explicit_confirmation_required"
    assert service.authorize(Actor("u", "customer", True), "appointment:create").allowed is True
    with pytest.raises(PermissionError, match="tool_not_whitelisted"):
        ToolPolicy(["safe_tool"]).require("delete_database")

