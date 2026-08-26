from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from agents.contracts import Actor
from api.dependencies import get_actor, get_db, require_user_scope
from api.schemas import (
    AppointmentCancelRequest,
    AppointmentConfirmRequest,
    AppointmentDraftRequest,
    AutoDreamRequest,
    AvailabilityRequest,
    BehaviorEventRequest,
    ChatRequest,
    EngineerCreateRequest,
    EvaluationRequest,
    KnowledgeQueryRequest,
    SessionCreate,
    ShiftCreateRequest,
)
from db.models import (
    Appointment,
    AuditLog,
    BehaviorEvent,
    Engineer,
    EngineerShift,
    EvaluationFailure,
    Handoff,
    Invocation,
    InvocationEvent,
    Trace,
    TraceSpan,
    UserPreference,
)
from db.repositories import AppointmentRepository, AuditRepository, BehaviorRepository, SessionRepository
from evaluation.runner import EvaluationRunner
from services.appointment import AppointmentService
from services.autodream import AutoDreamService
from services.memory import MemoryService, text_embedding
from services.orchestrator import AgentOrchestrator, ChatCommand
from services.rag import RagGateway
from services.security import AuthorizationService
from services.slot_extraction import AppointmentSlots, SlotExtractorAdapter


router = APIRouter(prefix="/api/v1")


def _iso(value: Any) -> Any:
    return value.isoformat() + "Z" if hasattr(value, "isoformat") and value is not None else value


def _appointment(item: Appointment) -> Dict[str, Any]:
    return {
        "id": item.id, "user_id": item.user_id, "session_id": item.session_id,
        "engineer_id": item.engineer_id, "service_type": item.service_type,
        "issue_category": item.issue_category, "start_time": _iso(item.start_time),
        "end_time": _iso(item.end_time), "status": item.status, "version": item.version,
        "created_at": _iso(item.created_at),
    }


def _authorize(db: Session, actor: Actor, permission: str) -> None:
    decision = AuthorizationService().authorize(actor, permission)
    AuditRepository(db).record(
        actor.actor_id,
        actor.role,
        "authorization.check",
        "permission",
        "allowed" if decision.allowed else "denied",
        decision.risk_level,
        {"permission": permission, "reason": decision.reason},
        resource_id=permission,
    )
    db.commit()
    if not decision.allowed:
        raise HTTPException(status_code=403, detail=decision.reason)


@router.get("/health", tags=["system"])
def health(request: Request, db: Session = Depends(get_db)) -> Dict[str, Any]:
    active_invocations = db.query(Invocation).filter(Invocation.status == "active").count()
    orphan_handoffs = db.query(Handoff).filter(Handoff.status.in_(["pending", "started"])).count()
    incomplete_traces = db.query(Trace).filter(Trace.incomplete.is_(True)).count()
    return {
        "status": "degraded" if orphan_handoffs else "ok",
        "version": request.app.state.settings.version,
        "storage": "sqlite",
        "active_invocations": active_invocations,
        "orphan_handoffs": orphan_handoffs,
        "incomplete_traces": incomplete_traces,
    }


@router.post("/sessions", tags=["sessions"])
def create_session(payload: SessionCreate, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)) -> Dict[str, Any]:
    require_user_scope(actor, payload.user_id)
    item = SessionRepository(db).create(payload.user_id)
    db.commit()
    return {"id": item.id, "user_id": item.user_id, "status": item.status}


@router.get("/sessions/{session_id}", tags=["sessions"])
def get_session(session_id: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)) -> Dict[str, Any]:
    item = SessionRepository(db).require(session_id)
    require_user_scope(actor, item.user_id)
    return {
        "id": item.id, "user_id": item.user_id, "status": item.status,
        "message_count": item.message_count, "completed_turns": item.completed_turns,
        "summary_generation": item.summary_generation, "slot_state": item.slot_state,
    }


@router.post("/sessions/{session_id}/close", tags=["sessions"])
def close_session(session_id: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)) -> Dict[str, Any]:
    item = SessionRepository(db).require(session_id)
    require_user_scope(actor, item.user_id)
    item = SessionRepository(db).close(session_id)
    db.commit()
    return {"id": item.id, "status": item.status, "closed_at": _iso(item.closed_at)}


