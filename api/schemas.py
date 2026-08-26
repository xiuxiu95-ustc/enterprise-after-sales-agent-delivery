from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class SessionCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)


class ChatRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=8000)
    session_id: Optional[str] = None
    idempotency_key: Optional[str] = Field(default=None, max_length=128)


class AppointmentSlotsRequest(BaseModel):
    service_type: str = Field(min_length=1, max_length=64)
    issue_category: str = Field(min_length=1, max_length=128)
    start_time: str
    duration_minutes: int = Field(ge=30, le=480, multiple_of=30)
    engineer_name: Optional[str] = Field(default=None, max_length=128)
    required_skills: List[str] = Field(default_factory=list, max_length=20)
    location: Optional[str] = Field(default=None, max_length=256)
    contact: Optional[str] = Field(default=None, max_length=128)
    confirmation: bool = False

    @field_validator("start_time")
    @classmethod
    def validate_start_time(cls, value: str) -> str:
        datetime.strptime(value, "%Y-%m-%d %H:%M")
        return value


class AppointmentDraftRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    session_id: str
    message: str = Field(min_length=1, max_length=8000)


class AppointmentConfirmRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    session_id: str
    engineer_id: str
    slots: AppointmentSlotsRequest
    idempotency_key: str = Field(min_length=8, max_length=128)


class AppointmentCancelRequest(BaseModel):
    expected_version: int = Field(ge=1)


class AvailabilityRequest(BaseModel):
    slots: AppointmentSlotsRequest


class EngineerCreateRequest(BaseModel):
    employee_code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    skills: List[str] = Field(min_length=1, max_length=30)
    service_regions: List[str] = Field(default_factory=list, max_length=30)


class ShiftCreateRequest(BaseModel):
    start_time: datetime
    end_time: datetime
    capacity: int = Field(default=1, ge=1, le=10)


class BehaviorEventRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    session_id: Optional[str] = None
    event_type: str = Field(min_length=1, max_length=64)
    payload: Dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=8, max_length=128)


class KnowledgeQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=20)
    collection: Optional[str] = Field(default=None, max_length=128)


class AutoDreamRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    force: bool = False


class EvaluationRequest(BaseModel):
    layers: List[str] = Field(default_factory=lambda: ["routing", "slot", "trajectory", "safety"])

