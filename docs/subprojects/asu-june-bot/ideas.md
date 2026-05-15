# Ideas / Research Backlog — Asu June Bot

Обновлено: 2026-05-15.

## Назначение

Документ фиксирует идеи, которые полезны для Asu June Bot, но не должны попадать в текущий MVP без отдельной проверки. Цель — не раздувать локальный CPU-first контур и не превращать `search_v2`, `/search` или `/chat` в монолит.

## Текущий вывод после анализа внешнего ревью Chat MVP

Внешние ответы по Chat MVP сходятся в нескольких позициях:

```text
оставить линейный pipeline SearchService -> PromptBuilder -> LLMClient -> AnswerValidator -> ResponseFormatter;
не делать монолит и не дублировать retrieval/guard/context внутри ChatService;
LLM не вызывается при refused/clarify/no_sources;
LLM получает только primary_sources + supporting_sources;
excluded_sources не попадают в prompt;
ответ без источников не считается answered;
пустой ответ LLM не считается answered;
для MVP достаточно deterministic validation, без LLM-judge/NLI;
до POST /chat сначала стабилизировать CLI Chat MVP.
```

Что решено внедрять сейчас:

```text
Context budget / truncation в PromptBuilder;
явная разметка primary/supporting sources в prompt;
temperature=0.0 по умолчанию;
более строгий AnswerValidator: unknown citations, external phrases, length, citation density, citation coverage;
дополнительные unit tests для context budget и unknown citations.
```

Что решено не внедрять сейчас, а оставить в backlog:

```text
JSON-mode structured output;
S0 / formal no_answer contract;
1 retry на no_citations/invalid_json;
GroundedContext / GenerationGuard как отдельные классы;
LLM-as-judge;
NLI / sentence-to-source groundedness;
multi-turn / query condensation;
streaming/SSE;
telemetry dashboard;
LangGraph / Dify / RAGFlow / NeMo Guardrails.
```

## Реализовано по итогам ревью Chat MVP

### 1. Context budget / truncation

Статус: реализовано.

Файл:

```text
src/asu_june_bot/chat/prompt_builder.py
```

Решение:

- `PromptBuilder(max_sources=6, max_context_chars=9000, max_chars_per_source=1800)`;
- источники режутся по границе слова;
- суммарный prompt context ограничен;
- primary/supporting явно размечаются как `ОСНОВНОЙ ИСТОЧНИК` / `ДОПОЛНИТЕЛЬНЫЙ ИСТОЧНИК`;
- `excluded_sources` не передаются в LLM;
- diagnostics содержит `used_context_chars`, `selected_sources`, `skipped_by_budget`, `skipped_duplicate`, `skipped_empty`.

### 2. Deterministic mode для LLM

Статус: реализовано.

Файл:

```text
src/asu_june_bot/chat/models.py
```

Решение:

```text
ChatRequest.temperature = 0.0
```

Причина: для RAG по проектной документации нужна детерминированность, а не креативность.

### 3. Усиленный AnswerValidator

Статус: реализовано.

Файл:

```text
src/asu_june_bot/chat/answer_validator.py
```

Реализовано:

- извлечение ссылок `[S1]`, `[S1, S2]`;
- проверка unknown source references;
- проверка пустого/слишком короткого/слишком длинного ответа;
- блок-лист фраз внешнего знания;
- citation density для длинных ответов;
- citation coverage по предложениям;
- no-answer markers пока приводят к `validation_failed`, а не `answered`.

Важно: семантический groundedness не реализован. Validator пока подтверждает citation contract, а не фактическую истинность каждого утверждения.

## Backlog после внешнего ревью Chat MVP

### 1. JSON-mode structured output

Статус: идея / next hardening после CLI smoke.

Суть:

Заставить LLM возвращать JSON вида:

```json
{
  "answer": "текст ответа с [S1]",
  "sources": ["S1"],
  "insufficient": false
}
```

Плюсы:

- меньше неоднозначности parsing;
- проще deterministic validation;
- можно валидировать Pydantic-схемой.

Минусы / риски:

- нужно проверить, насколько стабильно текущая локальная модель в Ollama соблюдает JSON contract;
- OpenAI-compatible JSON mode у Ollama может отличаться по моделям и версиям;
- может ухудшить качество естественного ответа.

Решение:

