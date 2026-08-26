from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from db.models import Memory, utcnow


def _tokens(text: str) -> List[str]:
    return [item.lower() for item in re.findall(r"[A-Za-z0-9_\-]+|[\u4e00-\u9fff]", text)]


def text_embedding(text: str, dimensions: int = 64) -> List[float]:
    vector = [0.0] * dimensions
    for token in _tokens(text):
        index = int(hashlib.sha256(token.encode("utf-8")).hexdigest()[:8], 16) % dimensions
        vector[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return max(0.0, sum(a * b for a, b in zip(left, right)))


@dataclass
class MemoryHit:
    memory_id: str
    memory_type: str
    content: str
    score: float
    semantic_score: float
    recency_score: float
    importance_score: float
    confidence: float


class MemoryService:
    """Long-term recall: semantic 0.6 + recency 0.3 + importance 0.1."""

    def __init__(self, db: Session):
        self.db = db

    def recall(self, user_id: str, query: str, top_k: int = 5, now: Optional[datetime] = None) -> List[MemoryHit]:
        now = now or utcnow()
        query_vector = text_embedding(query)
        candidates = (
            self.db.query(Memory)
            .filter(Memory.user_id == user_id, Memory.is_active.is_(True))
            .all()
        )
        hits: List[MemoryHit] = []
        for item in candidates:
            vector = item.embedding or text_embedding(item.content)
            semantic = cosine(query_vector, vector)
            age_days = max(0.0, (now - item.occurred_at).total_seconds() / 86400.0)
            recency = math.exp(-age_days / 30.0)
            importance = min(1.0, max(0.0, float(item.importance)))
            confidence = min(1.0, max(0.0, float(item.confidence)))
            score = (0.6 * semantic + 0.3 * recency + 0.1 * importance) * (0.7 + 0.3 * confidence)
            hits.append(
                MemoryHit(
                    memory_id=item.id,
                    memory_type=item.memory_type,
                    content=item.content,
                    score=round(score, 6),
                    semantic_score=round(semantic, 6),
                    recency_score=round(recency, 6),
                    importance_score=round(importance, 6),
                    confidence=round(confidence, 6),
                )
            )
        hits.sort(key=lambda hit: (-hit.score, hit.memory_id))
        selected = hits[: max(1, min(top_k, 20))]
        if selected:
            ids = [hit.memory_id for hit in selected]
            self.db.query(Memory).filter(Memory.id.in_(ids)).update(
                {Memory.last_accessed_at: now}, synchronize_session=False
            )
        return selected

