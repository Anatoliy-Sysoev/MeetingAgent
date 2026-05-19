from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class QHGateItem:
    code: str
    title: str
    status: str
    evidence: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "title": self.title,
            "status": self.status,
            "evidence": self.evidence,
        }


@dataclass(slots=True)
class QHGateResult:
    status: str
    items: list[QHGateItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "items": [item.to_dict() for item in self.items],
            "passed": [item.code for item in self.items if item.status == "passed"],
            "pending": [item.code for item in self.items if item.status == "pending"],
            "failed": [item.code for item in self.items if item.status == "failed"],
        }


def build_release_gate(*, local_validation_done: bool = False, baseline_compared: bool = False) -> QHGateResult:
    """Build QH-5 release gate status.

    This function intentionally separates code readiness from local validation.
    GitHub-only implementation can make QH-2..QH-4 code-ready, but QH-5 is not
    passed until local regression/smoke/eval are run on the workstation with data.
    """

    items = [
        QHGateItem("QH-1", "Observability + Eval Baseline implemented", "passed", "chat_runs + eval runner exist"),
        QHGateItem("QH-2", "Source Quality Filter implemented", "passed", "source_quality integrated into ContextBuilder"),
        QHGateItem("QH-3", "Parent Expansion implemented with limits", "passed", "ParentExpander integrated into ContextBuilder"),
        QHGateItem("QH-4", "Semantic Warnings / Manual Labels implemented", "passed", "warnings.semantic + chat_runs semantic_warnings"),
        QHGateItem(
            "QH-5A",
            "Local regression/smoke executed",
            "passed" if local_validation_done else "pending",
            "requires workstation with data/asu_june_bot and Ollama",
        ),
        QHGateItem(
            "QH-5B",
            "Baseline compared after QH-2/QH-3/QH-4",
            "passed" if baseline_compared else "pending",
            "run eval label after_qh and compare with baseline",
        ),
        QHGateItem("QH-5C", "Docs updated", "passed", "README/RUNBOOK/TODO/context updated"),
        QHGateItem("QH-5D", "Docker postponed until QH-5 passed", "passed", "ADR-020"),
    ]
    status = "passed" if all(item.status == "passed" for item in items) else "pending_local_validation"
    return QHGateResult(status=status, items=items)
