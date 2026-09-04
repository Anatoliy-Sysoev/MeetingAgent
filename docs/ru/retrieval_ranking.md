# Ранжирование Retrieval

[English](../en/retrieval_ranking.md) | [Русский](retrieval_ranking.md)

## Назначение

Project Knowledge Bot ранжирует источники до любого вызова LLM. Этот слой
должен тестироваться независимо: неверно выбранный источник нельзя надёжно
исправить более качественным prompt или model.

Детерминированный путь:

1. классифицировать query intent;
2. посчитать BM25 base score и policy adjustments;
3. объединить BM25 и vector scores по выбранной fusion policy;
4. применить post-rerank policies;
5. разложить sources по primary, supporting и excluded context buckets.

`src/asu_june_bot/retrieval/ranking_policies.py` содержит именованные policies,
а `ranking_signals.py` — переиспользуемые structural predicates. BM25 и
post-rerank только оркестрируют эти компоненты и не владеют customer vocabulary.

## Ranking Profile

Публичные defaults лежат в
`configs/asu_june_bot/ranking_profile.yaml`. Приватная или customer-specific
терминология хранится только в ignored-файле
`configs/asu_june_bot/ranking_profile.local.yaml`.

Local YAML является deep overlay. Если local-файл задаёт list, он заменяет весь
публичный list этой группы: сохраните все default markers, которые всё ещё
нужны. Profile валидируется при старте; неверные имена групп, non-string
значения, дубликаты, слишком длинные значения и неподдерживаемая версия
отклоняются fail-closed.

Не добавляйте реальные customer names, corpus paths, queries или excerpts
документов в публичный profile и тесты.

## Diagnostics

Каждая корректировка score сохраняет:

- stage (`bm25` или `post_rerank`);
- policy и стабильный label;
- multiplier;
- score до и после корректировки;
- версию ranking profile.

Hybrid results также содержат выбранную fusion policy и веса vector/BM25.
Diagnostics объясняют ranking behavior, но не являются authorization boundary
и не должны содержать private paths или полный source content.

## Regression И Coverage Gates

`tests/fixtures/retrieval/ranking_characterization.jsonl` — ограниченный public
synthetic baseline поведения. Перед намеренным изменением ranking сначала
обновите этот evidence-файл. Policy tests отдельно покрывают positive, negative
и penalty branches.

Запуск retrieval-only gate:

```powershell
python scripts/48_retrieval_coverage.py
```

Команда работает без Ollama, сети и LLM calls и контролирует module/group
branch-coverage thresholds для ranking core и source routing. Канонический
`scripts/46_ci_verify.py` запускает этот gate после полного test suite.
