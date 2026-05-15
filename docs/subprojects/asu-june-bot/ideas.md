# Ideas / Research Backlog — Asu June Bot

Обновлено: 2026-05-15.

## Назначение

Документ фиксирует идеи, которые полезны для Asu June Bot, но не должны попадать в текущий MVP без отдельной проверки. Цель — не раздувать локальный CPU-first контур и не превращать `search_v2` / `/chat` в монолит.

## Основной вывод по анализу external answers

Для текущего MVP не нужно внедрять тяжёлую guardrails-платформу. Нужно развить собственный маленький guard-пайплайн:

```text
Segmenter -> PerSegmentScopeClassifier -> Aggregator -> Policy -> ProjectGuard
```

Это закрывает главную проблему mixed-scope запросов: запрос может содержать одновременно проектную часть и внепроектную просьбу. Простая логика `есть проектный маркер -> allow` недостаточна. Нужна логика:

```text
allow = есть проектный scope И нет внепроектного scope
refuse_mixed_scope = есть проектный scope И есть внепроектный scope
refuse_out_of_scope = нет проектного scope И есть внепроектный scope
clarify = scope неясен
```

## В MVP / CPU-first

### 1. Segmentation-based ProjectGuard v2

Статус: включить в ближайший MVP.

Суть:

- разбивать запрос на предложения / clauses;
- классифицировать каждый сегмент независимо;
- агрегировать результат;
- запускать retrieval только если все значимые сегменты `in_project` или `meta`;
- если есть `out_of_project`, отказывать или просить уточнение.

Минимальная структура:

```text
src/asu_june_bot/guardrails/models.py
src/asu_june_bot/guardrails/segmenter.py
src/asu_june_bot/guardrails/scope_classifier.py
src/asu_june_bot/guardrails/aggregator.py
src/asu_june_bot/guardrails/policy.py
src/asu_june_bot/guardrails/project_guard.py
```

CPU-оценка:

- нормально работает на CPU;
- rule-based классификация быстрая;
- LLM не нужен для fast path.

### 2. Rule-based fast path

Статус: включить в MVP.

Суть:

- использовать regex / keyword паттерны для `PROJECT_MARKERS`, `OUT_OF_PROJECT_MARKERS`, `GENERATION_VERBS`, `CODE_NOUNS`;
- отдельно обрабатывать границу `вопрос по проектной технологии` vs `просьба написать произвольный код`;
- не использовать только OR-логику.

Ключевое правило:

```text
Если в сегменте есть project marker и out-of-project marker -> segment = mixed/ambiguous.
Если в запросе есть in_project segment и out_of_project segment -> refuse_mixed_scope.
```

CPU-оценка:

- полностью CPU-friendly;
- без новых внешних сервисов.

### 3. Deterministic Aggregator + Policy

Статус: включить в MVP.

Суть:

- `Aggregator` — чистая функция над сегментами;
- `Policy` решает `allow`, `refuse`, `clarify`, `meta_response`;
- вся логика тестируется без LLM и без retrieval.

Рекомендуемая политика MVP:

```text
pure in_project -> allow
pure out_of_project -> refuse
mixed_scope high confidence -> refuse_with_explanation
mixed_scope low confidence -> request_clarification
ambiguous -> request_clarification
```

CPU-оценка:

- полностью CPU-friendly.

### 4. Pytest guard suite

Статус: включить в MVP до `/chat`.

Минимальные категории:

```text
pure_in_project
pure_out_of_project
mixed_scope_weather
mixed_scope_code
mixed_scope_jailbreak
ambiguous
project_tech_vs_general_code
```

Обязательные проверки:

```text
refuse -> retrieval_called == False
mixed_scope -> status == refused или clarify
in_project -> retrieval_called == True
```

CPU-оценка:

- полностью CPU-friendly;
- критично для регрессионной защиты.

### 5. Structured guard logs

Статус: включить в MVP.

Логировать:

```text
query_hash
raw_query
segments
segment_scope
matched_markers
guard_decision
guard_reason
retrieval_called
latency_ms
```

CPU-оценка:

- полностью CPU-friendly.

## Можно развернуть локально как research/lab

### 1. semantic-router

Статус: research/lab, не основная зависимость MVP.

Зачем смотреть:

- локальная semantic routing классификация на embeddings;
- подходит для быстрых маршрутов `project`, `out_of_scope`, `coding`, `weather`, `chitchat`, `jailbreak`;
- может заменить или усилить rule-based classifier после MVP.

Как использовать в лаборатории:

```text
routes/project_docs
routes/general_coding
routes/weather
routes/chitchat
routes/jailbreak
routes/meta
```

Ожидаемая польза:

- меньше ручных regex;
- лучше ловит перефразированные out-of-scope запросы;
- работает до retrieval.

CPU-оценка:

- должно работать локально на CPU, если использовать local encoder / текущий bge-m3 через существующий embeddings client или легкий локальный encoder;
- требует отдельного benchmark на latency.

Риск:

- добавляет зависимость и слой конфигурации;
- может ошибаться на узких проектных терминах без curated route examples.

Решение:

- не внедрять в основной MVP;
- сделать отдельный эксперимент `guard_semantic_router_lab` после API Search.

### 2. instructor + pydantic для LLM fallback

Статус: research/lab, можно подготовить после API Search.

Зачем смотреть:

- structured JSON из Qwen/Ollama;
- полезно для ambiguous segment fallback;
- уменьшает риск битого JSON от локальной LLM.

CPU-оценка:

- библиотека лёгкая;
- сам fallback через Qwen на CPU может быть медленным, поэтому только для ambiguous cases;
- обязательно нужен SQLite cache по hash(segment).

Решение:

