from __future__ import annotations

import json
from pathlib import Path

from .models import EvalReport


def save_report(report: EvalReport, output_dir: Path, label: str) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_label = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in label).strip("_") or "eval"
    ts = report.generated_at.replace(":", "").replace("+00:00", "Z")
    json_path = output_dir / f"{ts}__{safe_label}.json"
    md_path = output_dir / f"{ts}__{safe_label}.md"
    payload = report.to_dict()
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def render_markdown(report: EvalReport) -> str:
    payload = report.to_dict()
    summary = payload["summary"]
    lines = [
        f"# Chat Eval Report — {report.generated_at}",
        "",
        "## Summary",
        "",
        f"- Total: **{summary['total']}**",
        f"- Passed: **{summary['passed']}**",
        f"- Failed: **{summary['failed']}**",
        f"- Pass rate: **{summary['pass_rate'] * 100:.1f}%**",
        "",
        "## By category",
        "",
        "| Category | Total | Passed | Failed |",
        "|---|---:|---:|---:|",
    ]
    for category, row in summary["by_category"].items():
        lines.append(f"| {category} | {row['total']} | {row['passed']} | {row['failed']} |")

    lines.extend([
        "",
        "## By priority",
        "",
        "| Priority | Total | Passed | Failed |",
        "|---|---:|---:|---:|",
    ])
    for priority, row in summary["by_priority"].items():
        lines.append(f"| {priority} | {row['total']} | {row['passed']} | {row['failed']} |")

    failures = [result for result in report.results if not result.passed]
    lines.extend(["", "## Failures", ""])
    if not failures:
        lines.append("No failures.")
    else:
        for result in failures:
            lines.append(f"### {result.case_id}")
            lines.append(f"- Category: `{result.category}`")
            lines.append(f"- Query: `{result.query}`")
            lines.append(f"- Status: expected `{result.expected_status}`, actual `{result.actual_status}`")
            lines.append(f"- LLM called: `{result.diagnostics.get('llm_called')}`")
            failed_checks = [check for check in result.checks if not check.passed]
            lines.append("- Failed checks:")
            for check in failed_checks:
                lines.append(f"  - `{check.name}` — {check.detail}")
            if result.sources:
                titles = [str(source.get("title") or source.get("path") or source.get("source_ref")) for source in result.sources[:5]]
                lines.append("- Sources: " + "; ".join(titles))
            if result.answer_preview:
                lines.append("- Answer preview:")
                lines.append("")
                lines.append("```text")
                lines.append(result.answer_preview[:500])
                lines.append("```")
            lines.append("")
    return "\n".join(lines)
