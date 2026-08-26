from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Tuple

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _component_path(env_name: str, relative_default: str) -> str:
    configured = Path(os.getenv(env_name, relative_default)).expanduser()
    if not configured.is_absolute():
        configured = PROJECT_ROOT / configured
    return str(configured.resolve())


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


def _csv(name: str, default: str) -> Tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    app_name: str = "企业售后智能客服与预约 Agent 系统"
    version: str = "2.0.0"
    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "local"))
    host: str = field(default_factory=lambda: os.getenv("HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8001")))
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL", "sqlite:///./data/enterprise_after_sales.db"
        )
    )
    auth_required: bool = field(default_factory=lambda: _bool("AUTH_REQUIRED", False))
    local_api_token: str = field(default_factory=lambda: os.getenv("LOCAL_API_TOKEN", "local-dev-token"))
    allowed_origins: Tuple[str, ...] = field(
        default_factory=lambda: _csv(
            "ALLOWED_ORIGINS", "http://127.0.0.1:8001,http://localhost:8001"
        )
    )
    max_agent_steps: int = field(default_factory=lambda: int(os.getenv("MAX_AGENT_STEPS", "6")))
    context_window_tokens: int = field(
        default_factory=lambda: int(os.getenv("CONTEXT_WINDOW_TOKENS", "8000"))
    )
    context_summary_ratio: float = field(
        default_factory=lambda: float(os.getenv("CONTEXT_SUMMARY_RATIO", "0.60"))
    )
    recent_message_limit: int = field(
        default_factory=lambda: int(os.getenv("RECENT_MESSAGE_LIMIT", "10"))
    )
    slot_extractor_repo: str = field(
        default_factory=lambda: _component_path(
            "SLOT_EXTRACTOR_REPO", "packages/slot_extractor"
        )
    )
    slot_backend_config: str = field(
        default_factory=lambda: os.getenv("SLOT_EXTRACTOR_BACKEND_CONFIG", "")
    )
    rag_mode: str = field(default_factory=lambda: os.getenv("RAG_MODE", "local").lower())
    rag_mcp_repo: str = field(
        default_factory=lambda: _component_path(
            "RAG_MCP_REPO", "packages/modular_rag_mcp"
        )
    )
    rag_collection: str = field(
        default_factory=lambda: os.getenv("RAG_COLLECTION", "enterprise_after_sales")
    )
    autodream_min_closed_sessions: int = field(
        default_factory=lambda: int(os.getenv("AUTODREAM_MIN_CLOSED_SESSIONS", "5"))
    )
    autodream_min_interval_hours: int = field(
        default_factory=lambda: int(os.getenv("AUTODREAM_MIN_INTERVAL_HOURS", "24"))
    )
    autodream_lock_seconds: int = field(
        default_factory=lambda: int(os.getenv("AUTODREAM_LOCK_SECONDS", "300"))
    )
    allowed_tools: Tuple[str, ...] = (
        "memory_recall",
        "query_knowledge_hub",
        "list_collections",
        "get_document_summary",
        "extract_appointment_slots",
        "find_available_engineers",
        "create_appointment",
        "record_behavior",
    )

    def validate(self) -> None:
        if self.host not in {"127.0.0.1", "localhost", "::1"} and self.app_env == "local":
            raise ValueError("local mode must bind to a loopback address")
        if not 0.1 <= self.context_summary_ratio <= 0.9:
            raise ValueError("CONTEXT_SUMMARY_RATIO must be between 0.1 and 0.9")
        if self.max_agent_steps < 1 or self.max_agent_steps > 12:
            raise ValueError("MAX_AGENT_STEPS must be between 1 and 12")
        if self.auth_required and self.local_api_token in {"", "local-dev-token", "replace-in-production"}:
            raise ValueError("AUTH_REQUIRED needs a non-default LOCAL_API_TOKEN")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.validate()
    return settings
