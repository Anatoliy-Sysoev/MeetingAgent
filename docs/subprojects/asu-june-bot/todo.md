# TODO Asu June Bot

Обновлено: 2026-05-15.

## Текущий статус v2.2

Asu June Bot v2.1 технически собран до уровня локального search MVP, а Search Quality v2.2 реализуется отдельными модулями, без превращения `search_v2` в монолит.

Готово:

- независимый pipeline v2.1: `apply_config_v2_1 -> extract_text_v2 -> chunks_v2 -> audit_sources_v2 -> build_index_v2 -> health_v2 -> search_v2`;
- основной корпус очищен от `Система`, `asu_docs_export`, `asu_admin_export`, `site_review_runs`, `playwright`, `exports`, `.har`, временных файлов и медиа/архивов;
- extraction/chunking v2.1 пройдены: `documents=213`, `blocks=31076`, `chunks=31302`;
- `system_export` отсутствует в основном корпусе;
- полный `embeddings_cache_v2` собран: `cached_after=31285`, `missing_after=0`, `embedding_model=bge-m3`, `max_embedding_chars=3000`;
- `numpy_index_v2` собран: `index_built=true`, `index_count=31285`, `embedding_dim=1024`;
- из индекса исключены `code` chunks: `chunks_skipped_by_source_type=17`;
- `search_v2` поддерживает `bm25`, `vector`, `hybrid`;
- добавлен `src/asu_june_bot/retrieval/query_intent.py`;
- добавлен `src/asu_june_bot/guardrails/project_guard.py`;
- добавлен `src/asu_june_bot/retrieval/post_rerank.py`;
- добавлен `src/asu_june_bot/retrieval/context_builder.py`;
- `scripts/asu_june_bot_search_v2.py` подключает `QueryIntent`, `ProjectGuard`, `PostReranker`, `ContextBuilder`;
- для явно внепроектных вопросов `search_v2` возвращает `status=refused`, пустой `results` и не выполняет retrieval;
- JSON-ответ `search_v2` содержит `query_intent`, `guard`, `rerank`, `context.primary_sources`, `context.supporting_sources`, `context.excluded_sources`.

## Проверенный smoke 2026-05-15

### Внепроектный вопрос

Запрос:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Какая погода завтра в Москве?" --mode hybrid --top-k 12 --json
```

Результат:

```text
status = refused
intent = out_of_scope_candidate
project_related = false
results = []
```

Вывод: ProjectGuard работает корректно.

### Паспорт ИС overview

Запрос:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Что входит в Паспорт ИС?" --mode hybrid --top-k 8 --json
```

Результат после первого PostReranker/ContextBuilder:

```text
primary_sources = 1
supporting_sources = 1
excluded_sources = 14
```

Хорошо:

- `primary_sources[0]` — корректный обзорный chunk `Границы описания` из `ЦП УПКС_Паспорт ИС_v1.3.2`;
- таблицы ПО PostgreSQL/РЕД ОС/АСУ-С ушли в `excluded_sources`;
- vector-only ПР и ЦТА не попали в primary.

Дефект:

- в `supporting_sources` попал chunk `Требования к квалификации и численности сотрудников, обслуживающих систему`, строка про поддержку приложения;
- для обзорного вопроса `Что входит в Паспорт ИС?` такой chunk не должен попадать в LLM-контекст.

Коррекция внесена:

- в `post_rerank.py` усилена функция `_is_software_or_support_table`;
- добавлены маркеры `поддержка приложения`, `устранение ошибок`, `доработка приложения`, `требования к квалификации и численности сотрудников`, `сотрудников, обслуживающих систему`, `роль | минимальные требования`;
- штраф для software/support chunks в `document_overview` усилен с `0.16` до `0.08`;
- устранено дублирование `rerank_labels` для overflow excluded chunks.

Требуется повторная проверка только по `Паспорт ИС overview`.

### Интеграции

