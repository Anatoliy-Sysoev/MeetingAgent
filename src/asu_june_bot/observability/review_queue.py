from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VALID_LABELS: frozenset[str] = frozenset({
    "correct",
    "false_refuse",
    "false_clarify",
    "bad_source",
    "needs_case",
    "off_topic_ok",
    "needs_review",
})

_DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MiB

# Fields from source records that are safe to expose (no filesystem paths).
_SAFE_SOURCE_FIELDS: frozenset[str] = frozenset({
    "source_ref", "source_id", "chunk_id", "title",
    "section", "requirement_id", "source_type", "score", "bucket", "text_preview",
})

# Top-level run fields that contain prompt internals and must not be returned.
_EXCLUDED_RUN_FIELDS: frozenset[str] = frozenset({
    "prompt_sources",
    "manual_label",
    "manual_issue",
})


def _safe_run_fields(run: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of run with filesystem paths and prompt internals removed."""
    out: dict[str, Any] = {
        k: v for k, v in run.items()
        if k not in _EXCLUDED_RUN_FIELDS
    }
    sources = out.get("sources")
    if isinstance(sources, list):
        out["sources"] = [
            {k: v for k, v in s.items() if k in _SAFE_SOURCE_FIELDS}
            for s in sources
            if isinstance(s, dict)
        ]
    return out


@dataclass(slots=True)
class ReviewQueue:
    """Read/label interface over chat_runs.jsonl + chat_run_labels.jsonl sidecar.

    Original chat_runs.jsonl is never modified.  Labels are appended to a
    separate sidecar file.  The latest label record per run_id wins on export.
    """

    runs_path: Path
    labels_path: Path
    max_bytes: int = _DEFAULT_MAX_BYTES

    def __post_init__(self) -> None:
        self.labels_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_runs(
        self,
        limit: int = 100,
        status: str | None = None,
        guard_decision: str | None = None,
        label: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return up to limit runs from the tail of runs_path, newest first.

        Each row includes current_label / manual_issue from the sidecar.
        Filtering on label matches the current (latest) label for each run.
        """
        runs = list(reversed(self._read_jsonl_tail(self.runs_path)))
        labels = self._load_labels()
        results: list[dict[str, Any]] = []
        for run in runs:
            if len(results) >= limit:
                break
            run_id = run.get("run_id")
            lbl_record = labels.get(run_id) if run_id else None
            current_label = lbl_record.get("label") if lbl_record else None
            if status is not None and run.get("status") != status:
                continue
            if guard_decision is not None and run.get("guard_decision") != guard_decision:
                continue
            if label is not None and current_label != label:
                continue
            out = _safe_run_fields(run)
            out["current_label"] = current_label
            out["manual_issue"] = lbl_record.get("manual_issue") if lbl_record else None
            out["comment"] = lbl_record.get("comment") if lbl_record else None
            out["labeled_at"] = lbl_record.get("labeled_at") if lbl_record else None
            results.append(out)
        return results

    def set_label(
        self,
        run_id: str,
        label: str,
        manual_issue: str | None = None,
        comment: str | None = None,
        labeled_by: str = "unknown",
    ) -> dict[str, Any]:
        """Append a label record to the sidecar file and return the new record."""
        record: dict[str, Any] = {
            "run_id": run_id,
            "label": label,
            "manual_issue": manual_issue,
            "comment": comment,
            "labeled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "labeled_by": labeled_by,
        }
        with self.labels_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        return record

    def export_joined(self) -> list[dict[str, Any]]:
        """Return all runs (oldest first) joined with their latest label."""
        runs = self._read_jsonl_tail(self.runs_path)
        labels = self._load_labels()
        result: list[dict[str, Any]] = []
        for run in runs:
            run_id = run.get("run_id")
            lbl_record = labels.get(run_id) if run_id else None
            out = _safe_run_fields(run)
            out["current_label"] = lbl_record.get("label") if lbl_record else None
            out["manual_issue"] = lbl_record.get("manual_issue") if lbl_record else None
            out["comment"] = lbl_record.get("comment") if lbl_record else None
            out["labeled_at"] = lbl_record.get("labeled_at") if lbl_record else None
            out["labeled_by"] = lbl_record.get("labeled_by") if lbl_record else None
            result.append(out)
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_jsonl_tail(self, path: Path) -> list[dict[str, Any]]:
        """Read JSONL from the tail of path, up to max_bytes.

        Returns list in file order (oldest first).  Bounded read follows the
        same TOCTOU-safe stat→read pattern as MeetingsService._read_text_bounded.
        """
        if not path.exists():
            return []
        size = path.stat().st_size
        offset = max(0, size - self.max_bytes)
        with path.open("rb") as fh:
            if offset > 0:
                fh.seek(offset)
                fh.readline()  # discard the potentially partial first line
            raw = fh.read(self.max_bytes + 1)
        lines = raw.decode("utf-8", errors="replace").splitlines()
        records: list[dict[str, Any]] = []
        for line in lines:
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
        """Return {run_id: latest_label_record} from the sidecar file.

        Last record per run_id wins (append-only log semantics).
        """
        records = self._read_jsonl_tail(self.labels_path)
        latest: dict[str, dict[str, Any]] = {}
        for rec in records:
            run_id = rec.get("run_id")
            if run_id:
                latest[run_id] = rec
        return latest
