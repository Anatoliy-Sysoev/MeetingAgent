# Список задач

Обновлено: 2026-05-16.

## Сейчас

### Приоритет 1. Project Knowledge Bot — QH-1 baseline

Project Knowledge Bot v2.1/v2.2 доведён до API Chat MVP. Следующий практический шаг — локально прогнать QH-1 regression и baseline eval.

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
FastAPI POST /chat готов
API Chat MVP smoke пройден
QH-1 Observability + Eval Baseline реализован в коде
product documentation обновлена
chunks_v2 = 31302
indexed_chunks = 31285
embedding_model = bge-m3
vector_ready = true
bm25_ready = true
ProjectGuard v2 false_allow = 0
ChatService tests = 7 passed
```

Финальные отчёты:

```text
docs/subprojects/asu-june-bot/smoke_report_project_guard_v2.md
docs/subprojects/asu-june-bot/smoke_report_search_service_commit1.md
docs/subprojects/asu-june-bot/smoke_report_api_search_mvp.md
docs/subprojects/asu-june-bot/smoke_report_chat_mvp.md
docs/subprojects/asu-june-bot/smoke_report_api_chat_mvp.md
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
QH-1 baseline eval
```

Сделать локально:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\chat\test_chat_service.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_health.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_search_smoke.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\api\test_chat_smoke.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\observability\test_chat_runs.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\eval\test_checks.py -q
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\eval\test_runner.py -q
.\.venv\Scripts\python.exe scripts\asu_june_bot_chat_eval.py --cases eval\cases\base.jsonl --label baseline --model qwen2.5:7b-instruct --top-k 5
```

Ожидаемо:

```text
eval/reports/*__baseline.json
eval/reports/*__baseline.md
```

Важно:

```text
baseline может быть ниже 100%
это не ошибка
цель — измерить текущее качество, а не подогнать кейсы
```

## Приоритет 2. QH-2 Source Quality Filter

После baseline:

- [ ] Проанализировать failures в eval report.
- [ ] Выделить проблемы short_source_trap / UML / heading / caption chunks.
- [ ] Добавить `src/asu_june_bot/retrieval/source_quality.py`.
- [ ] Добавить unit tests для weak chunks.
- [ ] Интегрировать source quality в `ContextBuilder`.
- [ ] Повторно прогнать eval с label `with_source_filter`.
- [ ] Сравнить baseline vs with_source_filter.

Принцип:

```text
не удалять chunks из индекса
не ломать retrieval
помечать / понижать weak chunks в context stage
фиксировать reason в diagnostics
```

## Приоритет 3. QH-3 Parent Expansion

Делать только если QH-2 не устранил проблему коротких chunks.

- [ ] Спроектировать parent expansion с max chars.
- [ ] Добавить dedup parent context.
- [ ] Не расширять все chunks подряд.
- [ ] Сравнить eval до/после.

## Статус Project Knowledge Bot v2.1/v2.2

Готово:

