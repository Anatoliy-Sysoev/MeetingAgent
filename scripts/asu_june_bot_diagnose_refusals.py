#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Диагностика отказов Asu June Bot по chat_runs.jsonl.

Делит bad_refusal на два механизма:
  Путь А (guard)   — guard отказал/уточнил ДО retrieval (refuse/clarify, retrieval не вызывался).
  Путь Б (порог)   — guard пропустил, retrieval нашёл источники, но порог/quality-filter
                     обнулил ответ (status no_answer/no_sources при sources>0).
  C (retrieval)    — guard пропустил, retrieval отработал, но источников нет (gap корпуса/поиска).
  E (LLM)          — сбой на стороне модели/валидатора.

Не трогает корпус, не требует внешних зависимостей (только стандартная библиотека).

Запуск (PowerShell):
  .\\.venv\\Scripts\\python.exe scripts\\asu_june_bot_diagnose_refusals.py
  .\\.venv\\Scripts\\python.exe scripts\\asu_june_bot_diagnose_refusals.py --path data\\asu_june_bot\\chat_runs.jsonl --examples 5
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

DEFAULT_PATH = "data/asu_june_bot/chat_runs.jsonl"

NO_ANSWER_STATUSES = {"no_answer", "no_sources"}
LLM_FAIL_STATUSES = {"llm_empty_response", "validation_failed", "llm_error", "search_error"}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def pick(row, *paths, default=None):
    """Вернуть первое непустое значение по списку путей вида 'a.b.c'."""
    for path in paths:
        cur = row
        ok = True
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok and cur is not None:
            return cur
    return default


