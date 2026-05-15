# Asu June Bot v2.1 Runbook

Обновлено: 2026-05-15.

## Назначение

Инструкция запуска независимого pipeline Asu June Bot v2.1/v2.2:

```text
apply_config_v2_1 -> extract_text_v2 -> chunks_v2 -> audit_sources_v2 -> build_index_v2 -> health_v2 -> search_v2 -> project_guard/query_intent
```

Pipeline v2.1 не использует старый `scripts/02_extract_text.py` и не меняет старые runtime-файлы MeetingAgent:

```text
data/chunks.jsonl
data/embeddings_cache.jsonl
data/numpy_index/
```

Все новые данные пишутся в:

```text
data/asu_june_bot/
```

## Что изменилось

- Исключается шумная папка `**/Система/**`.
- Исключаются `asu_docs_export`, `asu_admin_export`, `site_review_runs`, `playwright`, `exports`, HTML/text exports и screenshots.
- Исключаются `.har`, временные файлы, архивы, медиа и изображения.
- `system_export` сильно понижен в весах и не участвует в обычном поиске без явного запроса.
- Улучшена классификация `document_type`: ФТТ, ЦТА, ПР, ПМИ, СоИ, Паспорт ИС, Руководство, Протокол, API, BPMN.
- Улучшено чтение DOCX-таблиц: заголовочная строка определяется эвристически, а не всегда берется первая строка.
- Улучшено чтение XLSX: используется `openpyxl`, строки и ячейки сохраняются структурно.
- Добавлены отдельные `embeddings_cache_v2.jsonl`, `numpy_index_v2/` и `asu_june_bot_search_v2.py`.
- Добавлен `asu_june_bot_health_v2.py` для проверки готовности корпуса, индекса и Ollama.
- В `search_v2` добавлена понятная ошибка при недоступном Ollama вместо traceback.
- В `hybrid` добавлен fallback на BM25, если Ollama недоступен.
- В BM25 добавлен deterministic rerank: intent boosts по `Паспорт ИС`, `ФТТ`, интеграциям, exact requirement/section и штраф для глоссариев.
- Добавлены `QueryIntent` и `ProjectGuard`.
- Внепроектные вопросы теперь должны возвращать `status=refused` до retrieval.
- Для диагностики retrieval без защиты добавлен флаг `--no-guard`.

## 1. Обновить ветку

```powershell
cd C:\Users\Сотрудник\Desktop\AI\MeetingAgent
git checkout docs/asu-june-bot-subproject
git pull
```

## 2. Health check v2

После сборки `embeddings_cache_v2` и `numpy_index_v2` сначала проверять состояние одной командой:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_health_v2.py
```

JSON-вывод:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_health_v2.py --json
```

Ключевые признаки готовности:

```text
bm25_ready = true
vector_ready = true
counts.manifest_count = 31285
counts.index_metadata = 31285
checks.ollama_available = true
checks.embedding_model_installed = true
```

Если `bm25_ready = true`, а `vector_ready = false`, BM25-поиск работает, но vector/hybrid требует запущенный Ollama и модель `bge-m3`.

## 3. Если Ollama недоступен

Vector search и нормальный hybrid search требуют embedding запроса. Даже при готовом `numpy_index_v2` нужен работающий Ollama.

Проверка:

```powershell
ollama list
```

Если Ollama не запущен:

```powershell
ollama serve
```

Если модели нет:

```powershell
ollama pull bge-m3
```

После этого повторить:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_health_v2.py
```

## 4. ProjectGuard smoke

Внепроектный вопрос должен отказываться до retrieval:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Какая погода завтра в Москве?" --mode hybrid --top-k 12
```

Ожидаемо:

```text
status = refused
Intent = out_of_scope_candidate
Guard = refuse
Результатов = 0
```

JSON-проверка:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Какая погода завтра в Москве?" --mode hybrid --top-k 12 --json
```

Ожидаемо:

```json
{
  "status": "refused",
  "results": []
}
```

Диагностический запуск без guard:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Какая погода завтра в Москве?" --mode hybrid --top-k 12 --no-guard
```

Этот режим нужен только для отладки retrieval. В обычном режиме его не использовать.

## 5. BM25 smoke

BM25 не требует Ollama.

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Что входит в Паспорт ИС?" --mode bm25 --top-k 5
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Какие интеграции заявлены в проекте?" --mode bm25 --top-k 5
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "ФТТ 4.2.5 НОВАДОК ЭЦП" --mode bm25 --top-k 5
```

Ожидаемые признаки:

- по `Что входит в Паспорт ИС?` в top-2 должны быть актуальные версии `ЦП УПКС_Паспорт ИС`;
- по `Какие интеграции заявлены в проекте?` должны подниматься `ЦТА`, `Паспорт ИС`, `СоИ AD`, `СоИ Справочники` и/или wiki-summary;
- по `ФТТ 4.2.5 НОВАДОК ЭЦП` должен подниматься `ФТТ` с exact `4.2.5`; ПМИ и ПР допустимы ниже как проверочные/реализационные документы.

## 6. Vector smoke

Требует `vector_ready = true` из health check.

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Что входит в Паспорт ИС?" --mode vector --top-k 8
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Какие интеграции заявлены в проекте?" --mode vector --top-k 8
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "ФТТ 4.2.5 НОВАДОК ЭЦП" --mode vector --top-k 8
```