Запрос:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Какие интеграции заявлены в проекте?" --mode hybrid --top-k 8 --json
```

Результат:

- `primary_sources` содержит ЦТА, Паспорт ИС, ФТТ, ЦТА/SIEM/S3;
- `supporting_sources` содержит дополнительные ФТТ/ЦТА chunks по КШД/SOAP, LDAP/SMTP, S3/Minio;
- результат пригоден для API Search MVP.

Замечание:

- `primary_sources` сейчас может содержать слишком много похожих ЦТА chunks по S3/Minio/SIEM;
- для Chat MVP позже нужна дедупликация по семейству интеграции, но для API Search MVP это не блокер.

## Что изменилось в ProjectGuard / QueryIntent

`QueryIntent` классифицирует запросы в минимальные intent:

```text
document_overview
integration_overview
requirement_lookup
general_project_question
out_of_scope_candidate
```

`ProjectGuard` принимает решение:

```text
allow
refuse
```

Правило MVP:

- если вопрос явно вне проекта и не содержит проектных маркеров, `search_v2` сразу возвращает отказ;
- если вопрос содержит проектные маркеры, retrieval разрешается;
- отказ не вызывает BM25/vector/hybrid и не возвращает случайные chunks.

## Что изменилось в PostReranker / ContextBuilder

`PostReranker` выполняет второй слой ранжирования после BM25/vector/hybrid:

- штрафует vector-only chunks для `document_overview` и `requirement_lookup`;
- штрафует software/support/front matter/glossary chunks;
- усиливает `Паспорт ИС` для обзорных вопросов по паспорту;
- усиливает ЦТА/Паспорт/СоИ/ФТТ для вопросов по интеграциям;
- усиливает ФТТ и exact section mentions для `requirement_lookup`;
- добавляет `rerank_labels` в diagnostics.

`ContextBuilder` разделяет результат на:

```text
primary_sources
supporting_sources
excluded_sources
```

Правило: LLM в будущем должен получать не raw top-k, а только подготовленный context.

## Следующий практический шаг

Подтянуть исправление и повторить smoke.

```powershell
cd C:\Users\Сотрудник\Desktop\AI\MeetingAgent
git pull
```

Проверить только два запроса:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Что входит в Паспорт ИС?" --mode hybrid --top-k 8 --json
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "ФТТ 4.2.5 НОВАДОК ЭЦП" --mode hybrid --top-k 8 --json
```

Проверить:

- Паспорт ИС: support/qualification/application support chunks не должны быть в `primary_sources` и `supporting_sources`;
- Паспорт ИС: обзорный chunk `Границы описания` должен оставаться в `primary_sources`;
- ФТТ 4.2.5: `primary_sources` должен содержать ФТТ с НОВАДОК/ЭЦП, ПР/встреча должны быть в `supporting_sources`.

## Следующие задачи разработки

### A. Search Quality v2.2

- [x] Добавить `src/asu_june_bot/retrieval/query_intent.py`.
- [x] Добавить `src/asu_june_bot/guardrails/project_guard.py`.
- [x] Подключить `QueryIntent` и `ProjectGuard` в `scripts/asu_june_bot_search_v2.py`.
- [x] Добавить `--no-guard` для диагностического retrieval без отказа.
- [x] Добавить `src/asu_june_bot/retrieval/post_rerank.py`.
- [x] Добавить `src/asu_june_bot/retrieval/context_builder.py`.
- [x] Добавить диагностику `rerank_labels`, `primary_sources`, `supporting_sources` в JSON-ответ `search_v2`.
- [x] Локально проверить ProjectGuard и часть baseline-вопросов.
- [x] Скорректировать support filtering для `document_overview`.
- [ ] Повторно проверить `Паспорт ИС overview` после support filtering.
- [ ] Проверить `ФТТ 4.2.5` после context builder.
- [ ] Создать markdown smoke-отчет v2.2.

### B. API Search

После Search Quality v2.2:

```text
src/asu_june_bot/api/app.py
src/asu_june_bot/api/routes_search.py
```

Endpoint:

```text
GET /health
POST /search
```

К API Search переходить только если:

- `Паспорт ИС overview` top/context не забит таблицей ПО или поддержкой;
- `Интеграции` возвращают ЦТА/Паспорт/ФТТ/СоИ;
- `ФТТ 4.2.5` возвращает ФТТ с НОВАДОК/ЭЦП в primary sources;
- внепроектный вопрос возвращает `status=refused` и `results=[]`;
- JSON содержит пригодные diagnostics.

### C. Chat MVP

После API Search:

- [ ] `PromptBuilder`.
- [ ] `LLMClient` через OpenAI-compatible API.
- [ ] `AnswerValidator`.
- [ ] `ResponseFormatter`.
- [ ] CLI `scripts/asu_june_bot_chat.py`.

## Рекомендуемые решения

- Qdrant пока не подключать; numpy index v2 достаточен для MVP.
- BM25 in-memory оставить до API Search; storage потребуется позже.
- `Система` не возвращать в основной corpus; при необходимости сделать отдельный `system_export_corpus`.
- Ссылки на Яндекс.Диск добавлять позже через `data/asu_june_bot/source_links.json`.
- До Chat MVP не делать fine-tuning, UI и agentic tool-use.

## Definition of Done для перехода к API Search

- `health_v2`: `status=ok`, `vector_ready=true`, `bm25_ready=true`.
- Внепроектный вопрос возвращает `status=refused` и не вызывает retrieval.
- Для каждого baseline-запроса есть primary sources.
- В JSON выдаче есть diagnostics по intent/rerank/context.
- В primary/supporting context нет критического шума, который может увести LLM в неверный ответ.
- Старые `data/chunks.jsonl`, `data/embeddings_cache.jsonl`, `data/numpy_index` не меняются.

## Не делать

- Не переходить к Chat MVP напрямую от текущего hybrid top-k.
- Не отправлять в LLM все top-8 как есть.
- Не индексировать `Система` в основной corpus.
- Не раздувать старый `scripts/09_chat.py`.
- Не делать UI до API Search.