def deep_find(obj, key):
    """Рекурсивный поиск первого значения по ключу — резерв, если структура отличается."""
    if isinstance(obj, dict):
        if key in obj and obj[key] is not None:
            return obj[key]
        for value in obj.values():
            found = deep_find(value, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = deep_find(value, key)
            if found is not None:
                return found
    return None


def extract(row):
    query = pick(row, "query", "request.query", "response.query") or deep_find(row, "query")
    status = pick(row, "status", "response.status") or deep_find(row, "status")

    guard = pick(
        row,
        "search.guard.decision",
        "response.search.guard.decision",
        "guard.decision",
        "guard_decision",
    )
    if guard is None:
        g = deep_find(row, "guard")
        if isinstance(g, dict):
            guard = g.get("decision")
        guard = guard or deep_find(row, "guard_decision")

    retrieval_called = pick(
        row,
        "search.diagnostics.search_service.retrieval_called",
        "response.search.diagnostics.search_service.retrieval_called",
        "diagnostics.search_service.retrieval_called",
        "retrieval_called",
    )
    if retrieval_called is None:
        retrieval_called = deep_find(row, "retrieval_called")
    if retrieval_called is None:
        search_status = pick(row, "search_status", "search.status", "response.search.status")
        # ChatRunsLogger stores a compact flat record. In that shape retrieval is implied
        # by search_status=ok; guard clarify/refuse records have no retrieval stage.
        if search_status is not None:
            retrieval_called = str(search_status).lower() == "ok"

    prompt_sources = pick(row, "prompt_sources", "diagnostics.prompt_sources", "response.diagnostics.prompt_sources")
    primary = pick(
        row,
        "search.context.primary_sources",
        "response.search.context.primary_sources",
        "context.primary_sources",
    )
    if prompt_sources is None and isinstance(primary, list):
        prompt_sources = len(primary)
    if prompt_sources is None:
        sources = pick(row, "sources", "response.sources")
        if isinstance(sources, list):
            prompt_sources = len(sources)

    llm_called = pick(row, "llm_called", "diagnostics.llm_called", "response.diagnostics.llm_called")
    if llm_called is None:
        llm_called = deep_find(row, "llm_called")

    return {
        "query": query,
        "status": (status or "").lower() or None,
        "guard": (guard or "").lower() or None,
        "retrieval_called": bool(retrieval_called) if retrieval_called is not None else None,
        "sources": int(prompt_sources) if isinstance(prompt_sources, (int, float)) else None,
        "llm_called": bool(llm_called) if llm_called is not None else None,
    }


def classify(e):
    g = e["guard"] or ""
    st = e["status"] or ""
    src = e["sources"] or 0
    if st == "answered":
        return "answered"
    if g in {"refuse", "refused"}:
        return "A_guard_refuse"
    if g == "clarify":
        return "A_guard_clarify"
    if st in LLM_FAIL_STATUSES:
        return "E_llm_side"
    if st in NO_ANSWER_STATUSES:
        return "B_threshold_with_sources" if src > 0 else "C_retrieval_miss"
    return "other"


BUCKET_LABELS = {
    "answered": "answered (ответ дан)",
    "A_guard_refuse": "ПУТЬ А: guard refuse (до retrieval)",
    "A_guard_clarify": "ПУТЬ А: guard clarify (до retrieval)",
    "B_threshold_with_sources": "ПУТЬ Б: порог обнулил при наличии источников",
    "C_retrieval_miss": "C: retrieval пуст (gap корпуса/поиска)",
    "E_llm_side": "E: сбой LLM/валидатора",
    "other": "прочее",
}
BUCKET_ORDER = [
    "A_guard_refuse",
    "A_guard_clarify",
    "B_threshold_with_sources",
    "C_retrieval_miss",
    "E_llm_side",
    "answered",
    "other",
]


def main():
    parser = argparse.ArgumentParser(description="Разбор отказов Asu June Bot по chat_runs.jsonl")
    parser.add_argument("--path", default=DEFAULT_PATH, help="Путь к chat_runs.jsonl")
    parser.add_argument("--examples", type=int, default=5, help="Сколько примеров запросов печатать на бакет")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        raise SystemExit(f"Файл не найден: {path}")

    rows, parse_errors = [], 0
    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                parse_errors += 1

    if not rows:
        raise SystemExit("В файле нет валидных JSON-строк.")

    extracted = [extract(r) for r in rows]

    # 1. Проверка, что извлечение полей сработало (по первой строке).
    first = extracted[0]
    print("=" * 78)
    print("ПРОВЕРКА СХЕМЫ (первая строка). Если поле = None — пути в extract() надо поправить.")
    for k in ("query", "status", "guard", "retrieval_called", "sources", "llm_called"):
        val = first[k]
        if k == "query" and isinstance(val, str):
            val = val[:60] + ("..." if len(val) > 60 else "")
        print(f"  {k:18s}: {val}")
    print(f"  строк всего: {len(rows)} | parse_errors: {parse_errors}")

    # 2. Распределение по статусам и guard.
    print("=" * 78)
    print("STATUS:")
    for st, n in Counter(e["status"] for e in extracted).most_common():
        print(f"  {str(st):28s} {n:5d}")
    print("GUARD DECISION:")
    for g, n in Counter(e["guard"] for e in extracted).most_common():
        print(f"  {str(g):28s} {n:5d}")

    # 3. Главный сплит по механизму отказа.
    buckets = Counter(classify(e) for e in extracted)
    total = len(extracted)
    print("=" * 78)
    print("МЕХАНИЗМ (где именно теряется ответ):")
    for b in BUCKET_ORDER:
        if buckets.get(b):
            n = buckets[b]
            print(f"  {BUCKET_LABELS[b]:48s} {n:5d}  ({n / total * 100:4.1f}%)")

    path_a = buckets.get("A_guard_refuse", 0) + buckets.get("A_guard_clarify", 0)
    path_b = buckets.get("B_threshold_with_sources", 0)
    print("-" * 78)
    print(f"  ИТОГО ПУТЬ А (guard, чинится в guardrails):      {path_a:5d}")
    print(f"  ИТОГО ПУТЬ Б (порог, чинится в context/threshold): {path_b:5d}")

    # 4. Кросс-таб: guard x retrieval_called x есть_источники x status.
    print("=" * 78)
    print("КРОСС-ТАБ  guard | retrieval | sources | status -> count")
    cross = Counter()
    for e in extracted:
        src_bucket = ">0" if (e["sources"] or 0) > 0 else "0"
        cross[(e["guard"], e["retrieval_called"], src_bucket, e["status"])] += 1
    for (g, rc, sb, st), n in cross.most_common(25):
        print(f"  {str(g):10s} | rc={str(rc):5s} | src={sb:>2s} | {str(st):22s} -> {n:5d}")

    # 5. Примеры запросов по проблемным бакетам.
    if args.examples > 0:
        print("=" * 78)
        print(f"ПРИМЕРЫ ЗАПРОСОВ (до {args.examples} на бакет):")
        for b in ("A_guard_clarify", "A_guard_refuse", "B_threshold_with_sources", "C_retrieval_miss"):
            samples = [e["query"] for e in extracted if classify(e) == b and e["query"]][: args.examples]
            if samples:
                print(f"\n  [{BUCKET_LABELS[b]}]")
                for q in samples:
                    print(f"    - {q[:100]}")
    print("=" * 78)


if __name__ == "__main__":
    main()
