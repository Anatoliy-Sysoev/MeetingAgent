from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class EvalCase:
    case_id: str
    query: str
    expected_status: str
    expected_llm_called: bool
    category: str = "uncategorized"
    priority: str = "medium"
    expected_citation_required: bool = False
    expected_min_sources: int | None = None
    must_include: list[str] = field(default_factory=list)
    must_not_include: list[str] = field(default_factory=list)
    expected_source_title_contains: list[str] = field(default_factory=list)
    golden_answer_path: str | None = None
    from_log_run_id: str | None = None
    notes: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvalCase":
        return cls(
            case_id=str(data["case_id"]),
            query=str(data["query"]),
            expected_status=str(data["expected_status"]),
            expected_llm_called=bool(data["expected_llm_called"]),
            category=str(data.get("category") or "uncategorized"),
            priority=str(data.get("priority") or "medium"),
            expected_citation_required=bool(data.get("expected_citation_required", False)),
            expected_min_sources=data.get("expected_min_sources"),
            must_include=list(data.get("must_include") or []),
            must_not_include=list(data.get("must_not_include") or []),
            expected_source_title_contains=list(data.get("expected_source_title_contains") or []),
            golden_answer_path=data.get("golden_answer_path"),
            from_log_run_id=data.get("from_log_run_id"),
            notes=data.get("notes"),
        )


@dataclass(slots=True)
class CheckResult:
    name: str
    passed: bool
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(slots=True)
class EvalResult:
    case_id: str
    category: str
    priority: str
    query: str
    expected_status: str
    actual_status: str
    passed: bool
    checks: list[CheckResult]
    answer_preview: str | None = None
    sources: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    latency_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "priority": self.priority,
            "query": self.query,
            "expected_status": self.expected_status,
            "actual_status": self.actual_status,
            "passed": self.passed,
            "checks": [check.to_dict() for check in self.checks],
            "answer_preview": self.answer_preview,
            "sources": self.sources,
            "diagnostics": self.diagnostics,
            "latency_ms": self.latency_ms,
        }


@dataclass(slots=True)
class EvalReport:
    results: list[EvalResult]
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for result in self.results if result.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "summary": {
                "total": self.total,
                "passed": self.passed,
                "failed": self.failed,
                "pass_rate": round(self.pass_rate, 4),
                "by_category": self._by_field("category"),
                "by_priority": self._by_field("priority"),
            },
            "results": [result.to_dict() for result in self.results],
        }

    def _by_field(self, field_name: str) -> dict[str, dict[str, Any]]:
        groups: dict[str, list[EvalResult]] = {}
        for result in self.results:
            key = getattr(result, field_name)
            groups.setdefault(key, []).append(result)
        return {
            key: {
                "total": len(items),
                "passed": sum(1 for item in items if item.passed),
                "failed": sum(1 for item in items if not item.passed),
            }
            for key, items in sorted(groups.items())
        }