- не использовать в fast path;
- добавить как optional fallback после того, как rule-based/semantic-router покажут свои границы.

### 3. RAGAS / DeepEval

Статус: research/lab, затем evaluation track.

Зачем смотреть:

- автоматическая оценка context relevancy, faithfulness, answer relevancy;
- полезно для regression reports по `/search` и `/chat`.

CPU-оценка:

- вычисление метрик может требовать LLM judge;
- на CPU будет медленно, если запускать много кейсов;
- можно запускать редко и маленькими наборами.

Решение:

- не блокировать MVP;
- сначала сделать собственные deterministic pytest asserts;
- RAGAS/DeepEval — после появления `/chat`.

### 4. Guardrails AI

Статус: research/lab, не MVP.

Зачем смотреть:

- input/output validation;
- декларативные validators;
- может быть полезен для output guard: запрет ответов без источников, запрет внепроектного кода.

CPU-оценка:

- сама библиотека не тяжёлая;
- validators, которые требуют LLM, будут медленными на CPU;
- integration overhead выше, чем у текущего кастомного guard.

Решение:

- не подключать до API Search;
- рассмотреть для output guard после первого `/chat`.

## За пределами MVP

### 1. NVIDIA NeMo Guardrails

Статус: за пределами MVP, enterprise/research track.

Почему интересно:

- input/dialog/retrieval/output rails;
- Colang для явных диалоговых потоков;
- защита от jailbreak/prompt injection;
- подходит для domain-specific assistants и RAG с fact-checking/output moderation.

Почему не сейчас:

- добавляет DSL, конфигурации и отдельный runtime layer;
- может быть избыточен до стабилизации собственного `/search` и `/chat`;
- потребует времени на изучение Colang и интеграцию.

CPU-оценка:

- сам framework можно запустить локально;
- guardrails на LLM/self-check будут медленными на CPU;
- практично оценивать после появления GPU или после стабилизации API.

Решение:

- оставить как `enterprise-hardening` после MVP;
- сделать отдельный PoC позже: `nemo_guardrails_lab`.

### 2. LlamaGuard / ShieldGemma

Статус: за пределами MVP, GPU-preferred.

Почему интересно:

- специализированные guard-модели;
- могут лучше ловить jailbreak/safety/forbidden requests.

Почему не сейчас:

- отдельная модель рядом с Qwen и bge-m3;
- на CPU может быть медленно;
- не решает всю project-only специфику без собственной таксономии проекта.

Решение:

- записать как идею для GPU migration / enterprise hardening;
- не включать в локальный CPU-first MVP.

### 3. Fine-tuned intent classifier / SetFit / sentence-transformers classifier head

Статус: за пределами MVP до появления датасета.

Почему интересно:

- быстрый inference;
- можно обучить на реальных запросах;
- лучше ручных regex на больших объёмах.

Почему не сейчас:

- нет размеченного датасета 200–500 запросов;
- fine-tuning без данных создаст ложное чувство качества.

Решение:

- сначала логировать guard decisions и собирать dataset;
- вернуться после 2–4 недель реального использования.

### 4. RAGFlow / Dify / AnythingLLM как основной backend

Статус: за пределами MVP как production replacement.

Почему интересно:

- готовые UI и ingestion workflows;
- RAGFlow может быть полезен как лаборатория качества парсинга PDF/таблиц;
- Dify/AnythingLLM полезны как референсы UX и knowledge-base workflows.

Почему не сейчас:

- текущий проект уже имеет собственный extraction/chunking/index/search v2.1;
- перенос в готовую платформу усложнит контроль source policy, guard policy и traceability;
- есть риск потерять точную трассировку ФТТ/ЦТА/ПР/ПМИ.

Решение:

- не использовать как backend MVP;
- RAGFlow можно поднять отдельно как ingestion/chunking lab, если появится задача сравнить качество таблиц/PDF.

### 5. LangGraph / agentic RAG

Статус: за пределами MVP.

Почему интересно:

- удобен для state machine и сложных многошаговых workflows;
- может пригодиться для будущего multi-turn dialog и tool orchestration.

Почему не сейчас:

- текущий бот не должен быть агентом общего назначения;
- пока достаточно линейного pipeline;
- agentic orchestration повышает риск выхода за рамки project-only.

Решение:

- не внедрять до стабилизации `/search`, `/chat`, guard logs и eval.

## Итоговое решение

### Берём сейчас

```text
Segmenter
RuleBasedScopeClassifier
Aggregator
Policy
ProjectGuard v2
pytest guard suite
structured guard logs
```

### Проверяем локально потом

```text
semantic-router lab
instructor + pydantic для ambiguous LLM fallback
RAGAS / DeepEval для evaluation
Guardrails AI для output validation
```

### Оставляем за пределами MVP

```text
NVIDIA NeMo Guardrails
LlamaGuard / ShieldGemma
fine-tuned classifier
RAGFlow/Dify/AnythingLLM как основной backend
LangGraph / agentic RAG
```

## Следующий практический шаг

После прохождения текущего mixed-scope smoke перейти к реализации `ProjectGuard v2`:

```text
guardrails/models.py
guardrails/segmenter.py
guardrails/scope_classifier.py
guardrails/aggregator.py
guardrails/policy.py
guardrails/project_guard.py
```

Сразу добавить pytest-набор:

```text
tests/asu_june_bot/test_project_guard_v2.py
```

Минимальный критерий готовности:

```text
pure in_project -> allow
pure out_of_project -> refuse
mixed weather -> refuse
mixed code/game -> refuse
ambiguous -> clarify
project technical question -> allow
arbitrary code generation -> refuse
retrieval_called == False при refuse/clarify
```
