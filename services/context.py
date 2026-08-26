from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from config.settings import Settings
from db.models import ConversationSession, Message
from db.repositories import SessionRepository


@dataclass
class ContextBundle:
    summary: str
    messages: List[Dict[str, str]]
    slots: Dict[str, Any]
    token_count: int
    summarized: bool


class ContextWindowService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    def build(self, session_id: str) -> ContextBundle:
        repository = SessionRepository(self.db)
        conversation = repository.require(session_id)
        all_messages = repository.list_messages(session_id, limit=1000)
        threshold = int(self.settings.context_window_tokens * self.settings.context_summary_ratio)
        summarized = False
        if conversation.context_tokens >= threshold and len(all_messages) > self.settings.recent_message_limit:
            old_boundary = len(all_messages) - self.settings.recent_message_limit
            old = all_messages[conversation.summary_message_count : old_boundary]
            if old:
                conversation.summary = self._summarize(old, conversation.summary or "")
                conversation.summary_generation += 1
                conversation.summary_message_count = old_boundary
                summarized = True
        recent = all_messages[-self.settings.recent_message_limit :]
        return ContextBundle(
            summary=conversation.summary or "",
            messages=[{"role": item.role, "content": item.content} for item in recent],
            slots=dict(conversation.slot_state or {}),
            token_count=sum(item.token_count for item in recent),
            summarized=summarized,
        )

    @staticmethod
    def _summarize(messages: List[Message], previous: str) -> str:
        facts = []
        if previous:
            facts.append(previous[-1200:])
        for message in messages[-20:]:
            compact = " ".join(message.content.split())[:160]
            facts.append(f"{message.role}:{compact}")
        return " | ".join(facts)[-3000:]
