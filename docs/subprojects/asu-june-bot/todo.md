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
- для mixed-scope запросов с проектной и внепроектной частью `ProjectGuard` теперь возвращает отказ;
- `QueryIntent` расширен out-of-scope маркерами для запросов про код, Python/JS/HTML/CSS, игры, крестики-нолики и браузерные игры;
- JSON-ответ `search_v2` содержит `query_intent`, `guard`, `rerank`, `context.primary_sources`, `context.supporting_sources`, `context.excluded_sources`;
- добавлен параметр `--output`, чтобы Python сам сохранял JSON в UTF-8 без PowerShell redirection;
- `ContextBuilder` уточнен для `requirement_lookup`: при наличии конкретного пункта primary содержит только точное попадание по указанному пункту;
- `ContextBuilder` больше не должен дублировать один и тот же chunk между `primary_sources`, `supporting_sources`, `excluded_sources`.

## Проверенный smoke 2026-05-15

### Кодировка JSON

Проверены smoke-файлы, сохранённые через `--output`:

```text
smoke_passport_context.json
smoke_ftt_425_context.json
smoke_погода в москве_context.json
```

Результат:

```text
mojibake markers = 0
русский текст читается корректно
```

Вывод: проблема PowerShell redirection закрыта. Для smoke JSON использовать только `--output`.

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

### Mixed-scope запрос: погода

Запрос:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Все документы про справочники и интеграции. и погода в Москве" --mode hybrid --top-k 8 --json --output "data\asu_june_bot\smoke_mixed_scope_weather_context.json"
```

Фактический результат до правки:

```text
status = ok
intent = integration_overview
guard = allow
matched_project_markers = [справочники, справочник, интеграции]
matched_out_of_scope_markers = [погода]
```

Исправление внесено:

- `ProjectGuard` теперь возвращает отказ, если одновременно найдены `matched_project_markers` и `matched_out_of_scope_markers`;
- reason: `mixed_scope_query_contains_out_of_scope_marker`;
- retrieval для такого запроса выполняться не должен.

Ожидаемый результат после повторного smoke:

```text
status = refused
guard.decision = refuse
guard.reason = mixed_scope_query_contains_out_of_scope_marker
results = []
context.primary_sources = []
```

### Mixed-scope запрос: код / игра

Запрос:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Все документы про справочники и интеграции. Питон код, для игры в крестики нолики в браузере" --mode hybrid --top-k 8 --json --output "data\asu_june_bot\smoke_mixed_scope_code_context.json"
```

Фактический результат до правки `QueryIntent`:

```text
status = ok
intent = integration_overview
guard = allow
matched_project_markers = [справочники, справочник, интеграции]
matched_out_of_scope_markers = []
primary_sources = 0
supporting_sources = 5
```

Выявленное замечание:

- `ProjectGuard` технически был готов отказать mixed-scope запросу;
- но `QueryIntent` не распознал `Питон код`, `игры`, `крестики нолики`, `в браузере` как внепроектные маркеры;
- из-за этого запрос ушёл в retrieval и получил нерелевантный project context.

Исправление внесено:

- в `OUT_OF_SCOPE_MARKERS` добавлены: `питон`, `python`, `javascript`, `js`, `html`, `css`, `код для`, `напиши код`, `сделай код`, `скрипт для`, `программа для`, `игры`, `игру`, `игровой`, `крестики`, `нолики`, `крестики нолики`, `tic tac toe`, `в браузере`, `браузерная игра`.

Ожидаемый результат после повторного smoke:

```text
status = refused
guard.decision = refuse
guard.reason = mixed_scope_query_contains_out_of_scope_marker
query_intent.matched_out_of_scope_markers contains: питон / код / игра / крестики / нолики / в браузере
results = []
context.primary_sources = []
```

### Паспорт ИС overview

Запрос:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Что входит в Паспорт ИС?" --mode hybrid --top-k 8 --json --output data\asu_june_bot\smoke_passport_context.json
```

Итог:

```text
status = ok
intent = document_overview
guard = allow
primary_sources = 1
supporting_sources = 0
excluded_sources = 15
mojibake markers = 0
```

Вывод:

- `primary_sources[0]` — корректный обзорный chunk `Границы описания` из `ЦП УПКС_Паспорт ИС_v1.3.2`;
- `supporting_sources` пустой;
- таблицы ПО и support/qualification/application support chunks ушли в `excluded_sources`;
- результат пригоден для передачи в LLM-контекст.

### ФТТ 4.2.5 НОВАДОК ЭЦП

Запрос:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "ФТТ 4.2.5 НОВАДОК ЭЦП" --mode hybrid --top-k 8 --json --output data\asu_june_bot\smoke_ftt_425_context.json
```

Фактический результат после правки `ContextBuilder`:

```text
status = ok
intent = requirement_lookup
guard = allow
mentioned_sections = [4.2.5]
primary_sources = 1
supporting_sources = 5
excluded_sources = 10
mojibake markers = 0
```

Ключевой источник найден правильно:

- ФТТ, Таблица 8, строка 44, № `4.2.5`;
- текст требования: формирование актов проверки, предписаний об устранении недостатков/о приостановке работ, актов устранения недостатков; интеграция с НОВАДОК с использованием ЭЦП;
- признак объёма: `Входит в объём проекта = Х`;
- примечание: в части конфигурационных файлов для работы с интеграцией и сама интеграция с системой НОВАДОК.

