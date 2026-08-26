from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from agents.contracts import Actor
from db.models import Appointment, Engineer
from db.repositories import AppointmentRepository, AuditRepository
from services.memory import cosine, text_embedding
from services.security import AuthorizationService
from services.slot_extraction import AppointmentSlots


class AppointmentStateMachine:
    TRANSITIONS = {
        "collecting": {"awaiting_confirmation", "cancelled"},
        "awaiting_confirmation": {"confirmed", "collecting", "cancelled", "expired"},
        "confirmed": {"cancelled", "completed", "no_show"},
        "cancelled": set(),
        "completed": set(),
        "no_show": set(),
        "expired": set(),
    }

    @classmethod
    def transition(cls, current: str, target: str) -> str:
        if target not in cls.TRANSITIONS.get(current, set()):
            raise ValueError("invalid_appointment_state_transition")
        return target

    @staticmethod
    def draft_state(slots: AppointmentSlots) -> str:
        if slots.missing_info:
            return "collecting"
        return "confirmed" if slots.confirmation else "awaiting_confirmation"


@dataclass
class EngineerMatch:
    engineer_id: str
    engineer_name: str
    skills: List[str]
    score: float
    substitution_for: Optional[str] = None


class AppointmentService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = AppointmentRepository(db)
        self.authorization = AuthorizationService()

    @staticmethod
    def parse_window(slots: AppointmentSlots) -> Tuple[datetime, datetime]:
        if not slots.start_time or not slots.duration_minutes:
            raise ValueError("appointment_slots_incomplete")
        start = datetime.strptime(slots.start_time, "%Y-%m-%d %H:%M")
        if slots.duration_minutes < 30 or slots.duration_minutes > 480:
            raise ValueError("duration_out_of_range")
        if slots.duration_minutes % 30 != 0:
            raise ValueError("duration_must_align_to_30_minutes")
        return start, start + timedelta(minutes=slots.duration_minutes)

    def match_engineers(self, slots: AppointmentSlots) -> List[EngineerMatch]:
        start, end = self.parse_window(slots)
        available = self.repository.list_available_engineers(
            start, end, slots.required_skills, slots.location
        )
        requested = None
        if slots.engineer_name:
            requested = self.db.query(Engineer).filter(
                Engineer.name == slots.engineer_name, Engineer.active.is_(True)
            ).one_or_none()
            if requested and any(item.id == requested.id for item in available):
                return [self._match(requested, slots.required_skills, None)]
        target_skills = requested.skills if requested else slots.required_skills
        ranked = [self._match(item, target_skills, requested.name if requested else None) for item in available]
        ranked.sort(key=lambda item: (-item.score, item.engineer_id))
        return ranked[:5]

    @staticmethod
    def _match(engineer: Engineer, target_skills: List[str], substitution_for: Optional[str]) -> EngineerMatch:
        target_vector = text_embedding(" ".join(target_skills))
        engineer_vector = engineer.skill_embedding or text_embedding(" ".join(engineer.skills or []))
        score = cosine(target_vector, engineer_vector) if target_skills else 0.5
        return EngineerMatch(
            engineer_id=engineer.id,
            engineer_name=engineer.name,
            skills=list(engineer.skills or []),
            score=round(score, 6),
            substitution_for=substitution_for,
        )

    def create(
        self,
        actor: Actor,
        user_id: str,
        session_id: str,
        slots: AppointmentSlots,
        engineer_id: str,
        idempotency_key: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> Tuple[Appointment, bool]:
        decision = self.authorization.authorize(actor, "appointment:create")
        AuditRepository(self.db).record(
            actor.actor_id, actor.role, "appointment.create", "appointment",
            "allowed" if decision.allowed else "denied", decision.risk_level,
            {"user_id": user_id, "session_id": session_id}, trace_id=trace_id,
        )
        if not decision.allowed:
            raise PermissionError(decision.reason)
        start, end = self.parse_window(slots)
        if start <= datetime.now() - timedelta(minutes=1):
            raise ValueError("appointment_must_be_in_future")
        stable = f"{user_id}|{session_id}|{engineer_id}|{start.isoformat()}|{end.isoformat()}"
        key = idempotency_key or hashlib.sha256(stable.encode("utf-8")).hexdigest()
        values = asdict(slots)
        values["state"] = "confirmed"
        return self.repository.create_reserved(
            user_id, session_id, engineer_id, values, start, end, key
        )

    def cancel(self, actor: Actor, appointment_id: str, expected_version: int) -> Appointment:
        decision = self.authorization.authorize(actor, "appointment:cancel")
        if not decision.allowed:
            raise PermissionError(decision.reason)
        appointment = self.repository.cancel(appointment_id, expected_version)
        AuditRepository(self.db).record(
            actor.actor_id, actor.role, "appointment.cancel", "appointment",
            "allowed", decision.risk_level, {"version": expected_version}, resource_id=appointment_id,
        )
        return appointment

