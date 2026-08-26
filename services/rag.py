from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from config.settings import Settings
from db.models import KnowledgeDocument
from db.repositories import KnowledgeRepository


@dataclass
class Citation:
    source_id: str
    title: str
    uri: str
    score: float


@dataclass
class RagResult:
    answer_context: str
    citations: List[Citation] = field(default_factory=list)
    candidate_count: int = 0
    rank_changes: List[Dict[str, Any]] = field(default_factory=list)
    degraded: bool = False
    source: str = "mcp"


class RagGateway:
    """Three-tool adapter for MODULAR-RAG-MCP-SERVER-main."""

    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    async def query(self, query: str, top_k: int = 5, collection: Optional[str] = None) -> RagResult:
        mode = self.settings.rag_mode
        if mode == "local":
            return self._query_local(query, top_k, collection)
        if mode == "inprocess":
            return await self._query_inprocess(query, top_k, collection)
        if mode == "mcp":
            return await self._call_mcp("query_knowledge_hub", {"query": query, "top_k": top_k, "collection": collection or self.settings.rag_collection})
        raise ValueError("unsupported_rag_mode")

    async def list_collections(self) -> Dict[str, Any]:
        if self.settings.rag_mode == "mcp":
            result = await self._call_mcp_raw("list_collections", {})
            return {"source": "mcp", "content": result}
        rows = self.db.query(KnowledgeDocument.collection).distinct().all()
        return {"source": "local", "collections": [row[0] for row in rows]}

    async def document_summary(self, document_id: str) -> Dict[str, Any]:
        if self.settings.rag_mode == "mcp":
            result = await self._call_mcp_raw(
                "get_document_summary",
                {"doc_id": document_id, "collection": self.settings.rag_collection},
            )
            return {"source": "mcp", "content": result}
        doc = self.db.get(KnowledgeDocument, document_id)
        if doc is None:
            raise LookupError("knowledge_document_not_found")
        return {"source": "local", "title": doc.title, "summary": doc.content[:500], "uri": doc.source_uri}

    def _query_local(self, query: str, top_k: int, collection: Optional[str]) -> RagResult:
        rows = KnowledgeRepository(self.db).search_local(query, collection or self.settings.rag_collection, top_k)
        citations = [Citation(doc.id, doc.title, doc.source_uri, score) for doc, score in rows]
        context = "\n\n".join(f"[{doc.title}] {doc.content}" for doc, _score in rows)
        return RagResult(
            answer_context=context,
            citations=citations,
            candidate_count=len(rows),
            degraded=True,
            source="local_development_fallback",
        )

    async def _query_inprocess(self, query: str, top_k: int, collection: Optional[str]) -> RagResult:
        repo = Path(self.settings.rag_mcp_repo)
        if not repo.exists():
            raise RuntimeError("rag_mcp_repo_not_found")
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))
        from src.mcp_server.tools.query_knowledge_hub import QueryKnowledgeHubTool

        response = await QueryKnowledgeHubTool().execute(query=query, top_k=top_k, collection=collection or self.settings.rag_collection)
        citations = []
        for item in response.citations:
            data = item if isinstance(item, dict) else getattr(item, "__dict__", {})
            citations.append(
                Citation(
                    str(data.get("chunk_id") or data.get("source_id") or data.get("id") or "unknown"),
                    str(data.get("title") or data.get("source") or "knowledge"),
                    str(data.get("source_path") or data.get("uri") or ""),
                    float(data.get("score") or 0.0),
                )
            )
        metadata = response.metadata or {}
        return RagResult(
            answer_context=response.content,
            citations=citations,
            candidate_count=len(metadata.get("final_results", citations)),
            rank_changes=metadata.get("rank_changes", []),
            degraded=False,
            source="modular_rag_inprocess_adapter",
        )

    async def _call_mcp(self, tool_name: str, arguments: Dict[str, Any]) -> RagResult:
        result = await self._call_mcp_raw(tool_name, arguments)
        text = result.get("text", "")
        structured = result.get("structured", {})
        citations = [
            Citation(
                str(item.get("chunk_id") or item.get("id") or "unknown"),
                str(item.get("title") or item.get("source") or "knowledge"),
                str(item.get("uri") or item.get("source_path") or ""),
                float(item.get("score") or 0.0),
            )
            for item in structured.get("citations", [])
        ]
        return RagResult(
            answer_context=text,
            citations=citations,
            candidate_count=int(structured.get("candidate_count", len(citations))),
            rank_changes=list(structured.get("rank_changes", [])),
            degraded=False,
            source="modular_rag_mcp",
        )

    async def _call_mcp_raw(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        repo = Path(self.settings.rag_mcp_repo)
        if not repo.exists():
            raise RuntimeError("rag_mcp_repo_not_found")
        env = dict(os.environ)
        env["PYTHONPATH"] = str(repo) + os.pathsep + env.get("PYTHONPATH", "")
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(repo / "main.py")],
            env=env,
            cwd=str(repo),
        )
        async with stdio_client(params) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                response = await session.call_tool(tool_name, arguments)
        text_parts = [getattr(block, "text", "") for block in response.content if getattr(block, "type", "") == "text"]
        return {
            "text": "\n".join(text_parts),
            "structured": (
                getattr(response, "structuredContent", None)
                or getattr(response, "structured_content", None)
                or {}
            ),
            "is_error": bool(getattr(response, "isError", False)),
        }
