from __future__ import annotations

from typing import Generator, Optional

from fastapi import Header, HTTPException, Request
from sqlalchemy.orm import Session

from agents.contracts import Actor


def get_db(request: Request) -> Generator[Session, None, None]:
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


def get_actor(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_actor_id: Optional[str] = Header(default=None),
    x_role: Optional[str] = Header(default=None),
    x_confirm_token: Optional[str] = Header(default=None),
) -> Actor:
    settings = request.app.state.settings
    if settings.auth_required:
        expected = f"Bearer {settings.local_api_token}"
        if authorization != expected:
            raise HTTPException(status_code=401, detail="invalid_api_token")
    role = (x_role or "customer").lower()
    if role not in {"customer", "support", "supervisor", "admin"}:
        raise HTTPException(status_code=403, detail="invalid_role")
    return Actor(
        actor_id=x_actor_id or "local-user",
        role=role,
        confirmed=x_confirm_token == "confirmed",
    )


def require_user_scope(actor: Actor, user_id: str) -> None:
    if actor.role == "customer" and actor.actor_id not in {"local-user", user_id}:
        raise HTTPException(status_code=403, detail="cross_user_access_denied")

