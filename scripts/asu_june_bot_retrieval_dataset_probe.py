from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from statistics import quantiles
from typing import Any


WORK_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = WORK_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from asu_june_bot.core.config import load_config, resolve_work_path  # noqa: E402
from asu_june_bot.core.corpus import get_corpus_config  # noqa: E402
from asu_june_bot.retrieval.chunks import read_jsonl as read_chunks_jsonl  # noqa: E402
from asu_june_bot.retrieval.context_builder import ContextBuilder  # noqa: E402
from asu_june_bot.retrieval.hybrid import build_hybrid_retriever  # noqa: E402
from asu_june_bot.retrieval.post_rerank import PostReranker  # noqa: E402
from asu_june_bot.retrieval.query_intent import classify_query_intent  # noqa: E402


DEFAULT_DATASET = "docs/quality/ntk_realistic_500_v3_queries_2026-06-03.jsonl"
DEFAULT_REPORT = "docs/quality/ntk_realistic_500_v3_retrieval_probe_2026-06-04.jsonl"
DEFAULT_SUMMARY = "docs/quality/ntk_realistic_500_v3_retrieval_probe_summary_2026-06-04.md"


def resolve_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = WORK_ROOT / path
    return path


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if "query" not in row:
                raise ValueError(f"Missing query at {path}:{line_no}")
            rows.append(row)
    return rows


def score_values(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "raw_results_count": 0,
            "best_score": None,
            "best_vector_score": None,
            "best_bm25_score": None,
            "best_raw_bm25_score": None,
            "best_document_type": None,
            "best_source_type": None,
            "best_matched_by": [],
            "best_source_id": None,
            "best_chunk_id": None,
            "best_title": None,
            "best_path": None,
        }
    best = results[0]
    diagnostics = best.get("diagnostics") or {}
    metadata = best.get("metadata") or {}
    return {
        "raw_results_count": len(results),
        "best_score": best.get("score"),
        "best_vector_score": best.get("vector_score"),
        "best_bm25_score": best.get("bm25_score"),
        "best_raw_bm25_score": diagnostics.get("raw_bm25_score"),
        "best_vector_component": diagnostics.get("vector_component"),
        "best_bm25_component": diagnostics.get("bm25_component"),
        "best_document_type": best.get("document_type"),
        "best_source_type": best.get("source_type"),
        "best_matched_by": best.get("matched_by") or [],
        "best_source_id": best.get("source_id"),
        "best_chunk_id": metadata.get("chunk_id") or best.get("chunk_id"),
        "best_title": best.get("title"),
        "best_path": best.get("document"),
    }


class ProbeRuntime:
    def __init__(self, mode: str) -> None:
        self.cfg = load_config()
        corpus = get_corpus_config(self.cfg)
        chunks_path = resolve_work_path(self.cfg, corpus.chunks_path)
        self.rows = read_chunks_jsonl(chunks_path)
        self.retriever = build_hybrid_retriever(self.cfg, self.rows, mode=mode)
        self.reranker = PostReranker()
        self.context_builder = ContextBuilder()
        self.mode = mode

    def search_no_guard(self, query: str, top_k: int) -> dict[str, Any]:
        intent = classify_query_intent(query)
        raw_results = self.retriever.search(
            query=query,
            top_k=max(top_k * 2, top_k + 8),
            include_source_types=None,
            mode=self.mode,
        )
        rerank = self.reranker.rerank(query, intent, raw_results, top_k=top_k)
        context = self.context_builder.build(query, intent, rerank.results, rerank.excluded)
        return {
            "status": "ok",
            "query_intent": intent.to_dict(),
            "retrieval_raw_results": len(raw_results),
            "rerank": rerank.diagnostics,
            "context": context.to_dict(),
            "results": [result.to_dict() for result in rerank.results],
        }


def probe_row(runtime: ProbeRuntime, row: dict[str, Any], idx: int, top_k: int) -> dict[str, Any]:
    query = str(row["query"])
    base = {
        "row_index": idx,
        "id": row.get("id") or row.get("eval_id") or f"row_{idx}",
        "scope": row.get("scope"),
        "category": row.get("category"),
        "query": query,
    }
    try:
        payload = runtime.search_no_guard(query=query, top_k=top_k)
        results = payload.get("results") or []
        context = payload.get("context") or {}
        context_diag = context.get("diagnostics") or {}
        row_payload = {
            **base,
            "status": payload.get("status"),
            "error": payload.get("error"),
            "retrieval_called": True,
            "retrieval_raw_results": payload.get("retrieval_raw_results"),
            "primary_count": context_diag.get("primary_count"),
            "supporting_count": context_diag.get("supporting_count"),
            "excluded_count": context_diag.get("excluded_count"),
            "source_quality_filter": context_diag.get("source_quality_filter"),
            **score_values(results if isinstance(results, list) else []),
        }
        return row_payload
    except Exception as exc:  # noqa: BLE001
        return {
            **base,
            "status": "probe_error",
            "error": repr(exc),
            "retrieval_called": None,
        }


