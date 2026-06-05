from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
    return rows


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize(text: Any) -> str:
    return " ".join(str(text or "").lower().replace("ё", "е").split())


def row_text(row: dict[str, Any]) -> str:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    parts = [
        row.get("text"),
        row.get("text_preview"),
        row.get("title"),
        row.get("relative_path"),
        row.get("path"),
        row.get("document_type"),
        row.get("requirement_id"),
        row.get("table_id"),
        metadata.get("title") if metadata else None,
        metadata.get("relative_path") if metadata else None,
        metadata.get("document_type") if metadata else None,
        metadata.get("requirement_id") if metadata else None,
        metadata.get("table_id") if metadata else None,
    ]
    cells = row.get("cells") or (metadata.get("cells") if metadata else None)
    if isinstance(cells, dict):
        parts.extend(cells.keys())
        parts.extend(cells.values())
    headers = row.get("headers") or (metadata.get("headers") if metadata else None)
    if isinstance(headers, list):
        parts.extend(headers)
    return normalize(" ".join(str(part or "") for part in parts))


def metadata_value(row: dict[str, Any], key: str) -> str:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    return str(row.get(key) or metadata.get(key) or "")


def required_terms(gold_row: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for key in ("required_terms", "expected_answer_facts", "required_anchors"):
        value = gold_row.get(key)
        if isinstance(value, list):
            terms.extend(str(item) for item in value if str(item).strip())
    return terms


def required_sources(gold_row: dict[str, Any]) -> list[dict[str, Any]]:
    raw = gold_row.get("required_sources") or []
    sources: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                sources.append(item)
            elif str(item).strip():
                sources.append({"path_contains": str(item)})
    return sources


def row_matches_source(row: dict[str, Any], source: dict[str, Any]) -> bool:
    haystack = row_text(row)
    document_type = normalize(metadata_value(row, "document_type"))
    if source.get("document_type") and normalize(source["document_type"]) != document_type:
        return False
    if source.get("table_id") and normalize(source["table_id"]) != normalize(metadata_value(row, "table_id")):
        return False
    if source.get("requirement_id") and normalize(source["requirement_id"]) != normalize(metadata_value(row, "requirement_id")):
        return False
    path_contains = source.get("path_contains") or source.get("source_name_contains")
    if path_contains and normalize(path_contains) not in haystack:
        return False
    return True


@dataclass(frozen=True)
class CoverageResult:
    eval_id: str
    ok: bool
    matched_sources: int
    matched_terms: list[str]
    missing_terms: list[str]
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "eval_id": self.eval_id,
            "ok": self.ok,
            "matched_sources": self.matched_sources,
            "matched_terms": self.matched_terms,
            "missing_terms": self.missing_terms,
            "notes": self.notes,
        }


def chunks_for_sources(chunks: list[dict[str, Any]], sources: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    source_list = list(sources)
    if not source_list:
        return chunks
    matched: list[dict[str, Any]] = []
    for row in chunks:
        if any(row_matches_source(row, source) for source in source_list):
            matched.append(row)
    return matched


def check_gold_row(gold_row: dict[str, Any], chunks: list[dict[str, Any]]) -> CoverageResult:
    eval_id = str(gold_row.get("id") or gold_row.get("eval_id") or gold_row.get("query") or "unknown")
    sources = required_sources(gold_row)
    candidate_chunks = chunks_for_sources(chunks, sources)
    terms = required_terms(gold_row)
    candidate_texts = [row_text(row) for row in candidate_chunks]
    matched_terms: list[str] = []
    missing_terms: list[str] = []
    for term in terms:
        normalized = normalize(term)
        if any(normalized in text for text in candidate_texts):
            matched_terms.append(term)
        else:
            missing_terms.append(term)
    source_ok = bool(candidate_chunks) if sources else True
    terms_ok = not missing_terms
    return CoverageResult(
        eval_id=eval_id,
        ok=source_ok and terms_ok,
        matched_sources=len(candidate_chunks),
        matched_terms=matched_terms,
        missing_terms=missing_terms,
        notes=None if source_ok else "required_source_not_found",
    )


def build_report(gold_rows: list[dict[str, Any]], chunks: list[dict[str, Any]]) -> dict[str, Any]:
    results = [check_gold_row(row, chunks).to_dict() for row in gold_rows]
    failed = [row for row in results if not row["ok"]]
    return {
        "gold_rows": len(gold_rows),
        "chunks": len(chunks),
        "ok": len(results) - len(failed),
        "failed": len(failed),
        "failed_ids": [row["eval_id"] for row in failed],
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Check whether gold anchors are covered by a JSONL chunk index")
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--chunks", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    report = build_report(read_jsonl(args.gold), read_jsonl(args.chunks))
    if args.out:
        write_json(args.out, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
