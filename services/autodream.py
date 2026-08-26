from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from config.settings import Settings
from db.models import (
    AutoDreamJob,
    BehaviorEvent,
    ConversationSession,
    Memory,
    UserPreference,
    utcnow,
)
from services.memory import cosine, text_embedding


@dataclass
class AutoDreamResult:
    status: str
    user_id: str
    closed_sessions: int = 0
    scanned_events: int = 0
    memories_written: int = 0
    preferences_updated: int = 0
    checkpoint_event_id: Optional[str] = None
    reason: Optional[str] = None


class AutoDreamService:
    """Incremental consolidation with a durable per-user lock and checkpoint."""

    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    def run(self, user_id: str, force: bool = False, now: Optional[datetime] = None) -> AutoDreamResult:
        now = now or utcnow()
        job = self.db.get(AutoDreamJob, user_id)
        if job is None:
            job = AutoDreamJob(user_id=user_id)
            self.db.add(job)
            self.db.flush()
        if job.status == "running" and job.locked_until and job.locked_until > now:
            return AutoDreamResult(status="locked", user_id=user_id, reason="active_task_lock")
        if (
            not force
            and job.last_run_at
            and now - job.last_run_at < timedelta(hours=self.settings.autodream_min_interval_hours)
        ):
            return AutoDreamResult(status="not_due", user_id=user_id, reason="minimum_interval")

        closed_query = self.db.query(ConversationSession).filter(
            ConversationSession.user_id == user_id,
            ConversationSession.status == "closed",
            ConversationSession.closed_at.isnot(None),
        )
        if job.checkpoint_closed_at:
            closed_query = closed_query.filter(ConversationSession.closed_at > job.checkpoint_closed_at)
        closed_sessions = closed_query.order_by(ConversationSession.closed_at.asc()).all()
        if not force and len(closed_sessions) < self.settings.autodream_min_closed_sessions:
            return AutoDreamResult(
                status="not_due",
                user_id=user_id,
                closed_sessions=len(closed_sessions),
                reason="minimum_closed_sessions",
            )

        lock_token = str(uuid.uuid4())
        changed = (
            self.db.query(AutoDreamJob)
            .filter(
                AutoDreamJob.user_id == user_id,
                (AutoDreamJob.locked_until.is_(None)) | (AutoDreamJob.locked_until <= now),
            )
            .update(
                {
                    AutoDreamJob.status: "running",
                    AutoDreamJob.lock_token: lock_token,
                    AutoDreamJob.locked_until: now + timedelta(seconds=self.settings.autodream_lock_seconds),
                    AutoDreamJob.last_error: None,
                },
                synchronize_session=False,
            )
        )
        if changed != 1:
            return AutoDreamResult(status="locked", user_id=user_id, reason="lock_race_lost")
        self.db.commit()  # Publish ownership before the consolidation work starts.
        self.db.expire_all()  # expire_on_commit=False factories must reload the lock owner.

        try:
            job = self.db.get(AutoDreamJob, user_id)
            events_query = self.db.query(BehaviorEvent).filter(BehaviorEvent.user_id == user_id)
            if job.checkpoint_event_id:
                checkpoint = self.db.get(BehaviorEvent, job.checkpoint_event_id)
                if checkpoint is not None:
                    events_query = events_query.filter(BehaviorEvent.occurred_at > checkpoint.occurred_at)
            events = events_query.order_by(BehaviorEvent.occurred_at.asc(), BehaviorEvent.id.asc()).all()
            memory_count = 0
            preference_count = 0
            for event in events:
                content, memory_type, preference = self._extract(event)
                if content and self._write_memory(event, content, memory_type):
                    memory_count += 1
                if preference and self._update_preference(user_id, *preference):
                    preference_count += 1

            job = self.db.get(AutoDreamJob, user_id)
            if job.lock_token != lock_token:
                raise RuntimeError("autodream_lock_ownership_lost")
            job.status = "idle"
            job.lock_token = None
            job.locked_until = None
            job.last_run_at = now
            if events:
                job.checkpoint_event_id = events[-1].id
            if closed_sessions:
                job.checkpoint_closed_at = closed_sessions[-1].closed_at
            self.db.commit()  # Memories/preferences/checkpoint advance atomically.
            return AutoDreamResult(
                status="completed",
                user_id=user_id,
                closed_sessions=len(closed_sessions),
                scanned_events=len(events),
                memories_written=memory_count,
                preferences_updated=preference_count,
                checkpoint_event_id=job.checkpoint_event_id,
            )
        except Exception as exc:
            self.db.rollback()
            failed_job = self.db.get(AutoDreamJob, user_id)
            if failed_job is not None and failed_job.lock_token == lock_token:
                failed_job.status = "failed"
                failed_job.lock_token = None
                failed_job.locked_until = None
                failed_job.last_error = str(exc)[:512]
                self.db.commit()
            raise

    @staticmethod
    def _extract(event: BehaviorEvent) -> Tuple[Optional[str], str, Optional[Tuple[str, str]]]:
        payload = event.payload or {}
        preference = payload.get("preference")
        if isinstance(preference, dict) and preference.get("key") and preference.get("value"):
            key, value = str(preference["key"]), str(preference["value"])
            return f"用户偏好 {key}={value}", "preference", (key, value)
        if event.event_type.startswith("appointment"):
            service = payload.get("service_type", "售后服务")
            issue = payload.get("issue_category", "未分类问题")
            engineer = payload.get("engineer_name", "未指定工程师")
            return f"预约 {service}；问题 {issue}；工程师 {engineer}", "appointment", None
        if event.event_type.startswith("consult"):
            topic = payload.get("topic") or payload.get("query_digest")
            if topic:
                return f"咨询主题 {topic}", "consultation", None
        return None, "event", None

    def _write_memory(self, event: BehaviorEvent, content: str, memory_type: str) -> bool:
        if self.db.query(Memory.id).filter(Memory.source_event_id == event.id).first():
            return False
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if self.db.query(Memory.id).filter(
            Memory.user_id == event.user_id, Memory.content_hash == content_hash
        ).first():
            return False
        vector = text_embedding(content)
        near = self.db.query(Memory).filter(
            Memory.user_id == event.user_id,
            Memory.memory_type == memory_type,
            Memory.is_active.is_(True),
        ).all()
        for item in near:
            if cosine(vector, item.embedding or text_embedding(item.content)) >= 0.92:
                item.confidence = min(1.0, item.confidence + 0.05)
                return False
        self.db.add(
            Memory(
                user_id=event.user_id,
                session_id=event.session_id,
                source_event_id=event.id,
                memory_type=memory_type,
                content=content,
                content_hash=content_hash,
                embedding=vector,
                confidence=0.6,
                importance=0.7 if memory_type == "appointment" else 0.5,
                occurred_at=event.occurred_at,
            )
        )
        self.db.flush()
        return True

    def _update_preference(self, user_id: str, key: str, value: str) -> bool:
        rows = self.db.query(UserPreference).filter(
            UserPreference.user_id == user_id,
            UserPreference.preference_key == key,
        ).all()
        target = next((row for row in rows if row.preference_value == value), None)
        for row in rows:
            if row.preference_value != value:
                row.conflict_score = min(1.0, row.conflict_score + 0.1)
                row.confidence = max(0.05, row.confidence * 0.85)
        if target is None:
            self.db.add(
                UserPreference(
                    user_id=user_id,
                    preference_key=key,
                    preference_value=value,
                    confidence=0.55,
                )
            )
        else:
            target.evidence_count += 1
            target.confidence = min(1.0, target.confidence + (1.0 - target.confidence) * 0.2)
            target.conflict_score = max(0.0, target.conflict_score - 0.05)
        self.db.flush()
        return True
