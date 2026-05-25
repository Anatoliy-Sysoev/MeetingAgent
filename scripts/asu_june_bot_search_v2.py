from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


WORK_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = WORK_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from asu_june_bot.search.models import SearchRequest  # noqa: E402
from asu_june_bot.search.service import SearchService  # noqa: E402


DEFAULT_CHUNKS_PATH = "data/asu_june_bot/chunks_v2.jsonl"
DEFAULT_INDEX_DIR = "data/asu_june_bot/numpy_index_v2"


def get_path(item: dict[str, Any]) -> str | None:
    metadata = item.get("metadata") or {}
    return item.get("relative_path") or item.get("document") or metadata.get("relative_path")


def get_warning(item: dict[str, Any]) -> str | None:
    diagnostics = item.get("diagnostics") or {}
    warning = diagnostics.get("retrieval_warning")
    return str(warning) if warning else None


def write_json_output(payload: dict[str, Any], output_path: str | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if output_path:
        path = Path(output_path)
        if not path.is_absolute():
            path = WORK_ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8", newline="\n")
        print(f"JSON сохранён: {path}")
        return
    print(text)


def print_human(payload: dict[str, Any]) -> None:
    print(f"Запрос: {payload['query']}")
    print(f"Корпус: {payload['corpus']}")
    print(f"Режим: {payload['mode']}")
    print(f"Статус: {payload.get('status', 'ok')}")
    guard = payload.get("guard") or {}
    query_intent = payload.get("query_intent") or {}
    if query_intent:
        print(f"Intent: {query_intent.get('intent')} | project_related={query_intent.get('is_project_related')} | confidence={query_intent.get('confidence')}")
    if guard:
        print(f"Guard: {guard.get('decision')} | reason={guard.get('reason')}")
    if payload.get("context"):
        context = payload["context"]
        diagnostics = context.get("diagnostics") or {}
        print(
            "Context: "
            f"primary={diagnostics.get('primary_count')} "
            f"supporting={diagnostics.get('supporting_count')} "
            f"excluded={diagnostics.get('excluded_count')}"
        )
    if payload.get("answer"):
        print(f"Ответ: {payload['answer']}")
    if payload.get("warnings"):
        print("Предупреждения:")
        for warning in payload["warnings"]:
            print(f"- {warning}")
    service_diag = ((payload.get("diagnostics") or {}).get("search_service") or {})
    if service_diag:
        print(f"Retrieval called: {service_diag.get('retrieval_called')} | elapsed={service_diag.get('total_elapsed_ms')} ms")
    print(f"Результатов: {len(payload.get('results', []))}")
    print()
    for item in payload.get("results", []):
        metadata = item.get("metadata") or {}
        requirement_id = item.get("requirement_id") or metadata.get("requirement_id")
        print(
            f"[{item['source_id']}] score={item['score']} "
            f"vector={item['vector_score']} bm25={item['bm25_score']} matched_by={','.join(item['matched_by'])}"
        )
        warning = get_warning(item)
        if warning:
            print(f"Предупреждение: {warning}")
        rerank_labels = (item.get("diagnostics") or {}).get("rerank_labels") or []
        if rerank_labels:
            print(f"Rerank: {', '.join(rerank_labels)}")
        print(f"Документ: {item.get('document')}")
        print(f"Тип: {item.get('document_type')} | Source type: {item.get('source_type')} | Модуль: {item.get('module')}")
        print(f"Раздел: {item.get('section')} | Requirement: {requirement_id} | Chunk: {item.get('chunk_index')}")
        print(f"Путь: {get_path(item)}")
        if item.get("source_url"):
            print(f"Cloud URL: {item.get('source_url')}")
        print(f"Фрагмент: {item.get('text_preview')}")
        print("-" * 100)


def main() -> None:
    parser = argparse.ArgumentParser(description="Asu June Bot v2 search CLI over SearchService")
    parser.add_argument("query", nargs="+", help="Поисковый запрос")
    parser.add_argument("--top-k", type=int, default=10, help="Количество результатов")
    parser.add_argument("--mode", choices=["hybrid", "vector", "bm25"], default="hybrid", help="Режим поиска")
    parser.add_argument("--chunks-path", default=DEFAULT_CHUNKS_PATH)
    parser.add_argument("--index-dir", default=DEFAULT_INDEX_DIR)
    parser.add_argument(
        "--include-source-type",
        action="append",
        dest="include_source_types",
        help="Явно разрешить source_type. Можно указать несколько раз",
    )
    parser.add_argument("--json", action="store_true", help="Вывод JSON")
    parser.add_argument("--output", help="Путь для безопасной записи JSON в UTF-8 без PowerShell redirection")
    parser.add_argument("--no-guard", action="store_true", help="Отключить ProjectGuard для диагностики retrieval")
    args = parser.parse_args()

    query = " ".join(args.query).strip()
    if not query:
        raise SystemExit("Пустой запрос")

    if args.output and not args.json:
        args.json = True

    request = SearchRequest(
        query=query,
        mode=args.mode,
        top_k=args.top_k,
        chunks_path=args.chunks_path,
        index_dir=args.index_dir,
        include_source_types=args.include_source_types,
        no_guard=args.no_guard,
        include_diagnostics=True,
    )
    payload = SearchService(work_root=WORK_ROOT).search(request).to_dict()

    if args.json:
        write_json_output(payload, args.output)
    else:
        print_human(payload)


if __name__ == "__main__":
    main()
