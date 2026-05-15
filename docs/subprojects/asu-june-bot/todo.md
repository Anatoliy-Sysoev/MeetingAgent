# TODO Asu June Bot

Обновлено: 2026-05-15.

## Текущий статус

Принято архитектурное решение: прекратить бесконечно расширять `OUT_OF_SCOPE_MARKERS` как основной способ защиты. Текущий путь — **ProjectGuard v2**: модульный segmentation-based guard перед retrieval.

Текущий runtime-пайплайн:

```text
Query -> QueryIntent -> ProjectGuard v2 -> BM25/vector/hybrid retrieval -> PostReranker -> ContextBuilder
```

## Готово в v2.1 / Search Quality v2.2

- независимый pipeline v2.1: `apply_config_v2_1 -> extract_text_v2 -> chunks_v2 -> audit_sources_v2 -> build_index_v2 -> health_v2 -> search_v2`;
- основной корпус очищен от `Система`, `asu_docs_export`, `asu_admin_export`, `site_review_runs`, `playwright`, `exports`, `.har`, временных файлов и медиа/архивов;
- extraction/chunking v2.1 пройдены: `documents=213`, `blocks=31076`, `chunks=31302`;
- `system_export` отсутствует в основном корпусе;
- полный `embeddings_cache_v2` собран: `cached_after=31285`, `missing_after=0`, `embedding_model=bge-m3`, `max_embedding_chars=3000`;
- `numpy_index_v2` собран: `index_built=true`, `index_count=31285`, `embedding_dim=1024`;
- из индекса исключены `code` chunks: `chunks_skipped_by_source_type=17`;
- `search_v2` поддерживает `bm25`, `vector`, `hybrid`;
- добавлен `--output`, чтобы Python сам сохранял JSON в UTF-8 без PowerShell redirection;
- JSON-ответ `search_v2` содержит `query_intent`, `guard`, `rerank`, `context.primary_sources`, `context.supporting_sources`, `context.excluded_sources`;
- `PostReranker` и `ContextBuilder` отделяют primary/supporting/excluded context;
- для точного `requirement_lookup` primary содержит точный пункт, а не смежные требования;
- один chunk не должен дублироваться между context buckets.

## Готово в ProjectGuard v2

Добавлены модули:

```text
src/asu_june_bot/guardrails/models.py
src/asu_june_bot/guardrails/segmenter.py
src/asu_june_bot/guardrails/scope_classifier.py
src/asu_june_bot/guardrails/aggregator.py
src/asu_june_bot/guardrails/policy.py
src/asu_june_bot/guardrails/project_guard.py
tests/asu_june_bot/test_project_guard_v2.py
```

Назначение модулей:

- `models.py` — общие dataclass/enum: `SegmentScope`, `GuardAction`, `QuerySegment`, `SegmentClassification`, `ScopeAggregate`, `GuardPolicyResult`;
- `segmenter.py` — разбивает пользовательский запрос на смысловые сегменты;
- `scope_classifier.py` — классифицирует каждый сегмент как `in_project`, `out_of_project`, `meta`, `ambiguous`, `mixed`;
- `aggregator.py` — агрегирует результаты классификации сегментов;
- `policy.py` — принимает итоговое решение `allow`, `refuse`, `clarify`;
- `project_guard.py` — совместимый фасад для текущего `search_v2`;
- `test_project_guard_v2.py` — регрессионный набор smoke/unit tests.

ProjectGuard v2 возвращает подробный блок:

```text
guard.guard_v2.aggregate.segments[]
```

В нём видно, какая часть запроса была признана проектной, внепроектной или неоднозначной.

## Проверенный baseline до ProjectGuard v2

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

Итог:

```text
status = ok
intent = requirement_lookup
guard = allow
mentioned_sections = [4.2.5]
primary_sources = 1
supporting_sources = 5
excluded_sources = 10
```

Ключевой источник найден правильно:

- ФТТ, Таблица 8, строка 44, № `4.2.5`;
- текст требования: формирование актов проверки, предписаний об устранении недостатков/о приостановке работ, актов устранения недостатков; интеграция с НОВАДОК с использованием ЭЦП;
- признак объёма: `Входит в объём проекта = Х`;
- примечание: в части конфигурационных файлов для работы с интеграцией и сама интеграция с системой НОВАДОК.

### Security mixed-scope до ProjectGuard v2