- не включать до первого CLI smoke;
- сделать отдельный эксперимент `chat_json_mode_lab`;
- сравнить plain markdown vs JSON на 20 project questions.

### 2. Formal NO_ANSWER / S0 contract

Статус: идея / после первого smoke.

Суть:

Ввести отдельный статус:

```text
no_answer
```

или `insufficient_data`, если sources есть, но LLM честно говорит, что в них нет ответа.

Вариант prompt-contract:

```text
Если в источниках нет ответа, напиши ровно: "В переданных источниках данных недостаточно для ответа".
```

Риск:

- локальная модель может формулировать no-answer по-разному;
- расширение markers может стать новым раздуванием rules, если не собирать реальные логи.

Решение:

- пока no-answer markers приводят к `validation_failed`, не к `answered`;
- после smoke собрать реальные no-answer формулировки и решить, нужен ли отдельный `ChatStatus.NO_ANSWER`.

### 3. One retry

Статус: later после сбора статистики validation failures.

Суть:

Делать максимум 1 retry только при:

```text
missing_source_references
invalid JSON / unparsable structured output
empty answer
```

Не делать retry при:

```text
unknown citations
external knowledge markers
low citation density
low citation coverage
```

Причина:

- на CPU retry удваивает latency;
- retry может скрыть системную проблему prompt/validator;
- сначала нужны метрики причин validation_failed.

### 4. GroundedContext / GenerationGuard

Статус: later / refactor after smoke.

Суть:

Добавить отдельный промежуточный объект между `SearchResponse` и `PromptBuilder`:

```text
GroundedContext
  primary_sources
  supporting_sources
  citation_map
  budget_diagnostics
```

И отдельную проверку:

```text
GenerationGuard
  can_generate(search_response) -> yes/no/reason
```

Плюсы:

- ChatService станет тоньше;
- проще тестировать no_sources/budget/source mapping отдельно.

Решение:

- не делать до первого smoke, чтобы не рефакторить преждевременно;
- вернуться, если `ChatService` начнет разрастаться.

### 5. NLI / sentence-to-source groundedness

Статус: production hardening, не MVP.

Суть:

Проверять каждое утверждение ответа против цитируемого источника.

Почему не сейчас:

- нужна отдельная модель или второй LLM pass;
- latency на CPU вырастет кратно;
- без реальных диалогов невозможно настроить thresholds;
- возможны ложные отказы на валидные перефразированные ответы.

Решение:

- вернуться после 50–100 реальных диалогов;
- сначала оценить, сколько `answered` фактически галлюцинируют.

### 6. LLM-as-judge

Статус: production/lab, не MVP.

Плюсы:

- может ловить смысловые галлюцинации лучше regex;
- полезен для offline eval.

Минусы:

- удваивает latency;
- judge на той же модели может подтвердить собственную галлюцинацию;
- требует отдельного eval набора.

Решение:

- не использовать inline в Chat MVP;
- рассмотреть offline evaluation track после накопления smoke cases.

### 7. Multi-turn / Query condensation

Статус: later.

Суть:

Поддержка вопросов типа:

```text
А кто это утвердил?
А где это написано?
```

Почему не сейчас:

- текущий MVP должен быть single-turn;
- multi-turn требует ConversationStore и QueryCondensation перед SearchService;
- повышает риск неправильного scope carry-over.

Решение:

- явно считать Chat MVP single-turn;
- добавить multi-turn только после стабильного `/chat`.

### 8. Telemetry / validation logs

Статус: after CLI smoke, до расширенного пилота.

Идея:

Писать JSONL diagnostics:

```text
request_id
query
chat_status
search_status
prompt_sources
llm_model
llm_called
validation_errors
latency_ms
```

Польза:

- понять долю `validation_failed`;
- калибровать prompt и validator;
- увидеть топ причин отказов.

MVP-решение:

- пока diagnostics возвращается в JSON;
- после smoke добавить `chat_runs.jsonl` под флагом.

## Текущий вывод после анализа API Search MVP предложений

API Search MVP закрыт. Выбрана реализация через Service Layer:

```text
SearchService = единственная orchestration-точка
CLI = thin adapter
API = thin adapter
```

Финальный дизайн зафиксирован:

```text
docs/subprojects/asu-june-bot/api_search_mvp_design.md
```

Реализовано:

