# Список Задач

Обновлено: 2026-05-15.

## Сейчас

### Приоритет 1. Asu June Bot Chat MVP

Asu June Bot v2.1/v2.2 доведён до API Search MVP.

Закрыто:

```text
corpus/chunks/index/health/search готовы
Search Quality v2.2 готов
ProjectGuard v2 готов
SearchService готов
FastAPI /health и /search готовы
API smoke пройден
chunks_v2 = 31302
indexed_chunks = 31285
embedding_model = bge-m3
vector_ready = true
bm25_ready = true
ProjectGuard v2 regression = 45 cases
false_allow = 0
```

Финальные отчёты:

```text
docs/subprojects/asu-june-bot/smoke_report_project_guard_v2.md
docs/subprojects/asu-june-bot/smoke_report_search_service_commit1.md
docs/subprojects/asu-june-bot/smoke_report_api_search_mvp.md
```

Следующий практический шаг:

```text
Chat MVP
```

Сделать:

- [ ] Зафиксировать `docs/subprojects/asu-june-bot/chat_mvp_design.md`.
- [ ] Реализовать `src/asu_june_bot/chat/models.py`.
- [ ] Реализовать `src/asu_june_bot/chat/prompt_builder.py`.
- [ ] Реализовать `src/asu_june_bot/llm/client.py`.
- [ ] Реализовать OpenAI-compatible Ollama client.
- [ ] Реализовать `src/asu_june_bot/chat/service.py`.
- [ ] Реализовать `AnswerValidator`.
- [ ] Реализовать `ResponseFormatter`.
- [ ] Добавить CLI `scripts/asu_june_bot_chat.py`.
- [ ] Добавить smoke tests.
- [ ] Создать smoke report Chat MVP.

Ключевое правило:

```text
/search не должен генерировать осмысленный ответ.
/search возвращает sources/context.
/chat генерирует осмысленный ответ по context.
```

Chat MVP должен использовать `SearchService`, а не дублировать retrieval/guard/context.

Дополнительно:

- [ ] После API Search MVP синхронизировать `docs/subprojects/asu-june-bot/product/` с фактической реализацией API.

### Приоритет 2. Search / Retrieval hardening

После первого Chat MVP:

- [ ] Улучшить metadata extraction/chunking для `requirement_id`, `mentioned_requirement_ids`, `contract_section`, `document_version`.
- [ ] Добавить search eval cases для exact section lookup, document overview, integration overview, cross-document traceability.
- [ ] Добавить runner для search eval после появления API.
- [ ] Добавить source links через `data/asu_june_bot/source_links.json`.
- [ ] Рассмотреть дедупликацию семейств интеграций.

### Приоритет 3. API /chat

После стабильного CLI Chat MVP:

- [ ] Добавить API `POST /chat`.
- [ ] Добавить API tests.
- [ ] Добавить PowerShell smoke-команды.
- [ ] Обновить `RUNBOOK_V2.md`.

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
- API smoke пройден.

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

- После Chat MVP добавить API `POST /chat`.
- Добавить markdown smoke-отчеты после каждого важного среза retrieval/API/chat.
- Добавить инкрементальный `update_rag.ps1` для новых, измененных и удаленных документов.
- В `update_rag.ps1` обязательно обработать deletion: удаленные и попавшие под `exclude_path_patterns` документы должны исчезать из актуального индекса.
- Добавить watcher/скрипт загрузки встреч из `watched_folder/` поверх уже готового `06_transcribe_meeting.py`.
- Для future: добавить source links через `data/asu_june_bot/source_links.json`.
- Для future: рассмотреть Qdrant только после стабилизации numpy index/API Search.

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

- `/search` возвращает источники, а не осмысленный ответ; это нормально до реализации Chat MVP.
- Metadata `section/requirement_id` пока шумит на табличных chunks.
- ChromaDB локально нестабилен на загрузке HNSW-индекса, поэтому не должен быть критической зависимостью для поиска.
- Сгенерированные документы требуют строгого ревью источников.
- `qwen3:8b` на CPU может быть слишком медленным для интерактивного чата при большом prompt.
- `qwen3:4b` может вернуть пустой `response` без HTTP-ошибки; такой случай должен считаться отказом `llm_empty_response`, а не успешным ответом.

## Восстановление Контекста В Новом Треде

Используй prompt:

```text
Прочитай README.md, AGENTS.md, docs/context.md, docs/todo.md и git log --oneline -10. Восстанови контекст проекта и предложи следующий шаг.
```

Для Asu June Bot используй prompt:

```text
Прочитай README.md, AGENTS.md, docs/context.md, docs/todo.md и все файлы docs/subprojects/asu-june-bot/. Восстанови контекст подпроекта Asu June Bot и предложи следующий практический шаг.
```
