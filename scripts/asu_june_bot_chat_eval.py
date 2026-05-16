from __future__ import annotations

import argparse
import sys
from pathlib import Path


WORK_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = WORK_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from asu_june_bot.chat import ChatService  # noqa: E402
from asu_june_bot.core.config import load_config  # noqa: E402
from asu_june_bot.eval.loader import load_cases  # noqa: E402
from asu_june_bot.eval.report import save_report  # noqa: E402
from asu_june_bot.eval.runner import EvalRunner  # noqa: E402
from asu_june_bot.llm.ollama_openai import OllamaOpenAIClient  # noqa: E402
from asu_june_bot.observability import ChatRunsLogger  # noqa: E402
from asu_june_bot.search import SearchService  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Asu June Bot Chat Eval")
    parser.add_argument("--cases", default="eval/cases/base.jsonl", help="Path to eval cases JSONL")
    parser.add_argument("--reports-dir", default="eval/reports", help="Directory for JSON/Markdown reports")
    parser.add_argument("--label", default="baseline", help="Report label")
    parser.add_argument("--model", default=None, help="Override chat model")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--no-log", action="store_true", help="Disable chat_runs.jsonl logging during eval")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    cases_path = Path(args.cases)
    if not cases_path.is_absolute():
        cases_path = WORK_ROOT / cases_path
    reports_dir = Path(args.reports_dir)
    if not reports_dir.is_absolute():
        reports_dir = WORK_ROOT / reports_dir

    config = load_config()
    ollama_cfg = config.get("ollama", {}) if isinstance(config.get("ollama"), dict) else {}
    chat_base_url = str(ollama_cfg.get("chat_base_url") or "http://127.0.0.1:11434/v1")
    model = args.model or str(ollama_cfg.get("chat_model") or "qwen2.5:7b-instruct")

    cases = load_cases(cases_path)
    chat_service = ChatService(
        search_service=SearchService(config=config),
        llm_client=OllamaOpenAIClient(base_url=chat_base_url, model=model),
        runs_logger=None if args.no_log else ChatRunsLogger(WORK_ROOT / "data" / "asu_june_bot" / "chat_runs.jsonl"),
    )
    report = EvalRunner(chat_service=chat_service).run(cases=cases, model=model, top_k=args.top_k)
    json_path, md_path = save_report(report, output_dir=reports_dir, label=args.label)

    print(f"Eval cases: {report.total}")
    print(f"Passed: {report.passed}")
    print(f"Failed: {report.failed}")
    print(f"Pass rate: {report.pass_rate * 100:.1f}%")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {md_path}")
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
