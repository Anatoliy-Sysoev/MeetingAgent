from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SearchQuery:
    query: str
    top_k: int = 10
    filters: dict[str, Any] = field(default_factory=dict)
    include_source_types: list[str] | None = None
    exclude_source_types: list[str] | None = None


@dataclass(slots=True)
class SearchResult:
    source_id: str
    text: str
    score: float
    vector_score: float | None
    bm25_score: float | None
    metadata: dict[str, Any]
    matched_by: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, preview_chars: int = 600) -> dict[str, Any]:
        text_preview = " ".join(self.text.split())
        if len(text_preview) > preview_chars:
            text_preview = text_preview[: preview_chars - 1].rstrip() + "…"
        return {
            "source_id": self.source_id,
            "score": round(float(self.score), 6),
            "vector_score": None if self.vector_score is None else round(float(self.vector_score), 6),
            "bm25_score": None if self.bm25_score is None else round(float(self.bm25_score), 6),
            "matched_by": self.matched_by,
            "document": self.metadata.get("relative_path"),
            "document_type": self.metadata.get("document_type"),
            "source_type": self.metadata.get("source_type"),
            "module": self.metadata.get("module"),
            "stage": self.metadata.get("stage"),
            "section": self.metadata.get("section"),
            "sections": self.metadata.get("sections"),
            "title": self.metadata.get("title"),
            "chunk_index": self.metadata.get("chunk_index"),
            "chunk_id": self.metadata.get("chunk_id"),
            "text_preview": text_preview,
            "diagnostics": self.diagnostics,
            "metadata": self.metadata,
        }
