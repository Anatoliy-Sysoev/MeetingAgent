from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from asu_june_bot.core.limits import MAX_QUERY_CHARS, validate_query_length


class ChatStatus(StrEnum):
    ANSWERED = "answered"
    REFUSED = "refused"
    CLARIFY = "clarify"
    NO_SOURCES = "no_sources"
    LLM_ERROR = "llm_error"
    LLM_EMPTY_RESPONSE = "llm_empty_response"
    VALIDATION_FAILED = "validation_failed"


@dataclass(slots=True)
class ChatRequest:
    query: str
    mode: str = "hybrid"
    top_k: int = 8
    include_source_types: list[str] | None = None
    model: str | None = None
    temperature: float = 0.0
    max_tokens: int = 900
    timeout_sec: int = 300
    include_diagnostics: bool = True
    max_query_chars: int = MAX_QUERY_CHARS

    def __post_init__(self) -> None:
        self.query = " ".join((self.query or "").split())
        if not self.query:
            raise ValueError("ChatRequest.query must not be empty")
        validate_query_length(self.query, max_chars=self.max_query_chars)
        if self.top_k < 1:
            raise ValueError("ChatRequest.top_k must be >= 1")


@dataclass(slots=True)
class ChatSource:
    source_ref: str
    source_id: str | None = None
    chunk_id: str | None = None
    title: str | None = None
    path: str | None = None
    section: str | None = None
    requirement_id: str | None = None
    source_type: str | None = None
    score: float | None = None
    text_preview: str | None = None
    bucket: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_ref": self.source_ref,
            "source_id": self.source_id,
            "chunk_id": self.chunk_id,
            "title": self.title,
            "path": self.path,
            "section": self.section,
            "requirement_id": self.requirement_id,
            "source_type": self.source_type,
            "score": self.score,
            "text_preview": self.text_preview,
            "bucket": self.bucket,
        }


@dataclass(slots=True)
class ChatResponse:
    status: str
    query: str
    answer: str | None = None
    sources: list[ChatSource] = field(default_factory=list)
    search: dict[str, Any] = field(default_factory=dict)
    warnings: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "query": self.query,
            "answer": self.answer,
            "sources": [source.to_dict() for source in self.sources],
            "search": self.search,
            "warnings": self.warnings,
            "diagnostics": self.diagnostics,
        }
