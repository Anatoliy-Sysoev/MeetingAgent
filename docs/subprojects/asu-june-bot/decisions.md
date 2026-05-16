# Решения Project Knowledge Bot

Обновлено: 2026-05-16.

## ADR-001. Выделить Project Knowledge Bot как отдельный подпроект

Дата: 2026-05-12.

Решение: развитие project-only чат-бота выделяется в отдельный подпроект.

Причина:

- базовый репозиторий шире: RAG, встречи, транскрибация, протоколы, документы;
- бот по проектной документации требует отдельной архитектуры: guard, router, source policy, retrieval, citations, validator, eval;
- старый `scripts/09_chat.py` начал становиться монолитом.

Следствие:

- `scripts/09_chat.py` остается legacy/prototype;
- новая реализация ведётся модульно в `src/asu_june_bot/`;
- документация подпроекта хранится в `docs/subprojects/asu-june-bot/`;
- подпроект готовится к выделению в отдельный репозиторий.

## ADR-002. Не использовать Dify/RAGFlow как основное ядро MVP

Дата: 2026-05-12.

Решение: локальный MVP строится как собственный Python/FastAPI backend, а не как конфигурация Dify/RAGFlow.

Причина:

- нужен не универсальный «чат с файлами», а управляемый project-only RAG/Chat сервис;
- нужны строгие статусы, source policy, точные пункты, diagnostics и eval;
- готовые платформы можно использовать как reference/lab, но не как основной runtime MVP.

Следствие:

- MVP: FastAPI + локальный индекс + Ollama;
- OpenWebUI допускается как UI-оболочка позже;
- RAGFlow/Dify не смешиваются с основным индексом.

## ADR-003. Все LLM-вызовы через OpenAI-compatible API

Дата: 2026-05-12.

Решение: LLM-клиент проектируется через OpenAI-compatible интерфейс.

Текущий runtime:

```text
Ollama local
qwen2.5:7b-instruct
```

Не использовать как default:

```text
qwen3:4b
qwen3:8b
```

Причина:

- `qwen2.5:7b-instruct` прошла CLI/API smoke для Chat MVP;
- `qwen3:4b` вернула `llm_empty_response / finish_reason=length` даже с `/no_think`;
- `qwen3:8b` давала timeout/обрыв на локальном CPU runtime;
- OpenAI-compatible adapter сохраняет путь миграции на GPU/vLLM.

Следствие:

- бизнес-логика зависит от `LLMClient`, а не от Ollama-specific API;
- модель может задаваться в request/config;
- Ollama-specific параметры держатся в adapter.

## ADR-004. Статусы ответа должны быть строгими

Дата: 2026-05-12.

Решение: использовать явные статусы поиска и чата.

Search statuses:

```text
ok
refused
clarify
error
```

Chat statuses:

```text
answered
refused
clarify
no_sources
llm_error
llm_empty_response
validation_failed
```

Причина:

- нельзя считать пустой ответ LLM успешным;
- нельзя смешивать отказ guard, отсутствие источников и техническую ошибку;
- eval требует стабильных статусов.

Следствие:

- `llm_empty_response` не превращается в `answered`;
- `validation_failed` не скрывается как успешный ответ;
- `refused/clarify` не вызывают LLM.

## ADR-005. Нет источников — нет ответа

Дата: 2026-05-12.

Решение: бот не отвечает по общим знаниям модели.

Правило:

```text
Если релевантные источники не найдены, содержательная генерация не допускается.
```

Причина:

- режим project-only требует проверяемости;
- общие знания модели могут противоречить локальным документам;
- для аналитика важнее трассируемость, чем правдоподобный ответ.

Следствие:

- каждый `answered` должен иметь sources и citations;
- ответ без citations считается дефектом;
- отказ/уточнение возвращаются без вызова LLM.

## ADR-006. Source type обязателен для качества поиска

Дата: 2026-05-12.

Решение: каждый chunk должен иметь `source_type`.

