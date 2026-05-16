# Список Задач

Обновлено: 2026-05-15.

## Сейчас

### Приоритет 1. Asu June Bot POST /chat

Asu June Bot v2.1/v2.2 доведён до CLI Chat MVP.

Закрыто:

```text
corpus/chunks/index/health/search готовы
Search Quality v2.2 готов
ProjectGuard v2 готов
SearchService готов
FastAPI /health и /search готовы
API Search MVP smoke пройден
ChatService готов
CLI scripts/asu_june_bot_chat.py готов
Chat MVP smoke пройден на qwen2.5:7b-instruct
chunks_v2 = 31302
indexed_chunks = 31285
embedding_model = bge-m3
vector_ready = true
bm25_ready = true
ProjectGuard v2 regression = 45 cases
false_allow = 0
ChatService tests = 7 passed
```

Финальные отчёты:

```text
docs/subprojects/asu-june-bot/smoke_report_project_guard_v2.md
docs/subprojects/asu-june-bot/smoke_report_search_service_commit1.md
docs/subprojects/asu-june-bot/smoke_report_api_search_mvp.md
docs/subprojects/asu-june-bot/smoke_report_chat_mvp.md
```

Рекомендуемая chat-модель MVP:

```text
qwen2.5:7b-instruct
```

Не использовать как default для Chat MVP:

```text
qwen3:4b
qwen3:8b
```

Причины:

```text
qwen3:4b -> llm_empty_response / finish_reason=length даже с /no_think
qwen3:8b -> timeout/обрыв на локальном CPU runtime
```

Следующий практический шаг:

```text
POST /chat
```

Сделать:

- [ ] Добавить `src/asu_june_bot/api/routes_chat.py`.
- [ ] Подключить route в `src/asu_june_bot/api/app.py`.
- [ ] Использовать существующий `ChatService`, без дублирования логики.
- [ ] Добавить API request/response models для `/chat`.
- [ ] Добавить API tests:
  - [ ] project query -> `answered` на mock LLM;
  - [ ] refused query -> LLM не вызывается;
  - [ ] clarify query -> LLM не вызывается;
  - [ ] empty LLM -> `llm_empty_response`.
- [ ] Добавить PowerShell smoke для `/chat`.
- [ ] Обновить `RUNBOOK_V2.md`.

Ключевое правило:

```text
/search не должен генерировать осмысленный ответ.
/search возвращает sources/context.
/chat генерирует осмысленный ответ по context.
```

`POST /chat` должен быть thin API adapter над `ChatService`.

### Приоритет 2. Chat quality hardening

После `POST /chat`:

- [ ] Добавить `tests/asu_june_bot/chat_eval_cases.jsonl`.
- [ ] Добавить `scripts/asu_june_bot_chat_eval.py`.
- [ ] Добавить `chat_runs.jsonl` для накопления dataset.
- [ ] Добавить ручную разметку good/bad для ответов.
- [ ] Добавить source quality filter для слишком коротких chunks.
- [ ] Добавить parent expansion для heading/UML/caption chunks.
- [ ] Рассмотреть `NO_ANSWER` status.
- [ ] Рассмотреть DSPy Lab только как research/lab, не runtime MVP.

### Приоритет 3. Search / Retrieval hardening

После первого `/chat`:

- [ ] Улучшить metadata extraction/chunking для `requirement_id`, `mentioned_requirement_ids`, `contract_section`, `document_version`.
- [ ] Добавить search eval cases для exact section lookup, document overview, integration overview, cross-document traceability.
- [ ] Добавить runner для search eval.
- [ ] Добавить source links через `data/asu_june_bot/source_links.json`.
- [ ] Рассмотреть дедупликацию семейств интеграций.

## Статус Asu June Bot v2.1/v2.2

Готово:

- независимый pipeline v2.1: `apply_config_v2_1 -> extract_text_v2 -> chunks_v2 -> audit_sources_v2 -> build_index_v2 -> health_v2 -> search_v2`;
- `Система`, `asu_docs_export`, `asu_admin_export`, `site_review_runs`, `playwright`, `exports`, `.har`, временные файлы, медиа и архивы исключены из основного корпуса;
- extraction/chunking v2.1 пройдены: `documents=213`, `blocks=31076`, `chunks=31302`;
- `system_export` отсутствует в основном корпусе;
- `embeddings_cache_v2` собран: `cached_after=31285`, `missing_after=0`;
- `numpy_index_v2` собран: `index_built=true`, `index_count=31285`, `embedding_dim=1024`;
- `health_v2`: `status=ok`, `vector_ready=true`, `bm25_ready=true`, `ollama_available=true`, `embedding_model_installed=true`;
- `QueryIntent` реализован;
- `PostReranker` реализован;
- `ContextBuilder` реализован;
- `ProjectGuard v2` реализован;
- guard regression suite: `45 cases`, `false_allow=0`;
- `SearchService` реализован;
- CLI `search_v2` работает через `SearchService`;
- FastAPI `GET /health` и `POST /search` реализованы;
- API Search MVP smoke пройден;
- `ChatService` реализован;
- CLI `scripts/asu_june_bot_chat.py` реализован;
- Chat MVP smoke пройден на `qwen2.5:7b-instruct`.

