from __future__ import annotations

import argparse
import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


ROOT = repo_root()
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from meeting_agent.evaluation.summary_benchmark import (  # noqa: E402
    evaluate_candidate_dir,
    load_benchmark_cases,
    write_report,
)


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def run(args: argparse.Namespace) -> int:
    cases_path = resolve_path(args.cases)
    candidate_dir = resolve_path(args.candidate_dir)
    out_dir = resolve_path(args.out_dir)
    cases = load_benchmark_cases(cases_path)
    report = evaluate_candidate_dir(
        cases=cases,
        candidate_dir=candidate_dir,
        provider=args.provider,
        model=args.model,
    )
    paths = write_report(report, out_dir)
    print("meeting summary benchmark complete")
    print(f"provider: {report.provider}")
    print(f"model: {report.model or ''}")
    print(f"cases: {len(report.results)}")
    print(f"score: {report.score:.3f}")
    print(f"passed: {report.passed}")
    print(f"json: {paths['json']}")
    print(f"markdown: {paths['markdown']}")
    return 0 if report.score >= args.fail_under and report.passed else 1


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate meeting summary/protocol structured artifacts.")
    parser.add_argument("--cases", default="eval/cases/meeting_summary_synthetic.jsonl")
    parser.add_argument("--candidate-dir", required=True, help="Directory with artifacts or case_id/artifacts folders.")
    parser.add_argument("--provider", required=True, help="Provider label, e.g. ollama, gigachat, groq.")
    parser.add_argument("--model", default=None, help="Model label for comparison reports.")
    parser.add_argument("--out-dir", default="eval/reports/meeting_summary")
    parser.add_argument("--fail-under", type=float, default=1.0, help="Minimum average score. Default requires perfect score.")
    return parser.parse_args(argv)


def main() -> int:
    try:
        return run(parse_args(sys.argv[1:]))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