- независимый pipeline v2.1: `apply_config_v2_1 -> extract_text_v2 -> chunks_v2 -> audit_sources_v2 -> build_index_v2 -> health_v2 -> search_v2`;
- технические выгрузки, временные файлы, медиа и архивы исключены из основного корпуса;
- extraction/chunking v2.1 пройдены: `documents=213`, `blocks=31076`, `chunks=31302`;
- `system_export` отсутствует в основном корпусе;
- `embeddings_cache_v2` собран: `cached_after=31285`, `missing_after=0`;
- `numpy_index_v2` собран: `index_built=true`, `index_count=31285`, `embedding_dim=1024`;
- `health_v2`: `status=ok`, `vector_ready=true`, `bm25_ready=true`, `ollama_available=true`, `embedding_model_installed=true`;
- `QueryIntent`, `PostReranker`, `ContextBuilder` реализованы;
- `ProjectGuard v2` реализован, `false_allow=0`;
- `SearchService` реализован;
- CLI `search_v2` работает через `SearchService`;
- FastAPI `GET /health`, `POST /search`, `POST /chat` реализованы;
- `ChatService`, `PromptBuilder`, `LLMClient`, `AnswerValidator`, `ResponseFormatter` реализованы;
- `ChatRunsLogger` и `EvalRunner` реализованы.

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
поддерживается ли каждое утверждение конкретным source text
не сделала ли модель спорный вывод из короткого UML/heading/caption chunk
нет ли semantic hallucination при формально корректных [Sx]
```

Это quality debt. Не решать его вслепую до baseline.

## Статус старого RAG / Meeting pipeline

- Использовать `docs/product/PROJECT_STAGES_AND_FTT.md` как основной список этапов и требований для общего MeetingAgent.
- Использовать numpy-поиск как основной стабильный локальный RAG-поиск v1.
- Считать `scripts/09_chat.py` legacy/prototype project-only чата, не основной архитектурой Project Knowledge Bot.
- Использовать `configs/schemas/meeting.schema.json` как контракт `FTT-MA-09` для будущих обработчиков встреч.
- Использовать `scripts/06_transcribe_meeting.py` как минимальный offline CLI для одной встречи.
- Использовать `scripts/08_process_meeting_pipeline.py` как первый оконный offline-pipeline для готовой записи.
- Использовать `docs/architecture/MEETING_ARTIFACTS_PIPELINE.md` как целевую архитектуру итогов встречи.
- Использовать `scripts/07_generate_meeting_artifacts.py` как первый генератор `summarized`-состояния встречи, но считать `extractive` только скаффолдом контракта.

## Далее по общему MeetingAgent

- Добавить инкрементальный `update_rag.ps1` для новых, измененных и удаленных документов.
- В `update_rag.ps1` обязательно обработать deletion: удаленные и попавшие под `exclude_path_patterns` документы должны исчезать из актуального индекса.
- Добавить watcher/скрипт загрузки встреч из `watched_folder/` поверх уже готового `06_transcribe_meeting.py`.
- Для future: добавить source links через `data/asu_june_bot/source_links.json`.
- Для future: рассмотреть Qdrant только после стабилизации numpy index/API Search/Chat API.

## Когда вернуться

- Рассмотреть WhisperX, если появится UI с timeline или потребуется diarization.
- Рассмотреть pyannote 3.1 как основной путь diarization, когда дойдем до live-сессий или UI с timeline.
- Опционально добавить FAISS/Qdrant поверх того же формата metadata, если numpy станет медленным на большем корпусе.

## Продуктовые следующие шаги

- Использовать `docs/product/PRODUCT_VISION_AND_PLAN.md` как основную карту общего MeetingAgent.
- Использовать `docs/product/PROJECT_STAGES_AND_FTT.md` как рабочий чек-лист: этап -> требование -> артефакт -> критерий готовности.
- Использовать `docs/subprojects/asu-june-bot/architecture.md`, `mvp.md`, `roadmap.md`, `todo.md`, `RUNBOOK_V2.md` и smoke-отчёты как основной план реализации Project Knowledge Bot.
- Позже добавить политику обновления схемы в код: при появлении `schema_version = 2` нужен явный скрипт миграции.
- Для UI сначала рассмотреть OpenWebUI как оболочку над локальным API, но не подключать его до baseline eval и QH-2.

## Известные риски

- Metadata `section/requirement_id` пока может шуметь на табличных chunks.
- ChromaDB локально нестабилен на загрузке HNSW-индекса, поэтому не должен быть критической зависимостью для поиска.
- Сгенерированные документы требуют строгого ревью источников.
- `qwen3:8b` на CPU может быть слишком медленным для интерактивного чата при большом prompt.
- `qwen3:4b` может вернуть пустой `response` без HTTP-ошибки; такой случай должен считаться `llm_empty_response`, а не успешным ответом.
- Structural validation не ловит все semantic hallucinations.

## Восстановление контекста в новом треде

Для общего MeetingAgent:

```text
Прочитай README.md, AGENTS.md, docs/context.md, docs/todo.md и git log --oneline -10. Восстанови контекст проекта и предложи следующий шаг.
```

Для Project Knowledge Bot:

```text
Прочитай README.md, AGENTS.md, docs/context.md, docs/todo.md и все активные файлы docs/subprojects/asu-june-bot/. Восстанови контекст подпроекта Project Knowledge Bot и предложи следующий практический шаг.
```