@router.get("/sessions/{session_id}/messages", tags=["sessions"])
def list_messages(session_id: str, limit: int = Query(default=50, ge=1, le=200), actor: Actor = Depends(get_actor), db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    session = SessionRepository(db).require(session_id)
    require_user_scope(actor, session.user_id)
    return [
        {"id": item.id, "role": item.role, "content": item.content, "token_count": item.token_count, "created_at": _iso(item.created_at)}
        for item in SessionRepository(db).list_messages(session_id, limit)
    ]


@router.post("/chat", tags=["agents"])
async def chat(payload: ChatRequest, request: Request, actor: Actor = Depends(get_actor)) -> Dict[str, Any]:
    require_user_scope(actor, payload.user_id)
    orchestrator = AgentOrchestrator(request.app.state.session_factory, request.app.state.settings)
    return await orchestrator.run(ChatCommand(**payload.model_dump()), actor)


@router.post("/chat/stream", tags=["agents"])
async def chat_stream(payload: ChatRequest, request: Request, actor: Actor = Depends(get_actor)) -> StreamingResponse:
    require_user_scope(actor, payload.user_id)
    orchestrator = AgentOrchestrator(request.app.state.session_factory, request.app.state.settings)

    async def generate():
        async for item in orchestrator.stream(ChatCommand(**payload.model_dump()), actor):
            data = json.dumps(item["data"], ensure_ascii=False, separators=(",", ":"))
            yield f"id: {item['id']}\nevent: {item['event']}\ndata: {data}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/consultations", tags=["agents"])
async def consultation(payload: ChatRequest, request: Request, actor: Actor = Depends(get_actor)) -> Dict[str, Any]:
    require_user_scope(actor, payload.user_id)
    command = ChatCommand(**payload.model_dump())
    return await AgentOrchestrator(request.app.state.session_factory, request.app.state.settings).run(command, actor)


@router.post("/appointments/drafts", tags=["appointments"])
def appointment_draft(payload: AppointmentDraftRequest, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)) -> Dict[str, Any]:
    require_user_scope(actor, payload.user_id)
    session = SessionRepository(db).require(payload.session_id)
    slots = SlotExtractorAdapter(request.app.state.settings).extract(payload.message, session.slot_state or {})
    state = "collecting" if slots.missing_info else "confirmed" if slots.confirmation else "awaiting_confirmation"
    session.slot_state = {**asdict(slots), "state": state}
    db.commit()
    return {"state": state, "slots": asdict(slots)}


@router.post("/appointments/confirm", tags=["appointments"])
def appointment_confirm(payload: AppointmentConfirmRequest, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)) -> Dict[str, Any]:
    require_user_scope(actor, payload.user_id)
    slots = AppointmentSlots(**payload.slots.model_dump()).finalize_missing()
    if slots.missing_info or not slots.confirmation:
        raise HTTPException(status_code=409, detail="appointment_not_ready_for_confirmation")
    confirmed_actor = Actor(actor.actor_id, actor.role, True)
    try:
        item, created = AppointmentService(db).create(confirmed_actor, payload.user_id, payload.session_id, slots, payload.engineer_id, payload.idempotency_key)
        db.commit()
    except (ValueError, PermissionError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"appointment": _appointment(item), "created": created}


@router.get("/appointments", tags=["appointments"])
def list_appointments(user_id: str, status: Optional[str] = None, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    require_user_scope(actor, user_id)
    query = db.query(Appointment).filter(Appointment.user_id == user_id)
    if status:
        query = query.filter(Appointment.status == status)
    return [_appointment(item) for item in query.order_by(Appointment.created_at.desc()).limit(200).all()]


@router.get("/appointments/{appointment_id}", tags=["appointments"])
def get_appointment(appointment_id: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)) -> Dict[str, Any]:
    item = db.get(Appointment, appointment_id)
    if item is None:
        raise HTTPException(status_code=404, detail="appointment_not_found")
    require_user_scope(actor, item.user_id)
    return _appointment(item)