## Ограничение Chat MVP

Текущий `AnswerValidator` выполняет structural validation, но не semantic/factual validation.

Проверяется:

```text
пустой ответ
наличие sources
наличие ссылок [Sx]
unknown citations
external knowledge markers
answer length
citation density / coverage
```

Не проверяется:

```text
поддерживается ли каждое утверждение конкретным source text;
не сделала ли модель спорный вывод из короткого UML/heading/caption chunk;
нет ли semantic hallucination при формально корректных [Sx].
```

Это quality debt, а не blocker для добавления `POST /chat`.

## Статус старого RAG / Meeting pipeline

- Использовать `docs/product/PROJECT_STAGES_AND_FTT.md` как основной список этапов и ФТТ для движения по продукту.
- Использовать numpy-поиск как основной стабильный локальный RAG-поиск v1.
- Считать `scripts/09_chat.py` prototype project-only чата, не основной архитектурой Asu June Bot.
- Использовать `configs/schemas/meeting.schema.json` как контракт `FTT-MA-09` для всех будущих обработчиков встреч.
- Использовать `scripts/06_transcribe_meeting.py` как минимальный offline CLI для одной встречи.
- Использовать `scripts/08_process_meeting_pipeline.py` как первый оконный offline-pipeline для готовой записи.
- Использовать `docs/architecture/MEETING_ARTIFACTS_PIPELINE.md` как целевую архитектуру итогов встречи.
- Использовать `scripts/07_generate_meeting_artifacts.py` как первый генератор `summarized`-состояния встречи, но считать `extractive` только скаффолдом контракта.

## Далее

- Добавить API `POST /chat`.
- Добавить markdown smoke-отчеты после каждого важного среза retrieval/API/chat.
- Добавить инкрементальный `update_rag.ps1` для новых, измененных и удаленных документов.
- В `update_rag.ps1` обязательно обработать deletion: удаленные и попавшие под `exclude_path_patterns` документы должны исчезать из актуального индекса.
- Добавить watcher/скрипт загрузки встреч из `watched_folder/` поверх уже готового `06_transcribe_meeting.py`.
- Для future: добавить source links через `data/asu_june_bot/source_links.json`.
- Для future: рассмотреть Qdrant только после стабилизации numpy index/API Search/Chat API.

## Когда Вернуться

- Рассмотреть WhisperX, если появится UI с timeline или потребуется diarization.
- Рассмотреть pyannote 3.1 как основной путь diarization, когда дойдем до `FTT-MA-10` live-сессий или UI с timeline.
- Опционально добавить FAISS/Qdrant поверх того же формата metadata, если numpy станет медленным на большем корпусе.

## Продуктовые Следующие Шаги

- Использовать `docs/product/PRODUCT_VISION_AND_PLAN.md` как основную карту продукта.
- Использовать `docs/product/PROJECT_STAGES_AND_FTT.md` как рабочий чек-лист: этап -> ФТТ -> артефакт -> критерий готовности.
- Использовать `docs/subprojects/asu-june-bot/architecture.md`, `mvp.md`, `roadmap.md`, `todo.md`, `RUNBOOK_V2.md` и smoke-отчёты как основной план реализации AI-агента.
- Позже добавить политику обновления схемы в код: при появлении `schema_version = 2` нужен явный скрипт миграции.
- Для UI сначала рассмотреть OpenWebUI как оболочку над локальным API, но не подключать его до появления стабильного project-only `/chat`.

## Известные Риски

- Metadata `section/requirement_id` пока шумит на табличных chunks.
- ChromaDB локально нестабилен на загрузке HNSW-индекса, поэтому не должен быть критической зависимостью для поиска.
- Сгенерированные документы требуют строгого ревью источников.
- `qwen3:8b` на CPU может быть слишком медленным для интерактивного чата при большом prompt.
- `qwen3:4b` может вернуть пустой `response` без HTTP-ошибки; такой случай должен считаться отказом `llm_empty_response`, а не успешным ответом.
- Structural validation не ловит все semantic hallucinations.

## Восстановление Контекста В Новом Треде

Используй prompt:

```text
Прочитай README.md, AGENTS.md, docs/context.md, docs/todo.md и git log --oneline -10. Восстанови контекст проекта и предложи следующий шаг.
```

Для Asu June Bot используй prompt:

```text
Прочитай README.md, AGENTS.md, docs/context.md, docs/todo.md и все файлы docs/subprojects/asu-june-bot/. Восстанови контекст подпроекта Asu June Bot и предложи следующий практический шаг.
```
