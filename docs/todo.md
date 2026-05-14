# Список Задач

Обновлено: 2026-05-14.

## Сейчас

### Приоритет 1. Asu June Bot Search Quality v2.2

Asu June Bot v2.1 технически собран до уровня локального search MVP:

```text
corpus/chunks/index/health/search готовы
chunks_v2 = 31302
indexed_chunks = 31285
embedding_model = bge-m3
vector_ready = true
bm25_ready = true
```

Но к Chat MVP переходить рано: raw hybrid top-k всё ещё содержит vector-only noise для обзорных вопросов.

Следующий практический шаг:

```text
query_intent -> post_rerank -> context_builder -> diagnostics -> smoke_report
```

Сделать:

- [ ] `src/asu_june_bot/retrieval/query_intent.py`.
- [ ] `src/asu_june_bot/retrieval/post_rerank.py`.
- [ ] `src/asu_june_bot/retrieval/context_builder.py`.
- [ ] Добавить в `search_v2 --json`: `query_intent`, `rerank_labels`, `primary_sources`, `supporting_sources`.
- [ ] Повторить smoke по вопросам:
  - `Что входит в Паспорт ИС?`
  - `Какие интеграции заявлены в проекте?`
  - `ФТТ 4.2.5 НОВАДОК ЭЦП`
  - очевидный внепроектный вопрос.
- [ ] Обновить `docs/subprojects/asu-june-bot/search_smoke_report_2026-05-14.md` или создать новый smoke-отчет v2.2.

Критерий перехода к API Search:

- `Паспорт ИС overview` не забит таблицей ПО и поддержкой;
- `Интеграции` возвращают ЦТА/Паспорт/ФТТ/СоИ как primary/supporting sources;
- `ФТТ 4.2.5` возвращает ФТТ с НОВАДОК/ЭЦП как primary source;
- JSON содержит diagnostics;
- в LLM-контекст не попадает критический vector-only noise.

### Приоритет 2. API Search

После Search Quality v2.2:

```text
src/asu_june_bot/api/app.py
src/asu_june_bot/api/routes_search.py
```

Endpoints:

```text
GET /health
POST /search
```

Не начинать `/chat`, пока `/search` не возвращает `primary_sources` и `supporting_sources`.

### Приоритет 3. Chat MVP

После стабильного API Search:

- [ ] `ProjectGuard`.
- [ ] `PromptBuilder`.
- [ ] `LLMClient` через OpenAI-compatible API.
- [ ] `AnswerValidator`.
- [ ] `ResponseFormatter`.
- [ ] CLI `scripts/asu_june_bot_chat.py`.
- [ ] Затем локальный API `/chat`.

Правило: не отправлять raw hybrid top-k напрямую в LLM.

## Статус Asu June Bot v2.1

Готово:

- независимый pipeline v2.1: `apply_config_v2_1 -> extract_text_v2 -> chunks_v2 -> audit_sources_v2 -> build_index_v2 -> health_v2 -> search_v2`;
- `Система`, `asu_docs_export`, `asu_admin_export`, `site_review_runs`, `playwright`, `exports`, `.har`, временные файлы, медиа и архивы исключены из основного корпуса;
- extraction/chunking v2.1 пройдены: `documents=213`, `blocks=31076`, `chunks=31302`;
- `system_export` отсутствует в основном корпусе;
- `embeddings_cache_v2` собран: `cached_after=31285`, `missing_after=0`;
- `numpy_index_v2` собран: `index_built=true`, `index_count=31285`, `embedding_dim=1024`;
- `health_v2`: `status=ok`, `vector_ready=true`, `bm25_ready=true`, `ollama_available=true`, `embedding_model_installed=true`;
- smoke-отчет сохранен: `docs/subprojects/asu-june-bot/search_smoke_report_2026-05-14.md`.

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

- После Search Quality v2.2 реализовать API `/search`.
- После API `/search` реализовать Chat MVP.
- Добавить markdown smoke-отчеты после каждого важного среза retrieval.
- Улучшить metadata extraction/chunking для:
  - `requirement_id`;
  - `mentioned_requirement_ids`;
  - `contract_section`;
  - `document_version`.
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
- Использовать `docs/product/PROJECT_ONLY_CHATBOT_MVP.md` как дорожную карту project-only чат-бота.
- Использовать `docs/subprojects/asu-june-bot/architecture.md`, `mvp.md`, `roadmap.md`, `todo.md`, `RUNBOOK_V2.md` и `search_smoke_report_2026-05-14.md` как основной план реализации AI-агента.
- Позже добавить политику обновления схемы в код: при появлении `schema_version = 2` нужен явный скрипт миграции.
- Для UI сначала рассмотреть OpenWebUI как оболочку над локальным API, но не подключать его до появления project-only guardrail.

## Известные Риски

- Raw hybrid top-k может содержать vector-only noise.
- Обзорные вопросы требуют document-overview retrieval, а не обычный top-k.
- Metadata `section/requirement_id` пока шумит на табличных chunks.
- ChromaDB локально нестабилен на загрузке HNSW-индекса, поэтому не должен быть критической зависимостью для поиска.
- Сгенерированные документы требуют строгого ревью источников.
- Project-only отказ по одному `score_threshold` может быть слишком мягким или слишком жестким; порог нужно подобрать на smoke-наборе.
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