@router.post("/appointments/{appointment_id}/cancel", tags=["appointments"])
def cancel_appointment(appointment_id: str, payload: AppointmentCancelRequest, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)) -> Dict[str, Any]:
    item = db.get(Appointment, appointment_id)
    if item is None:
        raise HTTPException(status_code=404, detail="appointment_not_found")
    require_user_scope(actor, item.user_id)
    try:
        item = AppointmentService(db).cancel(actor, appointment_id, payload.expected_version)
        db.commit()
    except (ValueError, PermissionError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _appointment(item)


@router.post("/availability/search", tags=["appointments"])
def search_availability(payload: AvailabilityRequest, db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    slots = AppointmentSlots(**payload.slots.model_dump()).finalize_missing()
    if slots.missing_info:
        raise HTTPException(status_code=422, detail={"missing_info": slots.missing_info})
    return [asdict(item) for item in AppointmentService(db).match_engineers(slots)]


@router.get("/engineers", tags=["engineers"])
def list_engineers(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    return [{"id": item.id, "employee_code": item.employee_code, "name": item.name, "skills": item.skills, "service_regions": item.service_regions, "active": item.active} for item in db.query(Engineer).order_by(Engineer.employee_code).all()]


@router.post("/engineers", tags=["engineers"])
def create_engineer(payload: EngineerCreateRequest, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)) -> Dict[str, Any]:
    _authorize(db, actor, "engineer:write")
    item = Engineer(**payload.model_dump(), skill_embedding=text_embedding(" ".join(payload.skills)))
    db.add(item)
    db.commit()
    return {"id": item.id, "employee_code": item.employee_code, "name": item.name}


@router.post("/engineers/{engineer_id}/shifts", tags=["engineers"])
def create_shift(engineer_id: str, payload: ShiftCreateRequest, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)) -> Dict[str, Any]:
    _authorize(db, actor, "engineer:write")
    if payload.end_time <= payload.start_time:
        raise HTTPException(status_code=422, detail="shift_end_must_follow_start")
    if db.get(Engineer, engineer_id) is None:
        raise HTTPException(status_code=404, detail="engineer_not_found")
    item = EngineerShift(engineer_id=engineer_id, **payload.model_dump())
    db.add(item)
    db.commit()
    return {"id": item.id, "engineer_id": item.engineer_id}


@router.post("/behavior/events", tags=["behavior"])
def record_behavior(payload: BehaviorEventRequest, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)) -> Dict[str, Any]:
    require_user_scope(actor, payload.user_id)
    item, created = BehaviorRepository(db).record(**payload.model_dump())
    db.commit()
    return {"id": item.id, "created": created}


@router.get("/behavior/users/{user_id}/profile", tags=["behavior"])
def user_profile(user_id: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)) -> Dict[str, Any]:
    require_user_scope(actor, user_id)
    rows = db.query(UserPreference).filter(UserPreference.user_id == user_id).order_by(UserPreference.confidence.desc()).all()
    return {"user_id": user_id, "preferences": [{"key": row.preference_key, "value": row.preference_value, "confidence": row.confidence, "evidence_count": row.evidence_count, "conflict_score": row.conflict_score} for row in rows]}


@router.get("/memory/users/{user_id}/recall", tags=["memory"])
def recall_memory(user_id: str, query: str, top_k: int = Query(default=5, ge=1, le=20), actor: Actor = Depends(get_actor), db: Session = Depends(get_db)) -> Dict[str, Any]:
    require_user_scope(actor, user_id)
    hits = MemoryService(db).recall(user_id, query, top_k)
    db.commit()
    return {"user_id": user_id, "formula": "semantic*0.6+recency*0.3+importance*0.1", "hits": [asdict(hit) for hit in hits]}


@router.post("/memory/autodream/run", tags=["memory"])
def run_autodream(payload: AutoDreamRequest, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)) -> Dict[str, Any]:
    _authorize(db, actor, "autodream:run")
    result = AutoDreamService(db, request.app.state.settings).run(payload.user_id, payload.force)
    db.commit()
    return asdict(result)


@router.post("/knowledge/query", tags=["knowledge"])
async def knowledge_query(payload: KnowledgeQueryRequest, request: Request, db: Session = Depends(get_db)) -> Dict[str, Any]:
    result = await RagGateway(db, request.app.state.settings).query(payload.query, payload.top_k, payload.collection)
    return {"context": result.answer_context, "citations": [asdict(item) for item in result.citations], "candidate_count": result.candidate_count, "rank_changes": result.rank_changes, "source": result.source, "degraded": result.degraded}


