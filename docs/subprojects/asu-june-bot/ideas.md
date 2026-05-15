# Ideas / Research Backlog — Asu June Bot

Обновлено: 2026-05-15.

## Назначение

Документ фиксирует идеи, которые полезны для Asu June Bot, но не должны попадать в текущий MVP без отдельной проверки. Цель — не раздувать локальный CPU-first контур и не превращать `search_v2`, `/search` или `/chat` в монолит.

## Текущий вывод после ProjectGuard v2

Ранее рассматривался риск бесконечного расширения `OUT_OF_SCOPE_MARKERS`. Решение найдено и реализовано: **ProjectGuard v2**.

Реализованный guard-пайплайн:

```text
Segmenter -> PerSegmentScopeClassifier -> Aggregator -> Policy -> ProjectGuard
```

Финальный regression результат:

```json
{
  "total": 44,
  "passed": 44,
  "failed": 0,
  "false_allow": 0,
  "false_refuse": 0,
  "false_clarify": 0
}
```

Следствие:

- ProjectGuard v2 больше не является research-идеей — это runtime-компонент MVP.
- Следующий этап — API Search MVP.
- Внешние guardrails-фреймворки не подключаются в runtime MVP.

## Уже реализовано в MVP / CPU-first

### 1. Segmentation-based ProjectGuard v2

Статус: реализовано.

Суть:

- разбивает запрос на предложения / clauses;
- классифицирует каждый сегмент независимо;
- агрегирует результат;
- запускает retrieval только если запрос разрешён;
- отказывает на `out_of_project` и `mixed`;
- возвращает `clarify` для ambiguous.

Файлы:

```text
src/asu_june_bot/guardrails/models.py
src/asu_june_bot/guardrails/segmenter.py
src/asu_june_bot/guardrails/scope_classifier.py
src/asu_june_bot/guardrails/aggregator.py
src/asu_june_bot/guardrails/policy.py
src/asu_june_bot/guardrails/project_guard.py
```

### 2. Rule-based fast path

Статус: реализовано как deterministic CPU-first слой.

Суть:

- regex / keyword patterns для project/out/meta/generation/security/jailbreak;
- отдельная обработка коротких технических маркеров `AD`, `API`, `БД`, `ИБ`, чтобы они не срабатывали внутри слов;
- отдельная граница `вопрос по проектной технологии` vs `просьба написать произвольный код`;
- отказ до retrieval при mixed/out-of-project.

### 3. Deterministic Aggregator + Policy

Статус: реализовано.

Правила MVP:

```text
pure in_project -> allow
pure out_of_project -> refuse
mixed_scope -> refuse
ambiguous -> clarify
```

### 4. Pytest guard suite

Статус: реализовано.

Файлы:

```text
tests/asu_june_bot/test_project_guard_v2.py
tests/asu_june_bot/guard_v2_cases.jsonl
tests/asu_june_bot/test_project_guard_v2_cases.py
scripts/asu_june_bot_guard_v2_eval.py
```

Критерий:

```text
false_allow = 0
```

### 5. Structured guard diagnostics

Статус: реализовано в JSON-ответе `search_v2`.

Доступно:

```text
guard.guard_v2.aggregate.segments[]
```

Показывает segment text, scope, confidence, matched markers и labels.

## Можно развернуть локально как research/lab

### 1. semantic-router

Статус: research/lab, не основная зависимость MVP.

Зачем смотреть:

- локальная semantic routing классификация на embeddings;
- маршруты `project`, `out_of_scope`, `coding`, `weather`, `chitchat`, `jailbreak`;
- может заменить или усилить rule-based classifier после MVP.

Когда вернуться:

- после API Search;
- если rule-based ProjectGuard v2 начнёт давать много false_refuse/false_clarify на реальных запросах;
- если появится набор 100–200 размеченных guard-запросов.

CPU-оценка:

- возможно локально на CPU при лёгком encoder;
- с bge-m3 через Ollama может быть медленно для каждого запроса;
- нужен benchmark latency.

Решение:

- не внедрять в основной MVP;
- сделать отдельный эксперимент `guard_semantic_router_lab` после API Search.

### 2. instructor + pydantic для LLM fallback

Статус: research/lab после API Search.

Зачем смотреть:

- structured JSON из Qwen/Ollama;
- fallback для ambiguous segments;
- уменьшает риск битого JSON от локальной LLM.

CPU-оценка:

- библиотека лёгкая;
- LLM fallback на CPU может быть медленным;
- нужен SQLite cache по hash(segment).

Решение:

- не использовать в fast path;
- добавить как optional fallback только после стабилизации API Search.

### 3. RAGAS / DeepEval

Статус: research/lab, затем evaluation track.

Зачем смотреть:

- context relevancy;
- faithfulness;
- answer relevancy;
- regression reports по `/search` и `/chat`.

CPU-оценка:

- метрики с LLM judge будут медленными на CPU;
- можно запускать редко и маленькими наборами.

Решение:

- сначала собственные deterministic pytest asserts;
- RAGAS/DeepEval — после появления `/chat`.

### 4. Guardrails AI

Статус: research/lab, не MVP.

Зачем смотреть:

- output validation;
- декларативные validators;
- запрет ответов без источников;
- запрет внепроектного кода в ответе.

CPU-оценка:

- сама библиотека не тяжёлая;
- LLM validators на CPU будут медленными;
- integration overhead выше, чем у текущего кастомного guard.

Решение:

- не подключать до API Search;
- рассмотреть после первого `/chat` как output guard.

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
- текущий ProjectGuard v2 уже закрыл MVP-критерий `false_allow = 0`;
- LLM/self-check rails на CPU будут медленными.

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
- не решает project-only специфику без собственной таксономии проекта.

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
- перенос в готовую платформу усложнит source policy, guard policy и traceability;
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

### Уже взяли в MVP

```text
Segmenter
RuleBasedScopeClassifier
Aggregator
Policy
ProjectGuard v2
pytest guard suite
guard eval runner
structured guard diagnostics
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

Переход к API Search MVP:

```text
src/asu_june_bot/api/app.py
src/asu_june_bot/api/routes_health.py
src/asu_june_bot/api/routes_search.py
```

Минимальный критерий готовности:

```text
GET /health работает
POST /search работает
POST /search повторяет CLI search_v2 JSON semantics
refused/clarify не запускают retrieval
project queries возвращают primary/supporting context
```