Default indexed source types:

```text
project_doc
meeting_artifact
analytical_note
instruction
```

Не входят в основной project-only индекс:

```text
code
runtime_export
system_export
unknown
```

Причина:

- технические выгрузки и код могут вытеснять проектные документы;
- для разных вопросов нужны разные источники;
- future RBAC и аудит требуют контроля происхождения данных.

## ADR-007. Query expansion хранить в конфигурации, не в коде

Дата: 2026-05-12.

Решение: словари расширения запроса должны храниться в конфигурации.

Причина:

- термины предметной области будут меняться;
- добавление термина не должно требовать изменения Python-кода;
- аналитик должен иметь возможность редактировать словарь без разработки.

## ADR-008. Eval обязателен до развития UI

Дата: 2026-05-12; актуализировано 2026-05-16.

Решение: до UI нужен baseline по guard/search/chat.

Причина:

- без eval улучшения субъективны;
- нужно видеть, где ошибка: guard, retrieval, reranker, context, LLM, validator;
- source filter и parent expansion нельзя внедрять вслепую.

Следствие:

- QH-1 добавляет `chat_runs.jsonl`, `eval/cases/base.jsonl`, `asu_june_bot_chat_eval.py`;
- QH-2 source quality filter начинается только после baseline;
- QH-3 parent expansion начинается только после оценки QH-2.

## ADR-009. Не индексировать технические выгрузки в основном project-only корпусе

Дата: 2026-05-13.

Решение: папки и файлы технических выгрузок исключаются из основного корпуса.

Исключаются:

```text
**/Система/**
**/asu_docs_export/**
**/asu_admin_export/**
**/docs_html/**
**/docs_text/**
**/pages_html/**
**/pages_text/**
**/site_review_runs/**
**/playwright/**
**/exports/**
**/screenshots/**
**/*.har
```

Причина:

- это runtime/system exports, а не нормативная проектная документация;
- они создают шумные chunks;
- они ухудшают поиск по ФТТ/архитектуре/проектным решениям/интеграциям.

Следствие:

- `system_export` не входит в default corpus;
- при необходимости нужен отдельный `system_export_corpus`.

## ADR-010. Локальный config.yaml обновлять через Python, а не PowerShell-литералы с русскими путями

Дата: 2026-05-13.

Решение: локальная настройка `config.yaml` выполняется Python-скриптом.

Причина:

- PowerShell-файл с русским путём в значении по умолчанию ломался из-за кодировки;
- `config.yaml` локальный и не хранится в GitHub;
- нужно безопасно обновлять `project_root`, include/exclude lists и backups.

