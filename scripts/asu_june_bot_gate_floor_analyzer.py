from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCOPES = ("project", "out_of_scope", "harmful_security")
NOISE_DOCTYPES = {None, "", "unknown", "system_export", "noise"}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def pct(values: list[float], p: int) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    k = (len(sorted_values) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(sorted_values) - 1)
    return round(sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo), 4)


def first_present(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
    return default


def is_project_doc(candidate: dict[str, Any]) -> bool:
    source_type = str(first_present(candidate, "source_type", default="") or "").lower()
    if source_type == "project_doc":
        return True
    document_type = first_present(candidate, "document_type")
    return document_type not in NOISE_DOCTYPES


def features(row: dict[str, Any]) -> dict[str, Any]:
    candidates = first_present(row, "top_results", default=[]) or []
    vectors = [c.get("vector_score") for c in candidates if isinstance(c.get("vector_score"), (int, float))]
    overlaps = [c.get("term_overlap") for c in candidates if isinstance(c.get("term_overlap"), (int, float))]
    return {
        "max_vector": max(vectors) if vectors else None,
        "max_term_overlap": max(overlaps) if overlaps else None,
        "has_term_overlap": bool(overlaps),
        "project_doc_hits": sum(1 for candidate in candidates if is_project_doc(candidate)),
        "n_candidates": len(candidates),
    }


def passes_gate(feature_row: dict[str, Any], floor: float, k: int, term_available: bool) -> bool:
    vector_ok = feature_row["max_vector"] is not None and feature_row["max_vector"] >= floor
    if not term_available:
        return vector_ok
    lexical_ok = (
        feature_row["max_term_overlap"] is not None
        and feature_row["max_term_overlap"] >= k
        and feature_row["project_doc_hits"] > 0
    )
    return bool(vector_ok or lexical_ok)


def build_report(rows: list[dict[str, Any]], dataset_rows: list[dict[str, Any]] | None, floors: list[float], ks: list[int]) -> str:
    id_to_scope: dict[str, tuple[str, str]] = {}
    for row in dataset_rows or []:
        row_id = first_present(row, "id", "query_id", "qid")
        if row_id is not None:
            id_to_scope[str(row_id)] = (
                str(first_present(row, "scope", default="unknown")),
                str(first_present(row, "category", default="unknown")),
            )

    by_scope: dict[str, list[dict[str, Any]]] = defaultdict(list)
    term_available = True
    for row in rows:
        scope = first_present(row, "scope")
        if scope is None:
            row_id = first_present(row, "id", "query_id", "qid")
            scope = id_to_scope.get(str(row_id), ("unknown", "unknown"))[0]
        feature_row = features(row)
        if not feature_row["has_term_overlap"]:
            term_available = False
        by_scope[str(scope)].append(feature_row)

    lines: list[str] = []
    total = sum(len(values) for values in by_scope.values())
    lines.append("# NTK retrieval gate floor analyzer")
    lines.append("")
    lines.append(f"- rows: {total}")
    for scope in SCOPES:
        lines.append(f"- {scope}: {len(by_scope.get(scope, []))}")
    if not term_available:
        lines.append("- warning: `term_overlap` отсутствует минимум в одной строке; lexical route отключен.")

    lines.extend(["", "## Max Vector Distribution", ""])
    for scope in SCOPES:
        feature_rows = by_scope.get(scope, [])
        if not feature_rows:
            continue
        values = [row["max_vector"] for row in feature_rows if row["max_vector"] is not None]
        missing = sum(1 for row in feature_rows if row["max_vector"] is None)
        lines.append(
            f"- {scope}: n={len(feature_rows)} p10={pct(values, 10)} p50={pct(values, 50)} "
            f"p90={pct(values, 90)} max={pct(values, 100)} missing_vector={missing}"
        )

    if term_available:
        lines.extend(["", "## Max Term Overlap Distribution", ""])
        for scope in SCOPES:
            feature_rows = by_scope.get(scope, [])
            if not feature_rows:
                continue
            values = [row["max_term_overlap"] for row in feature_rows if row["max_term_overlap"] is not None]
            lines.append(
                f"- {scope}: p10={pct(values, 10)} p50={pct(values, 50)} "
                f"p90={pct(values, 90)} max={pct(values, 100)}"
            )

    project = by_scope.get("project", [])
    out_of_scope = by_scope.get("out_of_scope", [])
    harmful = by_scope.get("harmful_security", [])
    effective_ks = ks if term_available else [0]

    lines.extend(["", "## Frontier", ""])
    lines.append("Gate: `(max_vector >= floor) OR (term_overlap >= k AND project_doc_hits > 0)`")
    lines.append("")
    lines.append("| floor | k | project_pass | out_of_scope_leak | harmful_pass |")
    lines.append("|---:|---:|---:|---:|---:|")
    best: tuple[int, float, int] | None = None
    for floor in floors:
        for k in effective_ks:
            project_pass = sum(1 for row in project if passes_gate(row, floor, k, term_available))
            out_leak = sum(1 for row in out_of_scope if passes_gate(row, floor, k, term_available))
            harmful_pass = sum(1 for row in harmful if passes_gate(row, floor, k, term_available))
            lines.append(f"| {floor:.2f} | {k} | {project_pass}/{len(project)} | {out_leak} | {harmful_pass} |")
            if out_leak == 0 and (best is None or project_pass > best[0]):
                best = (project_pass, floor, k)

    lines.extend(["", "## Recommendation", ""])
    if best is None:
        lines.append("Нет точки с `out_of_scope_leak=0`; нужен дополнительный сигнал, например intent -> document_type.")
    else:
        lines.append(
            f"Лучшая точка с `out_of_scope_leak=0`: `floor={best[1]:.2f}`, `k={best[2]}`, "
            f"`project_pass={best[0]}/{len(project)}`."
        )
    lines.append("")
    lines.append("`harmful_pass` здесь диагностический: harmful держится pre-retrieval guard, а не evidence gate.")
    return "\n".join(lines) + "\n"


def parse_float_list(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def parse_int_list(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze retrieval-only probe candidates for evidence gate floor calibration")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--dataset", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--floors", default="0.40,0.42,0.44,0.46,0.48,0.50,0.52,0.55")
    parser.add_argument("--ks", default="1,2,3")
    args = parser.parse_args()

    rows = load_jsonl(args.report)
    dataset_rows = load_jsonl(args.dataset) if args.dataset and args.dataset.exists() else None
    report = build_report(rows, dataset_rows, parse_float_list(args.floors), parse_int_list(args.ks))

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
