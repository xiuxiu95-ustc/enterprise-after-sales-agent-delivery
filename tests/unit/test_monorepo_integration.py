from pathlib import Path

import pytest

from config.settings import Settings
from scripts.verify_repository import verify


@pytest.mark.unit
def test_component_defaults_resolve_inside_repository(monkeypatch):
    monkeypatch.delenv("SLOT_EXTRACTOR_REPO", raising=False)
    monkeypatch.delenv("RAG_MCP_REPO", raising=False)
    settings = Settings()
    root = Path(__file__).resolve().parents[2]

    assert Path(settings.slot_extractor_repo) == root / "packages" / "slot_extractor"
    assert Path(settings.rag_mcp_repo) == root / "packages" / "modular_rag_mcp"


@pytest.mark.unit
def test_integrated_repository_contract_is_clean():
    assert verify() == []
