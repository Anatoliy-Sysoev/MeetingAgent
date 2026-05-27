from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from asu_june_bot.core.limits import MAX_QUERY_CHARS, validate_query_length


class SearchMode(StrEnum):
    HYBRID = "hybrid"
    VECTOR = "vector"
    BM25 = "bm25"


class SearchStatus(StrEnum):
    OK = "ok"
    REFUSED = "refused"
    CLARIFY = "clarify"
    ERROR = "error"


@dataclass(slots=True)
class SearchStageDiagnostic:
    name: str
    elapsed_ms: float
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "elapsed_ms": round(float(self.elapsed_ms), 3),
            "payload": self.payload,
        }


@dataclass(slots=True)
class SearchDiagnostics:
    stages: list[SearchStageDiagnostic] = field(default_factory=list)
    total_elapsed_ms: float = 0.0
    retrieval_called: bool = False

    def add_stage(self, name: str, elapsed_ms: float, payload: dict[str, Any] | None = None) -> None:
        self.stages.append(SearchStageDiagnostic(name=name, elapsed_ms=elapsed_ms, payload=payload or {}))
        self.total_elapsed_ms = round(sum(stage.elapsed_ms for stage in self.stages), 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_elapsed_ms": round(float(self.total_elapsed_ms), 3),
            "retrieval_called": self.retrieval_called,
            "stages": [stage.to_dict() for stage in self.stages],
        }


@dataclass(slots=True)
class SearchRequest:
    query: str
    mode: str = SearchMode.HYBRID.value
    top_k: int = 10
    chunks_path: str | None = None
    index_dir: str | None = None
    include_source_types: list[str] | None = None
    no_guard: bool = False
    include_diagnostics: bool = True
    max_query_chars: int = MAX_QUERY_CHARS

    def __post_init__(self) -> None:
        self.query = " ".join((self.query or "").split())
        if not self.query:
            raise ValueError("SearchRequest.query must not be empty")
        validate_query_length(self.query, max_chars=self.max_query_chars)
        if self.mode not in {item.value for item in SearchMode}:
            raise ValueError(f"Unsupported search mode: {self.mode}")
        if self.top_k < 1:
            raise ValueError("SearchRequest.top_k must be >= 1")


@dataclass(slots=True)
class SearchResponse:
    payload: dict[str, Any]

    @property
    def status(self) -> str:
        return str(self.payload.get("status") or SearchStatus.OK.value)

    @property
    def results(self) -> list[dict[str, Any]]:
        return list(self.payload.get("results") or [])

    @property
    def context(self) -> dict[str, Any]:
        return dict(self.payload.get("context") or {})

    @property
    def guard(self) -> dict[str, Any]:
        return dict(self.payload.get("guard") or {})

    def to_dict(self) -> dict[str, Any]:
        return self.payload


def empty_context() -> dict[str, Any]:
    return {"primary_sources": [], "supporting_sources": [], "excluded_sources": [], "diagnostics": {}}
