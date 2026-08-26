from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Set

from agents.contracts import Actor


ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "customer": {
        "chat:write",
        "session:read",
        "appointment:read",
        "appointment:create",
        "appointment:cancel",
        "behavior:write",
        "memory:read:self",
    },
    "support": {
        "chat:write",
        "session:read",
        "appointment:read",
        "appointment:create",
        "appointment:cancel",
        "behavior:write",
        "memory:read",
        "trace:read",
    },
    "supervisor": {"*"},
    "admin": {"*"},
}


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    risk_level: str
    reason: str


class AuthorizationService:
    HIGH_RISK = {"engineer:write", "autodream:run", "audit:read", "eval:run"}
    CONFIRM_REQUIRED = {"appointment:create", "appointment:cancel"}

    def authorize(self, actor: Actor, permission: str) -> AuthorizationDecision:
        permissions = ROLE_PERMISSIONS.get(actor.role, set())
        allowed = "*" in permissions or permission in permissions
        risk = "high" if permission in self.HIGH_RISK else "medium" if permission in self.CONFIRM_REQUIRED else "low"
        if not allowed:
            return AuthorizationDecision(False, risk, "permission_denied")
        if permission in self.CONFIRM_REQUIRED and not actor.confirmed:
            return AuthorizationDecision(False, risk, "explicit_confirmation_required")
        return AuthorizationDecision(True, risk, "allowed")


class ToolPolicy:
    def __init__(self, allowed_tools: Iterable[str]):
        self.allowed_tools = set(allowed_tools)

    def require(self, tool_name: str) -> None:
        if tool_name not in self.allowed_tools:
            raise PermissionError("tool_not_whitelisted")

