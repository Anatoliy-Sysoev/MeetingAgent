from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORK_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = WORK_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from asu_june_bot.search import SearchRequest, SearchService  # noqa: E402


DEFAULT_CASES = "docs/quality/ntk_yandex_smoke_questions.jsonl"
DEFAULT_CHUNKS = "data/asu_june_bot_ntk/chunks_v2.jsonl"
DEFAULT_INDEX = "data/asu_june_bot_ntk/numpy_index_v2"
DEFAULT_OUTPUT = "data/asu_june_bot_ntk/smoke_eval_bm25.jsonl"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")


def resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = WORK_ROOT / path
    return path.resolve()


def top_doc_types(results: list[dict[str, Any]], limit: int = 5) -> list[str]:
    out: list[str] = []
    for item in results[:limit]:
        doc_type = str(item.get("document_type") or "")
        if doc_type:
            out.append(doc_type)
    return out


def terms_hit_in_top(results: list[dict[str, Any]], terms: list[str], limit: int = 5) -> bool:
    if not terms:
        return True
    haystack = " ".join(str(item.get("text_preview") or "") for item in results[:limit]).lower()
    return all(str(term).lower() in haystack for term in terms)


def evaluate_case(case: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    results = list(payload.get("results") or [])
    expected_doc_type = case.get("expected_doc_type")
    expected_status = case.get("expected_status")
    expected_terms_in_top5 = [str(item) for item in (case.get("expected_terms_in_top5") or [])]
    status = str(payload.get("status") or "")
    top_types = top_doc_types(results)
    doc_type_hit = bool(expected_doc_type and expected_doc_type in top_types)
    status_hit = bool(expected_status and status == expected_status)
    terms_hit = terms_hit_in_top(results, expected_terms_in_top5)
    has_source_url = any(item.get("source_url") or (item.get("metadata") or {}).get("source_url") for item in results[:5])
    ok = status_hit if expected_status else (doc_type_hit and terms_hit)
    return {
        "id": case.get("id"),
        "query": case.get("query"),
        "scope": case.get("scope"),
        "category": case.get("category"),
        "expected_doc_type": expected_doc_type,
        "expected_status": expected_status,
        "expected_terms_in_top5": expected_terms_in_top5,
        "status": status,
        "ok": ok,
        "doc_type_hit": doc_type_hit,
        "status_hit": status_hit,
        "terms_hit_in_top5": terms_hit,
        "top_doc_types": top_types,
        "top_sources": [
            {
                "score": item.get("score"),
                "document": item.get("document"),
                "document_type": item.get("document_type"),
                "source_url": item.get("source_url") or (item.get("metadata") or {}).get("source_url"),
                "section": item.get("section"),
                "chunk_index": item.get("chunk_index"),
            }
            for item in results[:5]
        ],
        "source_url_in_top5": has_source_url,
        "diagnostics": payload.get("diagnostics"),
        "guard": payload.get("guard"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke retrieval eval for NTK Yandex corpus")
    parser.add_argument("--cases", default=DEFAULT_CASES)
    parser.add_argument("--chunks-path", default=DEFAULT_CHUNKS)
    parser.add_argument("--index-dir", default=DEFAULT_INDEX)
    parser.add_argument("--mode", choices=["bm25", "hybrid", "vector"], default="bm25")
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", default=None)
    args = parser.parse_args()

    cases_path = resolve(args.cases)
    output_path = resolve(args.output)
    summary_path = resolve(args.summary) if args.summary else output_path.with_suffix(".summary.json")

    service = SearchService(work_root=WORK_ROOT)
    rows: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    for case in read_jsonl(cases_path):
        payload = service.search(
            SearchRequest(
                query=str(case["query"]),
                mode=args.mode,
                top_k=args.top_k,
                chunks_path=args.chunks_path,
                index_dir=args.index_dir,
                include_diagnostics=True,
            )
        ).to_dict()
        row = evaluate_case(case, payload)
        rows.append(row)
        status_counts[row["status"]] += 1
        print(f"{row['id']}: ok={row['ok']} status={row['status']} top={row['top_doc_types'][:3]}")

    write_jsonl(output_path, rows)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cases": str(cases_path),
        "output": str(output_path),
        "mode": args.mode,
        "chunks_path": args.chunks_path,
        "index_dir": args.index_dir,
        "total": len(rows),
        "ok": sum(1 for row in rows if row["ok"]),
        "doc_type_hits": sum(1 for row in rows if row["doc_type_hit"]),
        "status_hits": sum(1 for row in rows if row["status_hit"]),
        "source_url_in_top5": sum(1 for row in rows if row["source_url_in_top5"]),
        "status_counts": dict(status_counts),
        "failed_ids": [row["id"] for row in rows if not row["ok"]],
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
