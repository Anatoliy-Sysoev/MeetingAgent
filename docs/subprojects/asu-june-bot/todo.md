# TODO Asu June Bot

Обновлено: 2026-05-14.

## Текущий статус v2.1

Asu June Bot v2.1 технически собран до уровня локального search MVP.

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
- BM25 получил deterministic rerank: intent boosts по `Паспорт ИС`, `ФТТ`, интеграциям, exact section/requirement и штрафы для глоссариев/front matter/software tables.

## Результаты последнего smoke search

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

### Запрос: `Что входит в Паспорт ИС?`

Состояние после rerank:

- BM25 top-1/top-2 поднимает нужный chunk из `ЦП УПКС_Паспорт ИС_v1.3.2` и `v1.3.3` с текстом про границы паспорта: архитектурные и эксплуатационные сведения, платформа ЦП УПКС, модуль СМР, базовые сервисы Front/Core/Disk/Building/Approvals/Notifications/Catalog/Help/Mdr.
- Это уже пригодный источник для обзорного ответа.
- В top-8 всё ещё присутствуют chunks по `Программному обеспечению информационной системы` и поддержке. Для search это допустимо, но для Chat MVP нужен context builder, который будет отбирать обзорные chunks, а не все top-k.
- Hybrid top-1 корректный, но дальше попадают vector-only chunks из ПР и таблицы ПО. Нужно добавить post-rerank/intent filtering на уровне hybrid/context builder.

Вывод: вопрос стал проходить лучше, но ещё не готов для прямой генерации без фильтрации контекста.

### Запрос: `Какие интеграции заявлены в проекте?`

Состояние:

- Hybrid top-1 — ЦТА: `Blitz, AD, S3 Minio, Exchange, КШД`.
- Hybrid top-2 — Паспорт ИС: `Active Directory, Blitz IDP, MDR, почтовый сервер, SIEM`.
- Дополнительно поднимаются ЦТА по `S3 Minio/SIEM`, ФТТ по КШД/SOAP и ПР по взаимодействию со смежными модулями.

Вывод: retrieval для вопроса по интеграциям достаточен для API Search MVP.

### Запрос: `ФТТ 4.2.5 НОВАДОК ЭЦП`

Состояние после rerank:

- BM25/hybrid подняли ФТТ в top-1/top-2.
- В top-5 есть ФТТ с интеграционной строкой `ЦП УПКС -> НОВАДОК`: сформированные документы передаются для согласования и подписания ЭЦП.
- Встреча `ФТТ_ИД` поднимается как полезный аналитический источник по уточнению НОВАДОК/ЭЦП.
- Metadata всё ещё шумит: для части chunks поле `requirement_id` показывает `10.2`, хотя текст содержит `4.2.5`; это нужно исправлять в metadata extraction/chunking или компенсировать на уровне rerank.

Вывод: retrieval по ФТТ 4.2.5 практически пригоден, но metadata по section/requirement нужно улучшить до Chat MVP.

## Главные дефекты до API Search / Chat MVP

1. Hybrid top-k может подмешивать vector-only noise.
   - Пример: по Паспорту ИС после корректного top-1 идут ПР и таблицы ПО.
   - Решение: добавить post-rerank и intent-aware context builder.

2. Обзорные вопросы требуют не просто top-k retrieval, а document overview mode.
   - Пример: `Что входит в Паспорт ИС?` должен отдавать состав/границы/разделы, а не строки таблицы ПО.
   - Решение: определить `query_intent=document_overview`, затем брать chunks типа `scope/structure/heading/section_summary`, а таблицы ПО использовать только как вторичный контекст.

3. Metadata section/requirement шумит.
   - Пример: запрос по `4.2.5` возвращает chunks с `requirement_id=10.2`, хотя в тексте есть `4.2.5`.
   - Решение: улучшить extraction/chunking metadata; отдельно отличать `document_version`, `contract_section`, `requirement_id` и `mentioned_requirement_ids`.

4. Нужно формально сохранить smoke JSON.
   - Уже создаются файлы `data/asu_june_bot/smoke_*_hybrid.json`, но они runtime и не должны коммититься.
   - Нужно добавить markdown-отчет в `docs/subprojects/asu-june-bot/search_smoke_report_2026-05-14.md`.

## Следующий практический шаг

Перед API Search выполнить Search Quality v2.2:

```text
1. Добавить query intent classifier без LLM:
   - document_overview
   - integration_overview
   - requirement_lookup
   - general_project_question
   - out_of_scope_candidate

2. Добавить post-rerank после hybrid merge:
   - штраф vector-only chunks без BM25 для exact/overview queries;
   - штраф software/support/glossary tables для document_overview;
   - boost exact document_type по intent;
   - boost exact requirement mentions;
   - дедупликация версий одного документа или приоритет latest version.

3. Добавить ContextBuilder MVP:
   - не отдавать LLM весь top-k как есть;
   - выбирать 3-6 chunks по intent;
   - отделять primary sources от supporting sources;
   - отдавать diagnostics.

4. Повторить smoke:
   - Паспорт ИС overview;
   - интеграции;
   - ФТТ 4.2.5;
   - внепроектный вопрос.
```

## Следующие задачи разработки

### A. Search Quality v2.2

- [ ] Добавить `src/asu_june_bot/retrieval/query_intent.py`.
- [ ] Добавить `src/asu_june_bot/retrieval/post_rerank.py`.
- [ ] Добавить `src/asu_june_bot/retrieval/context_builder.py`.
- [ ] Добавить диагностику `query_intent`, `rerank_labels`, `primary_sources`, `supporting_sources` в JSON-ответ `search_v2`.
- [ ] Добавить markdown smoke-отчет по текущему срезу.
- [ ] Повторить baseline после rerank/context builder.

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
- JSON содержит пригодные diagnostics.

### C. Chat MVP

После API Search:

- [ ] `ProjectGuard`.
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
- Для каждого baseline-запроса есть primary sources.
- В JSON выдаче есть diagnostics по intent/rerank.
- В top/context нет критического шума, который может увести LLM в неверный ответ.
- Старые `data/chunks.jsonl`, `data/embeddings_cache.jsonl`, `data/numpy_index` не меняются.

## Не делать

- Не переходить к Chat MVP напрямую от текущего hybrid top-k.
- Не отправлять в LLM все top-8 как есть.
- Не индексировать `Система` в основной corpus.
- Не раздувать старый `scripts/09_chat.py`.
- Не делать UI до API Search.
