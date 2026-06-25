from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Labels that are exported by default (omits "correct" which floods the file).
_DEFAULT_EXPORT_LABELS: frozenset[str] = frozenset({
    "false_refuse",
    "false_clarify",
    "bad_source",
    "needs_case",
    "off_topic_ok",
    "needs_review",
})

_ALL_EXPORT_LABELS: frozenset[str] = _DEFAULT_EXPORT_LABELS | frozenset({"correct"})

_DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MiB

# Safe source fields — no filesystem paths.
_SAFE_SOURCE_FIELDS: frozenset[str] = frozenset({
    "source_ref", "source_id", "chunk_id", "title",
    "section", "requirement_id", "source_type", "score", "bucket",
})

# Run fields that must never appear in exported cases.
_EXCLUDED_RUN_FIELDS: frozenset[str] = frozenset({
    "prompt_sources",
    "manual_label",
    "manual_issue",
    "semantic_warnings",
    "validation_errors",
})


def _label_to_case_fields(
    label: str,
    observed_guard_decision: str | None,
) -> dict[str, Any]:
    """Return expected_guard_decision, case_type, needs_manual_expected for a label."""
    if label == "false_refuse":
        return {
            "expected_guard_decision": "allow",
            "case_type": "guard_false_refuse",
            "needs_manual_expected": False,
        }
    if label == "false_clarify":
        return {
            "expected_guard_decision": "allow",
            "case_type": "guard_false_clarify",
            "needs_manual_expected": False,
        }
    if label == "off_topic_ok":
        # Expected decision is ambiguous — human must confirm.
        return {
            "expected_guard_decision": None,
            "case_type": "guard_off_topic_allowed",
            "needs_manual_expected": True,
        }
    if label == "bad_source":
        # Guard expectation unchanged; useful for retrieval/source-quality eval.
        return {
            "expected_guard_decision": observed_guard_decision,
            "case_type": "retrieval_bad_source",
            "needs_manual_expected": False,
        }
    if label == "needs_case":
        return {
            "expected_guard_decision": None,
            "case_type": "candidate",
            "needs_manual_expected": True,
        }
    if label == "needs_review":
        return {
            "expected_guard_decision": None,
            "case_type": "needs_review",
            "needs_manual_expected": True,
        }
    if label == "correct":
        return {
            "expected_guard_decision": observed_guard_decision,
            "case_type": "positive_regression",
            "needs_manual_expected": False,
        }
    # Unknown label — emit null and flag for manual review.
    return {
        "expected_guard_decision": None,
        "case_type": "unknown",
        "needs_manual_expected": True,
    }


def _build_case(
    run: dict[str, Any],
    label_record: dict[str, Any],
) -> dict[str, Any]:
    """Build one export case row from a run + its label record."""
    run_id = run.get("run_id", "")
    label = label_record.get("label", "")
    observed_guard = run.get("guard_decision")

    label_fields = _label_to_case_fields(label, observed_guard)

    # Source refs and titles — safe fields only, no paths.
    sources = run.get("sources")
    source_refs: list[str] = []
    source_titles: list[str] = []
    if isinstance(sources, list):
        for s in sources:
            if not isinstance(s, dict):
                continue
            ref = s.get("source_ref")
            if ref:
                source_refs.append(str(ref))
            title = s.get("title")
            if title:
                source_titles.append(str(title))

    case: dict[str, Any] = {
        "case_id": f"run_{run_id}",
        "run_id": run_id,
        "created_at": run.get("created_at"),
        "query": run.get("query"),
        "label": label,
        "observed_guard_decision": observed_guard,
        "observed_status": run.get("status"),
        "manual_issue": label_record.get("manual_issue"),
        "comment": label_record.get("comment"),
        "source_refs": source_refs,
        "source_titles": source_titles,
        "answer_preview": run.get("answer_preview"),
        "metadata": {
            "mode": run.get("mode"),
            "top_k": run.get("top_k"),
            "search_status": run.get("search_status"),
            "llm_called": run.get("llm_called"),
            "llm_model": run.get("llm_model"),
            "llm_finish_reason": run.get("llm_finish_reason"),
            "latency_ms": run.get("latency_ms"),
        },
    }
    case.update(label_fields)
    return case


