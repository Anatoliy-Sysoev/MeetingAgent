# Search Smoke Report — Asu June Bot v2.1

Дата: 2026-05-14.

## Цель проверки

Проверить готовность Asu June Bot v2.1 после полной сборки корпуса, embeddings cache и numpy index.

Проверяется не качество LLM-ответа, а качество retrieval/search перед переходом к API Search и Chat MVP.

## Runtime-состояние

По результатам локального запуска:

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
embedding_model = bge-m3
embedding_dim = 1024
```

Индекс v2 собран только по разрешенным source types:

```text
project_doc = 26232
analytical_note = 2815
instruction = 1763
meeting_artifact = 475
```

Исключено:

```text
code = 17
```

## Проверенные запросы

### 1. Что входит в Паспорт ИС?

Команды:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Что входит в Паспорт ИС?" --mode bm25 --top-k 8
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Что входит в Паспорт ИС?" --mode hybrid --top-k 8
```

Результат:

- BM25 top-1/top-2 корректно поднимает `ЦП УПКС_Паспорт ИС_v1.3.2` и `ЦП УПКС_Паспорт ИС_v1.3.3`.
- Найденный фрагмент описывает границы паспорта: архитектурные и эксплуатационные сведения, платформа ЦП УПКС, модуль СМР и базовые сервисы Front/Core/Disk/Building/Approvals/Notifications/Catalog/Help/Mdr.
- Hybrid top-1 корректный.
- Hybrid top-k после top-1 всё ещё содержит vector-only noise: ПР, таблицы ПО, строки поддержки.

Вывод:

```text
search пригоден частично;
нельзя отправлять весь raw hybrid top-k в LLM;
нужен document_overview intent и ContextBuilder.
```

### 2. Какие интеграции заявлены в проекте?

Команда:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Какие интеграции заявлены в проекте?" --mode hybrid --top-k 8
```

Результат:

- Поднимаются ЦТА, Паспорт ИС, ФТТ, ПР и wiki-summary.
- ЦТА содержит внешние системы: `Blitz`, `AD`, `S3 Minio`, `Exchange`, `КШД`.
- Паспорт ИС содержит: `Active Directory`, `Blitz IDP`, `MDR`, почтовый сервер, `SIEM`.
- ФТТ поднимает КШД/SOAP.
- ПР поднимает взаимодействие со смежными модулями.

Вывод:

```text
retrieval достаточен для API Search MVP;
для Chat MVP всё равно нужен ContextBuilder и primary/supporting sources.
```

### 3. ФТТ 4.2.5 НОВАДОК ЭЦП

Команда:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "ФТТ 4.2.5 НОВАДОК ЭЦП" --mode hybrid --top-k 8
```

Результат:

- BM25/hybrid поднимает ФТТ в top-1/top-2.
- В top-5 есть ФТТ с интеграционной строкой `ЦП УПКС -> НОВАДОК`.
- Встреча `ФТТ_ИД` поднимается как полезный аналитический источник по уточнению НОВАДОК/ЭЦП.
- ПР поднимается как supporting source по реализации/соответствию требованиям.

Проблема:

- Metadata по `section/requirement_id` шумит: для части chunks выставляется `10.2`, хотя текст содержит `4.2.5`.
- Нужно различать `contract_section`, `requirement_id`, `mentioned_requirement_ids` и `document_version`.

Вывод:

```text
retrieval практически пригоден;
metadata надо улучшить до Chat MVP.
```

## Итоговая оценка

| Область | Статус |
| --- | --- |
| Corpus v2.1 | Готов |
| Embeddings cache v2 | Готов |
| Numpy index v2 | Готов |
| Health check | Готов |
| BM25 search | Частично готов |
| Vector search | Работает |
| Hybrid search | Частично готов |
| API Search | Не начинать до v2.2 |
| Chat MVP | Не начинать до v2.2 |

## Основные дефекты

1. Raw hybrid top-k нельзя отдавать напрямую в LLM.
2. Для обзорных вопросов нужен `document_overview` intent.
3. Нужен post-rerank после hybrid merge.
4. Нужен ContextBuilder с `primary_sources` и `supporting_sources`.
5. Нужно улучшить metadata для требований: `requirement_id`, `mentioned_requirement_ids`, `contract_section`.

## Решение

Перед API Search выполнить Search Quality v2.2:

```text
query_intent -> post_rerank -> context_builder -> diagnostics -> smoke_report
```

Минимальные файлы:

```text
src/asu_june_bot/retrieval/query_intent.py
src/asu_june_bot/retrieval/post_rerank.py
src/asu_june_bot/retrieval/context_builder.py
```

Definition of Done для v2.2:

- `search_v2 --json` возвращает `query_intent`.
- `search_v2 --json` возвращает `primary_sources` и `supporting_sources`.
- `Паспорт ИС overview` не забит таблицей ПО.
- `ФТТ 4.2.5` возвращает ФТТ с НОВАДОК/ЭЦП как primary source.
- `Интеграции` возвращают ЦТА/Паспорт/ФТТ/СоИ как primary/supporting sources.
- В LLM-контекст не попадает критический vector-only шум.