@router.get("/knowledge/collections", tags=["knowledge"])
async def knowledge_collections(request: Request, db: Session = Depends(get_db)) -> Dict[str, Any]:
    return await RagGateway(db, request.app.state.settings).list_collections()


@router.get("/knowledge/documents/{document_id}/summary", tags=["knowledge"])
async def knowledge_document_summary(document_id: str, request: Request, db: Session = Depends(get_db)) -> Dict[str, Any]:
    return await RagGateway(db, request.app.state.settings).document_summary(document_id)


@router.get("/handoffs/{handoff_id}", tags=["observability"])
def get_handoff(handoff_id: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)) -> Dict[str, Any]:
    _authorize(db, actor, "trace:read")
    item = db.get(Handoff, handoff_id)
    if item is None:
        raise HTTPException(status_code=404, detail="handoff_not_found")
    return {"id": item.id, "source_invocation_id": item.source_invocation_id, "target_invocation_id": item.target_invocation_id, "from_agent": item.from_agent, "to_agent": item.to_agent, "intent": item.intent, "status": item.status, "packet": item.packet, "failure_code": item.failure_code}


@router.get("/traces/{trace_id}", tags=["observability"])
def get_trace(trace_id: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)) -> Dict[str, Any]:
    _authorize(db, actor, "trace:read")
    trace = db.get(Trace, trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="trace_not_found")
    invocations = db.query(Invocation).filter(Invocation.trace_id == trace_id).all()
    ids = [item.id for item in invocations]
    events = db.query(InvocationEvent).filter(InvocationEvent.invocation_id.in_(ids)).order_by(InvocationEvent.created_at).all() if ids else []
    spans = db.query(TraceSpan).filter(TraceSpan.trace_id == trace_id).all()
    return {
        "trace": {"id": trace.id, "status": trace.status, "duration_ms": trace.duration_ms, "input_tokens": trace.input_tokens, "output_tokens": trace.output_tokens, "candidate_count": trace.candidate_count, "rank_changes": trace.rank_changes, "agent_steps": trace.agent_steps, "incomplete": trace.incomplete, "error_code": trace.error_code},
        "invocations": [{"id": item.id, "agent": item.agent_name, "phase": item.phase, "status": item.status, "error_code": item.error_code} for item in invocations],
        "events": [{"invocation_id": item.invocation_id, "sequence": item.sequence, "type": item.event_type, "payload": item.payload} for item in events],
        "spans": [{"name": item.name, "status": item.status, "duration_ms": item.duration_ms, "attributes": item.attributes} for item in spans],
    }


@router.get("/audit", tags=["observability"])
def list_audit(limit: int = Query(default=100, ge=1, le=500), actor: Actor = Depends(get_actor), db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    _authorize(db, actor, "audit:read")
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()
    return [{"id": row.id, "actor_id": row.actor_id, "actor_role": row.actor_role, "action": row.action, "resource_type": row.resource_type, "resource_id": row.resource_id, "decision": row.decision, "risk_level": row.risk_level, "payload": row.payload, "trace_id": row.trace_id, "created_at": _iso(row.created_at)} for row in rows]


@router.post("/evaluations/run", tags=["evaluation"])
def run_evaluations(payload: EvaluationRequest, request: Request, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)) -> Dict[str, Any]:
    _authorize(db, actor, "eval:run")
    return EvaluationRunner(request.app.state.settings, db).run(payload.layers)


@router.get("/evaluations/failures", tags=["evaluation"])
def evaluation_failures(layer: Optional[str] = None, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    _authorize(db, actor, "eval:run")
    query = db.query(EvaluationFailure)
    if layer:
        query = query.filter(EvaluationFailure.layer == layer)
    return [{"case_id": row.case_id, "layer": row.layer, "expected": row.expected, "actual": row.actual, "occurrences": row.occurrences, "trace_id": row.trace_id} for row in query.order_by(EvaluationFailure.last_seen_at.desc()).limit(500).all()]