def percentile_summary(values: list[float]) -> dict[str, float | int | None]:
    values = sorted(float(v) for v in values if v is not None)
    if not values:
        return {"count": 0, "min": None, "p10": None, "p25": None, "p50": None, "p75": None, "p90": None, "max": None}
    if len(values) == 1:
        v = values[0]
        return {"count": 1, "min": v, "p10": v, "p25": v, "p50": v, "p75": v, "p90": v, "max": v}
    qs = quantiles(values, n=100, method="inclusive")
    return {
        "count": len(values),
        "min": values[0],
        "p10": qs[9],
        "p25": qs[24],
        "p50": qs[49],
        "p75": qs[74],
        "p90": qs[89],
        "max": values[-1],
    }


def build_summary(rows: list[dict[str, Any]], dataset_path: Path, report_path: Path) -> str:
    status_counts = Counter(str(row.get("status")) for row in rows)
    scope_counts = Counter(str(row.get("scope")) for row in rows)
    lines = [
        "# NTK realistic 500 v3 retrieval-only probe",
        "",
        "Дата: 2026-06-04",
        "",
        "Назначение: измерить retrieval score distributions с `no_guard=True`, без LLM.",
        "",
        f"Dataset: `{dataset_path.relative_to(WORK_ROOT)}`",
        f"Report: `{report_path.relative_to(WORK_ROOT)}`",
        "",
        "## Counts",
        "",
        f"- total: {len(rows)}",
    ]
    for scope, count in scope_counts.most_common():
        lines.append(f"- scope {scope}: {count}")
    for status, count in status_counts.most_common():
        lines.append(f"- status {status}: {count}")

    lines.extend(["", "## Best Vector Score Percentiles By Scope", ""])
    for scope in sorted(scope_counts):
        values = [row.get("best_vector_score") for row in rows if str(row.get("scope")) == scope]
        lines.append(f"- {scope}: {percentile_summary(values)}")

    lines.extend(["", "## Best BM25 Score Percentiles By Scope", ""])
    for scope in sorted(scope_counts):
        values = [row.get("best_bm25_score") for row in rows if str(row.get("scope")) == scope]
        lines.append(f"- {scope}: {percentile_summary(values)}")

    lines.extend(["", "## Candidate Vector Floors", ""])
    project_rows = [row for row in rows if row.get("scope") == "project"]
    project_values = [float(row["best_vector_score"]) for row in project_rows if row.get("best_vector_score") is not None]
    project_missing_vector = len(project_rows) - len(project_values)
    for floor in (0.45, 0.5, 0.55, 0.6, 0.65, 0.7):
        below_project = sum(1 for value in project_values if value < floor)
        out_above = sum(1 for row in rows if row.get("scope") == "out_of_scope" and row.get("best_vector_score") is not None and float(row["best_vector_score"]) >= floor)
        harmful_above = sum(1 for row in rows if row.get("scope") == "harmful_security" and row.get("best_vector_score") is not None and float(row["best_vector_score"]) >= floor)
        lines.append(
            f"- floor {floor:.2f}: project_below_vector={below_project}/{len(project_values)}, "
            f"project_missing_vector={project_missing_vector}, "
            f"project_below_or_missing={below_project + project_missing_vector}/{len(project_rows)}, "
            f"out_of_scope_above={out_above}, harmful_above={harmful_above}"
        )

    lines.extend(["", "## Lowest Project Vector Scores", ""])
    low_project = sorted(
        [row for row in rows if row.get("scope") == "project"],
        key=lambda row: float(row.get("best_vector_score") or -1),
    )[:25]
    for row in low_project:
        lines.append(
            f"- `{row.get('id')}` vector={row.get('best_vector_score')} bm25={row.get('best_bm25_score')} "
            f"category={row.get('category')} doc={row.get('best_document_type')} query={row.get('query')}"
        )

    lines.extend(["", "## Highest Out Of Scope Vector Scores", ""])
    high_oos = sorted(
        [row for row in rows if row.get("scope") in {"out_of_scope", "harmful_security"}],
        key=lambda row: float(row.get("best_vector_score") or -1),
        reverse=True,
    )[:25]
    for row in high_oos:
        lines.append(
            f"- `{row.get('id')}` scope={row.get('scope')} vector={row.get('best_vector_score')} "
            f"bm25={row.get('best_bm25_score')} doc={row.get('best_document_type')} query={row.get('query')}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe retrieval distributions on a dataset with no_guard=True and no LLM")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--report", default=DEFAULT_REPORT)
    parser.add_argument("--summary", default=DEFAULT_SUMMARY)
    parser.add_argument("--mode", default="hybrid", choices=["hybrid", "vector", "bm25"])
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0, help="Optional first-N limit for smoke")
    args = parser.parse_args()

    dataset_path = resolve_path(args.dataset)
    report_path = resolve_path(args.report)
    summary_path = resolve_path(args.summary)

    rows = read_jsonl(dataset_path)
    if args.limit:
        rows = rows[: args.limit]

    runtime = ProbeRuntime(mode=args.mode)
    results: list[dict[str, Any]] = []
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8", newline="\n") as w:
        for idx, row in enumerate(rows, start=1):
            result = probe_row(runtime, row, idx, args.top_k)
            results.append(result)
            w.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
            if idx % 25 == 0 or idx == len(rows):
                print(f"processed={idx}/{len(rows)}", flush=True)

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(build_summary(results, dataset_path, report_path), encoding="utf-8")

    print(json.dumps({"total": len(results), "status": Counter(str(row.get("status")) for row in results)}, ensure_ascii=False, indent=2))
    print(f"report_path: {report_path}")
    print(f"summary_path: {summary_path}")


if __name__ == "__main__":
    main()
