from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .models import ChatSource


INSUFFICIENT_DATA_MARKER = "В переданных источниках данных недостаточно для ответа"
SOURCE_REF_RE = re.compile(r"\[S\d+")


@dataclass(slots=True)
class SemanticWarning:
    code: str
    message: str
    severity: str = "warning"
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "details": self.details or {},
        }


class SemanticWarningAnalyzer:
    """Warning-only semantic risk layer.

    This is not a factual validator and must not hard-fail the answer.
    It emits diagnostics for manual review and future dataset accumulation.
    """

    def analyze(
        self,
        *,
        answer: str | None,
        sources: list[ChatSource],
        search_payload: dict[str, Any],
        diagnostics: dict[str, Any],
    ) -> list[SemanticWarning]:
        warnings: list[SemanticWarning] = []
        answer_text = answer or ""
        context_diag = ((search_payload.get("context") or {}).get("diagnostics") or {}) if isinstance(search_payload, dict) else {}
        source_quality_diag = context_diag.get("source_quality_filter") if isinstance(context_diag, dict) else None
        parent_diag = context_diag.get("parent_expansion") if isinstance(context_diag, dict) else None

        if source_quality_diag:
            result_quality = source_quality_diag.get("results") or {}
            weak_count = int(result_quality.get("weak_count") or 0)
            if weak_count:
                warnings.append(
                    SemanticWarning(
                        code="weak_sources_present",
                        message="В контексте есть слабые источники; ответ требует ручной проверки доказательности.",
                        details={"weak_count": weak_count, "weak_reasons": result_quality.get("weak_reasons") or {}},
                    )
                )
            if source_quality_diag.get("primary_fallback_weak"):
                warnings.append(
                    SemanticWarning(
                        code="weak_primary_fallback",
                        message="Primary source выбран из слабых источников из-за отсутствия более сильного контекста.",
                        severity="high",
                        details=source_quality_diag,
                    )
                )

        if parent_diag and isinstance(parent_diag, dict):
            primary_expanded = ((parent_diag.get("primary") or {}).get("expanded_count") or 0)
            supporting_expanded = ((parent_diag.get("supporting") or {}).get("expanded_count") or 0)
            if primary_expanded or supporting_expanded:
                warnings.append(
                    SemanticWarning(
                        code="parent_expansion_applied",
                        message="К части источников добавлен соседний/родительский контекст; нужно проверить, что ответ не смешал разные фрагменты.",
                        details={"primary_expanded": primary_expanded, "supporting_expanded": supporting_expanded},
                    )
                )

        if sources and len(sources) < 2 and INSUFFICIENT_DATA_MARKER not in answer_text:
            warnings.append(
                SemanticWarning(
                    code="low_source_count",
                    message="Ответ построен по одному источнику; для обзорных выводов может потребоваться дополнительная проверка.",
                    details={"source_count": len(sources)},
                )
            )

        citation_count = len(SOURCE_REF_RE.findall(answer_text))
        if answer_text and sources and citation_count < len(sources) and INSUFFICIENT_DATA_MARKER not in answer_text:
            warnings.append(
                SemanticWarning(
                    code="low_citation_coverage",
                    message="Не все выбранные источники явно процитированы в ответе.",
                    details={"citation_count": citation_count, "source_count": len(sources)},
                )
            )

        validation_errors = diagnostics.get("validation_errors") or []
        if validation_errors:
            warnings.append(
                SemanticWarning(
                    code="structural_validation_errors",
                    message="Structural validator обнаружил ошибки. Ответ не должен считаться надежным без исправления.",
                    severity="high",
                    details={"validation_errors": validation_errors},
                )
            )

        return warnings


def semantic_warnings_to_payload(warnings: list[SemanticWarning]) -> dict[str, Any]:
    return {
        "items": [warning.to_dict() for warning in warnings],
        "count": len(warnings),
        "has_high": any(warning.severity == "high" for warning in warnings),
    }