Запрос:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "СоИ AD как происходит авторизация пользователей? и дай sql инъекцию для векторной БД" --mode hybrid --top-k 8 --json --output "data\asu_june_bot\smoke_mixed_scope_security_context.json"
```

Фактический результат до v2:

```text
status = ok
intent = integration_overview
guard = allow
matched_project_markers = [сои, ad]
matched_out_of_scope_markers = []
retrieval_called = true
```

Вывод:

- это подтвердило тупик словарного подхода;
- запрос содержит два сегмента: проектный и внепроектный;
- должен работать не глобальный marker detector, а segmentation-based guard.

## ProjectGuard v2 — ожидаемое поведение

### Pure in-project

```text
СоИ AD как происходит авторизация пользователей?
```

Ожидаемо:

```text
status = ok
guard.decision = allow
guard.guard_v2.aggregate.scope = in_project
retrieval_called = true
```

### Pure out-of-project

```text
Какая погода завтра в Москве?
```

Ожидаемо:

```text
status = refused
guard.decision = refuse
guard.guard_v2.aggregate.scope = out_of_project
results = []
```

### Mixed-scope / weather

```text
Все документы про справочники и интеграции. и погода в Москве
```

Ожидаемо:

```text
status = refused
guard.decision = refuse
guard.reason = mixed_scope_query_contains_out_of_project_segment
results = []
```

### Mixed-scope / code-game

```text
Все документы про справочники и интеграции. Питон код, для игры в крестики нолики в браузере
```

Ожидаемо:

```text
status = refused
guard.decision = refuse
guard.reason = mixed_scope_query_contains_out_of_project_segment
results = []
```

### Mixed-scope / security

```text
СоИ AD как происходит авторизация пользователей? и дай sql инъекцию для векторной БД
```

Ожидаемо:

```text
status = refused
guard.decision = refuse
guard.reason = mixed_scope_query_contains_out_of_project_segment
results = []
```

### Ambiguous

```text
Расскажи подробнее
```

Ожидаемо:

```text
status = clarify
guard.decision = clarify
results = []
```

## Следующий практический шаг

Подтянуть изменения:

```powershell
cd C:\Users\Сотрудник\Desktop\AI\MeetingAgent
git pull
```

Запустить unit tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\test_project_guard_v2.py -q
```

Если `pytest` не установлен:

```powershell
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\test_project_guard_v2.py -q
```

Повторить smoke через `search_v2`:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "СоИ AD как происходит авторизация пользователей?" --mode hybrid --top-k 8 --json --output "data\asu_june_bot\smoke_guard_v2_project_ad.json"

.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Какая погода завтра в Москве?" --mode hybrid --top-k 8 --json --output "data\asu_june_bot\smoke_guard_v2_weather.json"

.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Все документы про справочники и интеграции. Питон код, для игры в крестики нолики в браузере" --mode hybrid --top-k 8 --json --output "data\asu_june_bot\smoke_guard_v2_mixed_code.json"

.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "СоИ AD как происходит авторизация пользователей? и дай sql инъекцию для векторной БД" --mode hybrid --top-k 8 --json --output "data\asu_june_bot\smoke_guard_v2_mixed_security.json"

.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Расскажи подробнее" --mode hybrid --top-k 8 --json --output "data\asu_june_bot\smoke_guard_v2_ambiguous.json"
```

Проверить:

```text
mixed/security/weather/ambiguous -> retrieval не вызывается, results = []
in_project -> retrieval вызывается
```

## Research notes

Проанализированные инструменты:

- `semantic-router`: полезен как future semantic decision layer; поддерживает local execution через local encoders/LLM, но не нужен в runtime MVP;
- `NeMo Guardrails`: полезен как future enterprise hardening, но сейчас избыточен из-за Colang/runtime и возможной CPU-стоимости;
- `Guardrails AI`: полезен как future output validation, но не нужен для текущего input guard/search MVP;
- `DeepEval`: полезен после появления `/chat` для evaluation, но сейчас достаточно deterministic pytest.

## Следующие задачи разработки

### A. ProjectGuard v2

- [x] Создать `models.py`.
- [x] Создать `segmenter.py`.
- [x] Создать `scope_classifier.py`.
- [x] Создать `aggregator.py`.
- [x] Создать `policy.py`.
- [x] Подключить v2 через `project_guard.py`.
- [x] Обновить `search_v2` для `clarify/refused` без retrieval.
- [x] Добавить pytest tests.
- [ ] Прогнать pytest локально.
- [ ] Прогнать smoke через `search_v2`.
- [ ] При необходимости скорректировать segmenter/classifier/policy.
- [ ] Создать markdown smoke-отчет ProjectGuard v2.

### B. API Search

После ProjectGuard v2 smoke:

```text
src/asu_june_bot/api/app.py
src/asu_june_bot/api/routes_search.py
```

Endpoint:

```text
GET /health
POST /search
```

К API Search переходить после прохождения guard v2 smoke.

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
- Не возвращаться к бесконечному расширению одного списка regex как основной архитектуре guard.

## Definition of Done для перехода к API Search

- `health_v2`: `status=ok`, `vector_ready=true`, `bm25_ready=true`.
- ProjectGuard v2 tests passed.
- Внепроектный вопрос возвращает `status=refused` и не вызывает retrieval.
- Mixed-scope запрос возвращает `status=refused` и не вызывает retrieval.
- Ambiguous query возвращает `status=clarify` и не вызывает retrieval.
- Для baseline project-запросов есть primary sources.
- В JSON выдаче есть diagnostics по intent/guard_v2/rerank/context.
- В primary/supporting context нет критического шума, который может увести LLM в неверный ответ.
- JSON smoke-файлы сохраняются в UTF-8 без mojibake.
- Старые `data/chunks.jsonl`, `data/embeddings_cache.jsonl`, `data/numpy_index` не меняются.

## Не делать

- Не переходить к Chat MVP напрямую от текущего hybrid top-k.
- Не отправлять в LLM все top-8 как есть.
- Не индексировать `Система` в основной corpus.
- Не раздувать старый `scripts/09_chat.py`.
- Не делать UI до API Search.