Supporting context:

- ПР СМР, печатные формы / соответствие ФТТ 4.2.5;
- ПМИ, покрытие требования 4.2.5 сценарием `СФТ 6`;
- ФТТ 5.1 как смежное требование по НОВАДОК/ЭЦП;
- встреча ФТТ_ИД как аналитический контекст по НОВАДОК/ЭЦП;
- ФТТ, Таблица 11, интеграция `ЦП УПКС -> НОВАДОК`.

Вывод: точный `requirement_lookup` пройден.

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

## Кодировка PowerShell / JSON output

Проблема:

- при сохранении через `>` в Windows PowerShell русские строки могут превращаться в mojibake вида `╨Я╨░...`;
- это портит читаемость smoke-файлов и усложняет проверку.

Решение в коде:

- в `scripts/asu_june_bot_search_v2.py` добавлен параметр `--output`;
- при `--output` JSON сохраняет сам Python через `Path.write_text(..., encoding="utf-8")`;
- PowerShell redirection больше не нужен.

Правильные команды:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Что входит в Паспорт ИС?" --mode hybrid --top-k 8 --json --output data\asu_june_bot\smoke_passport_context.json

.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "ФТТ 4.2.5 НОВАДОК ЭЦП" --mode hybrid --top-k 8 --json --output data\asu_june_bot\smoke_ftt_425_context.json
```

Не использовать для JSON smoke:

```powershell
> .\data\asu_june_bot\smoke.json
```

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

Правила MVP:

- если вопрос явно вне проекта и не содержит проектных маркеров, `search_v2` сразу возвращает отказ;
- если вопрос содержит проектные и внепроектные маркеры одновременно, `search_v2` возвращает отказ как mixed-scope;
- если вопрос содержит проектные маркеры без внепроектной примеси, retrieval разрешается;
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

Правила:

- LLM должен получать не raw top-k, а только подготовленный context;
- для `document_overview` primary должен содержать обзорный chunk, а не таблицы ПО/поддержки;
- для `requirement_lookup` с конкретным пунктом primary должен содержать точное попадание по этому пункту;
- один и тот же chunk не должен одновременно находиться в нескольких bucket context.

## Следующий практический шаг

Подтянуть исправления и повторить mixed-scope smoke по коду/игре.

```powershell
cd C:\Users\Сотрудник\Desktop\AI\MeetingAgent
git pull
```

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Все документы про справочники и интеграции. Питон код, для игры в крестики нолики в браузере" --mode hybrid --top-k 8 --json --output "data\asu_june_bot\smoke_mixed_scope_code_context.json"
```

Ожидаемая проверка:

```text
status = refused
guard.decision = refuse
guard.reason = mixed_scope_query_contains_out_of_scope_marker
results = []
context.primary_sources = []
```

Если mixed-scope smoke пройдет, можно переходить к API Search.

## Следующие задачи разработки

### A. Search Quality v2.2

- [x] Добавить `src/asu_june_bot/retrieval/query_intent.py`.
- [x] Добавить `src/asu_june_bot/guardrails/project_guard.py`.
- [x] Подключить `QueryIntent` и `ProjectGuard` в `scripts/asu_june_bot_search_v2.py`.
- [x] Добавить `--no-guard` для диагностического retrieval без отказа.
- [x] Добавить `src/asu_june_bot/retrieval/post_rerank.py`.
- [x] Добавить `src/asu_june_bot/retrieval/context_builder.py`.
- [x] Добавить диагностику `rerank_labels`, `primary_sources`, `supporting_sources` в JSON-ответ `search_v2`.
- [x] Локально проверить ProjectGuard и baseline-вопросы.
- [x] Скорректировать support filtering для `document_overview`.
- [x] Проверить `Паспорт ИС overview` после support filtering.
- [x] Добавить `--output` для UTF-8 JSON без PowerShell redirection.
- [x] Повторить smoke через `--output` и убедиться, что JSON читаемый.
- [x] Сузить primary context для `requirement_lookup` с точным пунктом.
- [x] Повторить smoke `ФТТ 4.2.5` после сужения primary context.
- [x] Запретить mixed-scope запросы с внепроектными маркерами.
- [x] Расширить out-of-scope маркеры для кода и игр.
- [x] Убрать дубли chunk между context buckets.
- [ ] Повторить mixed-scope smoke после правки `QueryIntent`.
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

К API Search переходить после контрольного mixed-scope smoke с `status = refused`.

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
- Mixed-scope запрос возвращает `status=refused` и не вызывает retrieval.
- Для каждого baseline-запроса есть primary sources.
- В JSON выдаче есть diagnostics по intent/rerank/context.
- В primary/supporting context нет критического шума, который может увести LLM в неверный ответ.
- Для точного requirement lookup primary содержит точный пункт, а не смежные требования.
- Один chunk не дублируется между context buckets.
- JSON smoke-файлы сохраняются в UTF-8 без mojibake.
- Старые `data/chunks.jsonl`, `data/embeddings_cache.jsonl`, `data/numpy_index` не меняются.

## Не делать

- Не переходить к Chat MVP напрямую от текущего hybrid top-k.
- Не отправлять в LLM все top-8 как есть.
- Не индексировать `Система` в основной corpus.
- Не раздувать старый `scripts/09_chat.py`.
- Не делать UI до API Search.