@dataclass(slots=True)
class GuardCaseExporter:
    """Export reviewed chat runs into a structured JSONL regression case file.

    Original chat_runs.jsonl is never modified.  The exporter reads both files
    with the same bounded-tail strategy as ReviewQueue, deduplicates labels
    (last record per run_id wins), and applies the label→case mapping defined
    in ``_label_to_case_fields``.
    """

    runs_path: Path
    labels_path: Path
    max_bytes: int = _DEFAULT_MAX_BYTES

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def export_cases(
        self,
        *,
        include_correct: bool = False,
        limit: int | None = None,
        filter_labels: frozenset[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return case rows for all reviewed runs matching the filter.

        Args:
            include_correct: include ``correct``-labeled runs (default False).
            limit: cap on total cases returned.
            filter_labels: explicit label whitelist; overrides include_correct.
        """
        allowed = self._allowed_labels(
            include_correct=include_correct,
            filter_labels=filter_labels,
        )
        runs = self._read_jsonl_tail(self.runs_path)
        labels = self._load_labels()
        cases: list[dict[str, Any]] = []
        for run in runs:
            if limit is not None and len(cases) >= limit:
                break
            run_id = run.get("run_id")
            if not run_id:
                continue
            lbl_record = labels.get(run_id)
            if lbl_record is None:
                continue
            if lbl_record.get("label") not in allowed:
                continue
            cases.append(_build_case(run, lbl_record))
        return cases

    def write_cases(
        self,
        out_path: Path,
        *,
        include_correct: bool = False,
        limit: int | None = None,
        filter_labels: frozenset[str] | None = None,
    ) -> dict[str, Any]:
        """Export cases to out_path and return a summary dict.

        Written atomically: all data is serialised into a temp file in the same
        directory, then replaced with os.replace() so readers never see a
        partial file.  Original chat_runs.jsonl is never touched.
        """
        runs = self._read_jsonl_tail(self.runs_path)
        labels_map = self._load_labels()

        cases = self.export_cases(
            include_correct=include_correct,
            limit=limit,
            filter_labels=filter_labels,
        )

        # skipped_unlabeled: runs in the current bounded tail with no label entry.
        labeled_run_ids = frozenset(labels_map)
        skipped_unlabeled = sum(
            1 for r in runs if r.get("run_id") and r["run_id"] not in labeled_run_ids
        )
        allowed = self._allowed_labels(
            include_correct=include_correct,
            filter_labels=filter_labels,
        )
        skipped_correct = sum(
            1 for rec in labels_map.values()
            if rec.get("label") == "correct" and "correct" not in allowed
        )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=out_path.parent, prefix=".tmp_guard_cases_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                for case in cases:
                    fh.write(json.dumps(case, ensure_ascii=False, separators=(",", ":")) + "\n")
            os.replace(tmp, out_path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

        return {
            "runs_read": len(runs),
            "labels_read": len(labels_map),
            "cases_written": len(cases),
            "skipped_unlabeled": skipped_unlabeled,
            "skipped_correct": skipped_correct,
            "output": str(out_path),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _allowed_labels(
        *,
        include_correct: bool,
        filter_labels: frozenset[str] | None,
    ) -> frozenset[str]:
        if filter_labels is not None:
            return filter_labels
        if include_correct:
            return _ALL_EXPORT_LABELS
        return _DEFAULT_EXPORT_LABELS

    def _read_jsonl_tail(self, path: Path) -> list[dict[str, Any]]:
        """Read JSONL from tail of path, bounded to max_bytes.

        Returns records in file order (oldest first).
        Invalid JSON lines and non-dict objects are silently skipped.
        """
        if not path.exists():
            return []
        size = path.stat().st_size
        offset = max(0, size - self.max_bytes)
        with path.open("rb") as fh:
            if offset > 0:
                fh.seek(offset)
                fh.readline()  # discard potentially partial first line
            raw = fh.read(self.max_bytes + 1)
        records: list[dict[str, Any]] = []
        for line in raw.decode("utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
                if isinstance(obj, dict):
                    records.append(obj)
            except json.JSONDecodeError:
                continue
        return records

    def _load_labels(self) -> dict[str, dict[str, Any]]:
        """Return {run_id: latest_label_record} from sidecar (last wins)."""
        latest: dict[str, dict[str, Any]] = {}
        for rec in self._read_jsonl_tail(self.labels_path):
            run_id = rec.get("run_id")
            if run_id:
                latest[run_id] = rec
        return latest