## 7. Hybrid smoke

Требует Ollama для vector-части. Если Ollama выключен, `hybrid` вернет BM25 fallback с предупреждением.

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Что входит в Паспорт ИС?" --mode hybrid --top-k 8
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Какие интеграции заявлены в проекте?" --mode hybrid --top-k 8
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "ФТТ 4.2.5 НОВАДОК ЭЦП" --mode hybrid --top-k 8
```

## 8. JSON smoke для анализа retrieval

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Какие интеграции заявлены в проекте?" --mode hybrid --top-k 12 --json > .\data\asu_june_bot\smoke_integrations_hybrid.json
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Что входит в Паспорт ИС?" --mode hybrid --top-k 12 --json > .\data\asu_june_bot\smoke_passport_hybrid.json
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "ФТТ 4.2.5 НОВАДОК ЭЦП" --mode hybrid --top-k 12 --json > .\data\asu_june_bot\smoke_ftt_425_hybrid.json
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Какая погода завтра в Москве?" --mode hybrid --top-k 12 --json > .\data\asu_june_bot\smoke_out_of_scope_weather.json
```

Файлы `data/asu_june_bot/smoke_*_hybrid.json` являются runtime-данными и не коммитятся. Для фиксации результата нужно создать markdown-отчет в `docs/subprojects/asu-june-bot/`.

## 9. Search Quality v2.2 перед API Search

Сейчас реализована первая часть v2.2:

```text
query_intent -> project_guard
```

Осталось:

```text
post_rerank -> context_builder -> diagnostics -> smoke_report
```

Файлы:

```text
src/asu_june_bot/retrieval/post_rerank.py
src/asu_june_bot/retrieval/context_builder.py
```

Post-rerank должен:

- штрафовать vector-only chunks без BM25 для exact/overview queries;
- штрафовать software/support/glossary tables для `document_overview`;
- усиливать exact document_type по intent;
- усиливать exact requirement mentions;
- дедуплицировать версии одного документа или отдавать приоритет latest version.

ContextBuilder должен:

- выбирать 3-6 chunks по intent;
- отделять `primary_sources` от `supporting_sources`;
- не отправлять LLM все top-8 без фильтрации;
- возвращать diagnostics.

## 10. Полная пересборка v2.1 при изменении корпуса

Если меняются фильтры, список файлов или правила extraction/chunking, пересобрать с нуля:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_extract_text_v2.py --reset
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py
.\.venv\Scripts\python.exe scripts\asu_june_bot_audit_sources_v2.py
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_index_v2.py --embed-only
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_index_v2.py --index-only
.\.venv\Scripts\python.exe scripts\asu_june_bot_health_v2.py
```

## 11. Проверка extraction/chunking

Для Windows PowerShell 5.1 всегда указывать `-Encoding UTF8` при чтении отчетов.

```powershell
Get-Content .\data\asu_june_bot\extracted_v2\extraction_v2_report.json -Encoding UTF8
Get-Content .\data\asu_june_bot\chunking_v2_report.json -Encoding UTF8
Get-Content .\data\asu_june_bot\source_audit_v2_report.json -Encoding UTF8
Get-Content .\data\asu_june_bot\index_v2_report.json -Encoding UTF8
Get-Content .\data\asu_june_bot\numpy_index_v2\manifest.json -Encoding UTF8
```

## 12. Watchdog для долгого embeddings cache

Для долгого `--embed-only` использовать отдельный watchdog. Он не запускает extraction/chunking и не трогает старые RAG-файлы.

```powershell
.\register_asu_june_bot_index_v2_watchdog.ps1 -IntervalMinutes 30
```

Лог:

```powershell
Get-Content .\logs\asu_june_bot_index_v2_watchdog.log -Encoding UTF8 -Tail 80
```

Отключить вручную:

```powershell
Unregister-ScheduledTask -TaskName AsuJuneBotIndexV2Watchdog -Confirm:$false
```

## 13. Что считать успешным завершением

Успешное завершение extraction/chunking:

```text
существует data/asu_june_bot/extracted_v2/blocks.jsonl
существует data/asu_june_bot/chunks_v2.jsonl
существует data/asu_june_bot/chunking_v2_report.json
source_audit_v2_report.json показывает, что Система исключена
```

Успешное завершение index v2:

```text
существует data/asu_june_bot/embeddings_cache_v2.jsonl
существует data/asu_june_bot/numpy_index_v2/manifest.json
manifest.count = 31285
search_v2 --mode hybrid возвращает релевантные ФТТ/ЦТА/ПР/Паспорт/СоИ
```

Успешное завершение перед API Search:

```text
внепроектный вопрос возвращает status=refused и results=[]
query_intent определен
primary_sources сформированы
supporting_sources сформированы
критический vector-only шум не попадает в primary context
smoke report сохранен в docs/subprojects/asu-june-bot/
```

## 14. Не делать

- Не удалять `data/asu_june_bot/`, если нужно продолжить после прерывания.
- Не запускать `--reset`, если нужна resume-сборка.
- Не менять старый `run_full_rag.ps1`.
- Не перезаписывать `data/chunks.jsonl`.
- Не индексировать `Система` в основной project-only корпус.
- Не переходить к Chat MVP до успешного Search Quality v2.2.
- Не отправлять в LLM сырой hybrid top-k.
