"""Rank notes the caller already scoped to one person."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from hinga.embeddings import cosine

# Clear shared wording, not a near-miss. The local embedder's synonym lift is
# real but small, so a looser cutoff cites notes that only share one everyday word.
OVERLAP_THRESHOLD = 0.32


class Embedded(Protocol):
    id: str
    embedding_json: str
    embedding_space: str


@dataclass(frozen=True)
class Ranked:
    item_id: str
    overlap: float


def vector_of(raw: str) -> list[float]:
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [float(item) for item in data]


def rank(items: list[Embedded], query_vector: list[float], *, limit: int = 3) -> list[Ranked]:
    scored: list[Ranked] = []
    for item in items:
        overlap = cosine(query_vector, vector_of(item.embedding_json))
        if overlap >= OVERLAP_THRESHOLD:
            scored.append(Ranked(item_id=item.id, overlap=overlap))
    scored.sort(key=lambda row: row.overlap, reverse=True)
    return scored[:limit]
