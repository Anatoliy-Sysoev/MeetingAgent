from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


WORK_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = WORK_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from asu_june_bot.chat import ChatRequest, ChatService  # noqa: E402
from asu_june_bot.chat.response_formatter import ResponseFormatter  # noqa: E402
from asu_june_bot.core.config import load_config  # noqa: E402
from asu_june_bot.llm.ollama_openai import OllamaOpenAIClient  # noqa: E402
from asu_june_bot.search import SearchService  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Asu June Bot Chat MVP")
    parser.add_argument("query", help="Project question")
    parser.add_argument("--mode", choices=["hybrid", "vector", "bm25"], default="hybrid")
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--model", default=None)
    parser.add_argument("--llm-base-url", default=None)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-tokens", type=int, default=1200)
    parser.add_argument("--timeout-sec", type=int, default=120)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", help="Save UTF-8 JSON to path")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = load_config()
    ollama_cfg = config.get("ollama", {}) if isinstance(config.get("ollama"), dict) else {}
    llm_base_url = args.llm_base_url or str(ollama_cfg.get("chat_base_url") or "http://127.0.0.1:11434/v1")
    model = args.model or str(ollama_cfg.get("chat_model") or "qwen3:8b")

    chat_service = ChatService(
        search_service=SearchService(config=config),
        llm_client=OllamaOpenAIClient(base_url=llm_base_url, model=model),
    )
    response = chat_service.chat(
        ChatRequest(
            query=args.query,
            mode=args.mode,
            top_k=args.top_k,
            model=model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            timeout_sec=args.timeout_sec,
        )
    )

    payload = response.to_dict()
    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = WORK_ROOT / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON сохранён: {output_path}")
        return

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(ResponseFormatter().to_text(response))


if __name__ == "__main__":
    main()
