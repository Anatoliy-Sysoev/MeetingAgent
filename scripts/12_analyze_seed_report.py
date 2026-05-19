from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rag_common import WORK_ROOT, jsonl_read


DEFAULT_REPORT_PATH = WORK_ROOT / "data" / "synthetic_seed_report.jsonl"
DEFAULT_OUTPUT_PATH = WORK_ROOT / "data" / "synthetic_seed_summary.md"

SOURCE_LINE_RE = re.compile(r"^\[(?P<rank>\d+)\]\s+score=(?P<score>[0-9.\-]+).*?file=(?P<file>.+?)\s+chunk=", re.MULTILINE)


def extract_sources(stdout: str) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for match in SOURCE_LINE_RE.finditer(stdout or ""):
        try:
            score = float(match.group("score"))
        except ValueError:
            score = None
        sources.append(
            {
                "rank": int(match.group("rank")),
                "score": score,
                "file": match.group("file").strip(),
            }
        )
    return sources


def analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    status_counter = Counter(row.get("runner_status", "unknown") for row in rows)
    category_counter = Counter(str(row.get("category") or "unknown") for row in rows)
    category_failures: dict[str, int] = defaultdict(int)
    source_counter: Counter[str] = Counter()
    low_top_score: list[dict[str, Any]] = []
    failed_rows: list[dict[str, Any]] = []
    no_sources: list[dict[str, Any]] = []

    for row in rows:
        category = str(row.get("category") or "unknown")
        if row.get("runner_status") != "ok":
            category_failures[category] += 1
            failed_rows.append(row)
            continue

        result = row.get("result") or {}
        stdout = str(result.get("stdout") or "")
        sources = extract_sources(stdout)
        if not sources:
            no_sources.append(row)
            continue

        top = sources[0]
        if isinstance(top.get("score"), float) and top["score"] < 0.35:
            low_top_score.append(
                {
                    "seed_id": row.get("seed_id"),
                    "category": category,
                    "query": row.get("query"),
                    "score": top.get("score"),
                    "file": top.get("file"),
                }
            )
        for src in sources:
            source_counter[str(src.get("file") or "")] += 1

    return {
        "total": total,
        "status_counter": dict(status_counter),
        "category_counter": dict(category_counter),
        "category_failures": dict(category_failures),
        "failed_rows": failed_rows,
        "no_sources": no_sources,
        "low_top_score": low_top_score,
        "top_sources": source_counter.most_common(20),
    }


def md_escape(text: Any) -> str:
    return str(text or "").replace("|", "\\|").replace("\n", " ")


def render_markdown(summary: dict[str, Any], report_path: Path) -> str:
    lines: list[str] = []
    lines.append("# Synthetic Seed Report Summary")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Source report: `{report_path}`")
    lines.append("")

    lines.append("## Totals")
    lines.append("")
    lines.append(f"- total: {summary['total']}")
    for status, count in sorted(summary["status_counter"].items()):
        lines.append(f"- {status}: {count}")
    lines.append("")

    lines.append("## Categories")
    lines.append("")
    lines.append("| category | count | failures |")
    lines.append("| --- | ---: | ---: |")
    categories = summary["category_counter"]
    failures = summary["category_failures"]
    for category, count in sorted(categories.items()):
        lines.append(f"| {md_escape(category)} | {count} | {failures.get(category, 0)} |")
    lines.append("")

    lines.append("## Failed Rows")
    lines.append("")
    failed_rows = summary["failed_rows"][:30]
    if not failed_rows:
        lines.append("No failed rows.")
    else:
        lines.append("| seed_id | category | query | returncode | stderr |")
        lines.append("| --- | --- | --- | ---: | --- |")
        for row in failed_rows:
            result = row.get("result") or {}
            lines.append(
                f"| {md_escape(row.get('seed_id'))} | {md_escape(row.get('category'))} | {md_escape(row.get('query'))} | "
                f"{md_escape(result.get('returncode'))} | {md_escape(str(result.get('stderr') or '')[:240])} |"
            )
    lines.append("")

    lines.append("## No Sources")
    lines.append("")
    no_sources = summary["no_sources"][:30]
    if not no_sources:
        lines.append("No rows without parsed sources.")
    else:
        lines.append("| seed_id | category | query |")
        lines.append("| --- | --- | --- |")
        for row in no_sources:
            lines.append(f"| {md_escape(row.get('seed_id'))} | {md_escape(row.get('category'))} | {md_escape(row.get('query'))} |")
    lines.append("")

    lines.append("## Low Top Score (< 0.35)")
    lines.append("")
    low = summary["low_top_score"][:30]
    if not low:
        lines.append("No low top-score rows.")
    else:
        lines.append("| seed_id | category | score | query | top file |")
        lines.append("| --- | --- | ---: | --- | --- |")
        for row in low:
            lines.append(
                f"| {md_escape(row.get('seed_id'))} | {md_escape(row.get('category'))} | {row.get('score')} | "
                f"{md_escape(row.get('query'))} | {md_escape(row.get('file'))} |"
            )
    lines.append("")

    lines.append("## Most Frequent Sources")
    lines.append("")
    top_sources = summary["top_sources"][:20]
    if not top_sources:
        lines.append("No parsed sources.")
    else:
        lines.append("| source | count |")
        lines.append("| --- | ---: |")
        for source, count in top_sources:
            lines.append(f"| {md_escape(source)} | {count} |")
    lines.append("")

    lines.append("## Review Notes")
    lines.append("")
    lines.append("Manual review is still required. This summary only checks runner status and compact retrieval output.")
    lines.append("Do not promote synthetic rows to accepted eval cases without human review.")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Анализ synthetic_seed_report.jsonl")
    parser.add_argument("--input", default=str(DEFAULT_REPORT_PATH), help="JSONL отчёт от 11_run_synthetic_seed.py")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Markdown summary")
    args = parser.parse_args()

    report_path = Path(args.input)
    output_path = Path(args.output)
    rows = list(jsonl_read(report_path))
    if not rows:
        raise SystemExit(f"Пустой или отсутствующий отчёт: {report_path}")

    summary = analyze(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_markdown(summary, report_path), encoding="utf-8", newline="\n")

    print(f"Summary сохранён: {output_path}")
    print(json.dumps({
        "total": summary["total"],
        "status_counter": summary["status_counter"],
        "failed": len(summary["failed_rows"]),
        "no_sources": len(summary["no_sources"]),
        "low_top_score": len(summary["low_top_score"]),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