- `SearchService`;
- FastAPI `GET /health`;
- FastAPI `POST /search`;
- application factory;
- singleton AppState;
- request_id middleware;
- базовый error handling;
- unit test: `refused/clarify` не вызывают retrieval;
- API smoke tests.

## Уже реализовано в MVP / CPU-first

### 1. Segmentation-based ProjectGuard v2

Статус: реализовано.

Суть:

- разбивает запрос на предложения / clauses;
- классифицирует каждый сегмент независимо;
- агрегирует результат;
- запускает retrieval только если запрос разрешён;
- отказывает на `out_of_project` и `mixed`;
- возвращает `clarify` для ambiguous;
- блокирует `project + unknown tail` на уровне policy без раздувания marker DB.

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
project + unknown tail -> refuse
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

Статус: реализовано в JSON-ответе `search_v2` и `/search`.

Доступно:

```text
guard.guard_v2.aggregate.segments[]
```

Показывает segment text, scope, confidence, matched markers и labels.

## Можно реализовать позже после Chat MVP

### 1. CORS

Статус: после появления браузерного UI.

Решение:

- не включать в локальный API Search MVP;
- если потребуется UI, добавить `CORSMiddleware` с allow-list origins;
- не использовать `allow_origins=["*"]` для production.

### 2. Auth / API Key

Статус: после локального API MVP или перед внешним доступом.

Решение:

- для локального пилота можно без auth;
- перед публикацией API добавить dependency `require_api_key`;
- позже — OAuth/AD/Keycloak, если появится enterprise-сценарий.

### 3. OpenTelemetry / advanced observability

Статус: позже.

MVP:

- request_id;
- elapsed_ms;
- basic access log;
- diagnostics в ответе по флагу.

Позже:

- OpenTelemetry;
- metrics endpoint;
- traces;
- structured JSON logs.

### 4. structlog

Статус: optional позже.

Решение:

- MVP на stdlib logging;
- structlog можно добавить, если появится потребность в контекстных JSON-логах.

### 5. `/health/live`

Статус: позже.

Решение:

- основной MVP endpoint — `GET /health`;
- `/health/live` полезен для Docker/K8s/process manager;
- не блокирует Chat MVP.

### 6. Pagination / offset / limit

Статус: позже.

Решение:

- в MVP достаточно `top_k`;
- pagination нужна, если UI будет показывать много источников.

### 7. Admin endpoints

Статус: позже.

Возможные endpoints:

```text
POST /admin/reindex
GET /admin/stats
GET /admin/source-types
```

Решение:

- не делать до стабильного `/search` и `/chat`;
- обязательно защищать auth dependency.

### 8. Streaming / SSE

Статус: после базового `/chat`.

Решение:

- не делать в первой версии chat;
- сначала получить корректный non-streaming answer с citations.

### 9. OpenAI-compatible `/v1/chat/completions`

Статус: позже, если нужно подключение OpenWebUI/LibreChat/клиентов.

Решение:

- сначала собственный `/search` и `/chat`;
- затем adapter endpoint под OpenAI-compatible API.

### 10. MCP server для Codex

Статус: позже после API Search.

Идея:

```text
asu-june-bot-mcp
  search_project_docs(query, mode, top_k)
  get_source(chunk_id)
  health()
```

Решение:

- не делать до стабильного `/search` и `/chat`;
- API должен стать источником истины, MCP — только обёртка.

## Можно развернуть локально как research/lab

### 1. semantic-router

Статус: research/lab, не основная зависимость MVP.

Зачем смотреть:

- локальная semantic routing классификация на embeddings;
- маршруты `project`, `out_of_scope`, `coding`, `weather`, `chitchat`, `jailbreak`;
- может заменить или усилить rule-based classifier после MVP.

Когда вернуться:

- если rule-based ProjectGuard v2 начнёт давать много false_refuse/false_clarify на реальных запросах;
- если появится набор 100–200 размеченных guard-запросов.

CPU-оценка:

- возможно локально на CPU при лёгком encoder;
- с bge-m3 через Ollama может быть медленно для каждого запроса;
- нужен benchmark latency.

Решение:

- не внедрять в основной MVP;
- сделать отдельный эксперимент `guard_semantic_router_lab` после Chat MVP.

### 2. instructor + pydantic для LLM fallback

Статус: research/lab после Chat MVP.

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
- добавить как optional fallback только после стабилизации Chat MVP.

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

- не подключать до стабильного `/chat`;
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
