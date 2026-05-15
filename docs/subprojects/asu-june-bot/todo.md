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
- `scripts/asu_june_bot_health_v2.py` показывает `status=ok`, `bm25_ready=true`, `vector_ready=true`, `ollama_available=true`, `embedding_model_installed=true`;
- `search_v2` поддерживает `bm25`, `vector`, `hybrid`;
- `hybrid` умеет fallback на BM25 при недоступном Ollama;
- BM25 получил deterministic rerank: intent boosts по `Паспорт ИС`, `ФТТ`, интеграциям, exact section/requirement и штрафы для глоссариев/front matter/software tables;
- добавлен `src/asu_june_bot/retrieval/query_intent.py`;
- добавлен `src/asu_june_bot/guardrails/project_guard.py`;
- добавлен `src/asu_june_bot/retrieval/post_rerank.py`;
- добавлен `src/asu_june_bot/retrieval/context_builder.py`;
- `scripts/asu_june_bot_search_v2.py` подключает `QueryIntent`, `ProjectGuard`, `PostReranker`, `ContextBuilder`;
- для явно внепроектных вопросов `search_v2` возвращает `status=refused`, пустой `results` и не выполняет retrieval;
- добавлен диагностический флаг `--no-guard`, чтобы временно посмотреть retrieval без защиты;
- JSON-ответ `search_v2` теперь содержит `query_intent`, `guard`, `rerank`, `context.primary_sources`, `context.supporting_sources`, `context.excluded_sources`.

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

Проверочный пример:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Какая погода завтра в Москве?" --mode hybrid --top-k 12
```

Ожидаемо:

```text
status = refused
intent = out_of_scope_candidate
results = 0
```

Для диагностики retrieval без guard:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Какая погода завтра в Москве?" --mode hybrid --top-k 12 --no-guard
```

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

## Последний проверенный smoke до PostReranker/ContextBuilder

### Health

Проверка `scripts/asu_june_bot_health_v2.py` успешна:

```text
status = ok
vector_ready = true
bm25_ready = true
chunks_v2 = 31302
embeddings_cache_v2 = 31285
manifest_count = 31285
index_metadata = 31285
ollama_available = true
embedding_model_installed = true
```

### Запрос: `Какая погода завтра в Москве?`

После ProjectGuard:

```text
status = refused
intent = out_of_scope_candidate
project_related = false
results = 0
```

Вывод: ProjectGuard работает корректно.

### Запрос: `Что входит в Паспорт ИС?`

До PostReranker/ContextBuilder:

- top-1 корректный: `Паспорт ИС` с границами описания;
- дальше были vector-only chunks из ПР, front matter и таблицы ПО.

Ожидаемый эффект нового слоя:

- `primary_sources` должен содержать обзорный chunk Паспорт ИС;
- software table/front matter должны уйти в `excluded_sources` или не попасть в primary.

### Запрос: `Какие интеграции заявлены в проекте?`

До PostReranker/ContextBuilder:

- top-1 — ЦТА: `Blitz, AD, S3 Minio, Exchange, КШД`;
- top-2 — Паспорт ИС: `Active Directory, Blitz IDP, MDR, почтовый сервер, SIEM`;
- далее ФТТ/ПР.

Ожидаемый эффект нового слоя:

- ЦТА/Паспорт/ФТТ должны попасть в `primary_sources`;
- ПР — в `supporting_sources`.

### Запрос: `ФТТ 4.2.5 НОВАДОК ЭЦП`

До PostReranker/ContextBuilder:

- ФТТ поднимается в top-1/top-2;
- есть строка `ЦП УПКС -> НОВАДОК`;
- встреча `ФТТ_ИД` поднимается как аналитический источник;
- metadata всё ещё шумит: `requirement_id=10.2`, хотя текст содержит `4.2.5`.

Ожидаемый эффект нового слоя:

- ФТТ должен попасть в `primary_sources`;
- ПР/встреча — в `supporting_sources`;
- vector-only нерелевантные chunks должны уйти в `excluded_sources`.

## Следующий практический шаг

Локально проверить новый слой:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Какая погода завтра в Москве?" --mode hybrid --top-k 12 --json
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Что входит в Паспорт ИС?" --mode hybrid --top-k 8 --json
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Какие интеграции заявлены в проекте?" --mode hybrid --top-k 8 --json
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "ФТТ 4.2.5 НОВАДОК ЭЦП" --mode hybrid --top-k 8 --json
```

Проверить:

- внепроектный вопрос: `status=refused`, `results=[]`;
- Паспорт ИС: `context.primary_sources` содержит обзорный chunk, таблицы ПО не в primary;
- интеграции: `context.primary_sources` содержит ЦТА/Паспорт/ФТТ;
- ФТТ 4.2.5: `context.primary_sources` содержит ФТТ с НОВАДОК/ЭЦП;
- `context.excluded_sources` содержит отфильтрованный шум.

## Следующие задачи разработки

### A. Search Quality v2.2

- [x] Добавить `src/asu_june_bot/retrieval/query_intent.py`.
- [x] Добавить `src/asu_june_bot/guardrails/project_guard.py`.
- [x] Подключить `QueryIntent` и `ProjectGuard` в `scripts/asu_june_bot_search_v2.py`.
- [x] Добавить `--no-guard` для диагностического retrieval без отказа.
- [x] Добавить `src/asu_june_bot/retrieval/post_rerank.py`.
- [x] Добавить `src/asu_june_bot/retrieval/context_builder.py`.
- [x] Добавить диагностику `rerank_labels`, `primary_sources`, `supporting_sources` в JSON-ответ `search_v2`.
- [ ] Локально проверить новый слой на baseline-вопросах.
- [ ] Обновить markdown smoke-отчет после проверки нового слоя.
- [ ] При необходимости скорректировать правила `PostReranker`/`ContextBuilder`.

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

- `Паспорт ИС overview` top/context не забит таблицей ПО;
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
- `search_v2 --mode hybrid` проходит 3 baseline-запроса.
- Внепроектный вопрос возвращает `status=refused` и не вызывает retrieval.
- Для каждого baseline-запроса есть primary sources.
- В JSON выдаче есть diagnostics по intent/rerank/context.
- В primary context нет критического шума, который может увести LLM в неверный ответ.
- Старые `data/chunks.jsonl`, `data/embeddings_cache.jsonl`, `data/numpy_index` не меняются.

## Не делать

- Не переходить к Chat MVP напрямую от текущего hybrid top-k.
- Не отправлять в LLM все top-8 как есть.
- Не индексировать `Система` в основной corpus.
- Не раздувать старый `scripts/09_chat.py`.
- Не делать UI до API Search.