Следствие:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_apply_config_v2_1.py --project-root "C:\Users\Сотрудник\Desktop\!Проектные документы АСУ"
```

Старый PowerShell-путь не считать основным способом настройки.

## ADR-011. DOCX/XLSX extraction должен сохранять табличную структуру

Дата: 2026-05-13.

Решение: extraction v2.1 сохраняет таблицы как `table` и `table_row` blocks с `headers` и `cells`.

Причина:

- значительная часть требований и интеграционных спецификаций находится в таблицах;
- одна строка таблицы часто соответствует требованию, потоку, роли, атрибуту или сценарию;
- точные ссылки требуют `table_id`, `row_id`, `headers`, `cells`.

Следствие:

- chunking строит child chunks по строкам таблиц;
- eval должен проверять точные требования и табличные строки.

## ADR-012. Embeddings cache v2 мониторится отдельным watchdog

Дата: 2026-05-13.

Решение: долгий этап `--embed-only` мониторится отдельной задачей Windows Task Scheduler.

Причина:

- embeddings cache на CPU может строиться десятки часов;
- cache resumable по `chunk_id`;
- monitor не должен трогать живой Python/Ollama процесс.

Следствие:

```text
monitor_asu_june_bot_index_v2.ps1
register_asu_june_bot_index_v2_watchdog.ps1
```

## ADR-013. Search Quality v2.2: LLM получает не raw top-k, а подготовленный context

Дата: 2026-05-15.

Решение: между retrieval и LLM-ответом обязателен слой:

```text
QueryIntent -> PostReranker -> ContextBuilder
```

Причина:

- raw hybrid top-k может содержать шум;
- LLM не должен сам решать, какие chunks считать primary;
- exact requirement lookup и overview-запросы требуют разной сборки context.

Следствие:

- `/search` и CLI возвращают `primary_sources`, `supporting_sources`, `excluded_sources`;
- `/chat` использует только `primary_sources + supporting_sources`.

## ADR-014. ProjectGuard v2 вместо бесконечного расширения OUT_OF_SCOPE_MARKERS

Дата: 2026-05-15.

Решение: защита project-only режима строится как segmentation-based pipeline:

```text
QuerySegmenter -> RuleBasedScopeClassifier -> ScopeAggregator -> GuardPolicy -> ProjectGuard
```

Причина:

- один общий словарь out-of-scope не масштабируется;
- mixed-scope запросы могут содержать валидную и невалидную части;
- простая логика `есть проектный маркер -> allow` опасна.

Следствие:

- guard запускается до retrieval;
- `refused/clarify` не вызывают retrieval;
- guard regression suite обязателен.

## ADR-015. API Search должен повторять CLI search_v2 pipeline

Дата: 2026-05-15.

Решение: `POST /search` является thin HTTP adapter над `SearchService`.

Причина:

- дублирование CLI/API логики приведёт к расхождениям;
- reusable `SearchService` нужен для CLI, API и ChatService.

Статус:

```text
Реализовано
```

## ADR-016. ChatService — единая orchestration-точка для CLI и API chat

Дата: 2026-05-15.

Решение: `ChatService` является единственной бизнес-логикой chat-ответа.

Причина:

- `POST /chat` не должен дублировать guard/retrieval/context/generation;
- CLI и API должны давать одинаковую логику ответа;
- тесты должны проверять `ChatService` отдельно от FastAPI.

Следствие:

- `scripts/asu_june_bot_chat.py` использует `ChatService`;
- `src/asu_june_bot/api/routes_chat.py` использует `ChatService`;
- `ChatService` вызывает `SearchService`.

Статус:

```text
Реализовано
```

## ADR-017. qwen2.5:7b-instruct — рекомендуемая chat-модель MVP

Дата: 2026-05-15.

Решение: для MVP использовать `qwen2.5:7b-instruct` как рекомендуемую chat-модель.

Причина:

- дала `answered` на project smoke;
- `finish_reason=stop`;
- `validation_errors=[]`;
- qwen3 модели нестабильны на текущем CPU/Ollama runtime.

Следствие:

- default model в API/CLI — `qwen2.5:7b-instruct`;
- qwen3 остаётся для экспериментов, но не для MVP default.

## ADR-018. ChatRunsLogger и eval baseline до source quality filter

Дата: 2026-05-16.

Решение: сначала реализуется QH-1 Observability + Eval Baseline, затем source quality filter.

Причина:

- без baseline нельзя доказать, что filter улучшил качество;
- parent expansion может раздуть prompt;
- фактические failures должны определять следующий шаг.

Следствие:

- `ChatRunsLogger` пишет `data/asu_june_bot/chat_runs.jsonl`;
- `scripts/asu_june_bot_chat_eval.py` формирует baseline reports;
- QH-2 стартует только после анализа baseline.

## ADR-019. Semantic/factual validation не входит в MVP как hard-fail

Дата: 2026-05-16.

Решение: на текущем MVP semantic/factual validation не блокирует ответ.

Причина:

- deterministic structural checks уже работают;
- LLM-as-judge/NLI добавят сложность и latency;
- пока нужен baseline и ручная разметка спорных ответов.

Следствие:

- semantic warnings могут появиться позже;
- hard-fail по groundedness не внедряется до накопления dataset;
- golden answers используются как manual-review reference.
