# Asu June Bot v2.1 Runbook

Обновлено: 2026-05-14.

## Назначение

Инструкция запуска независимого pipeline Asu June Bot v2.1:

```text
apply_config_v2_1 -> extract_text_v2 -> chunks_v2 -> audit_sources_v2 -> build_index_v2 -> health_v2 -> search_v2
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

## Что изменилось в v2.1

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

## 4. BM25 smoke

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

## 5. Vector smoke

Требует `vector_ready = true` из health check.

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Что входит в Паспорт ИС?" --mode vector --top-k 8
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Какие интеграции заявлены в проекте?" --mode vector --top-k 8
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "ФТТ 4.2.5 НОВАДОК ЭЦП" --mode vector --top-k 8
```

## 6. Hybrid smoke

Требует Ollama для vector-части. Если Ollama выключен, `hybrid` вернет BM25 fallback с предупреждением.

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Что входит в Паспорт ИС?" --mode hybrid --top-k 8
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Какие интеграции заявлены в проекте?" --mode hybrid --top-k 8
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "ФТТ 4.2.5 НОВАДОК ЭЦП" --mode hybrid --top-k 8
```

## 7. JSON smoke для анализа retrieval

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Какие интеграции заявлены в проекте?" --mode hybrid --top-k 12 --json > .\data\asu_june_bot\smoke_integrations_hybrid.json
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Что входит в Паспорт ИС?" --mode hybrid --top-k 12 --json > .\data\asu_june_bot\smoke_passport_hybrid.json
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "ФТТ 4.2.5 НОВАДОК ЭЦП" --mode hybrid --top-k 12 --json > .\data\asu_june_bot\smoke_ftt_425_hybrid.json
```

## 8. Полная пересборка v2.1 при изменении корпуса

Если меняются фильтры, список файлов или правила extraction/chunking, пересобрать с нуля:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_extract_text_v2.py --reset
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py
.\.venv\Scripts\python.exe scripts\asu_june_bot_audit_sources_v2.py
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_index_v2.py --embed-only
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_index_v2.py --index-only
.\.venv\Scripts\python.exe scripts\asu_june_bot_health_v2.py
```

## 9. Проверка extraction/chunking

Для Windows PowerShell 5.1 всегда указывать `-Encoding UTF8` при чтении отчетов.

```powershell
Get-Content .\data\asu_june_bot\extracted_v2\extraction_v2_report.json -Encoding UTF8
Get-Content .\data\asu_june_bot\chunking_v2_report.json -Encoding UTF8
Get-Content .\data\asu_june_bot\source_audit_v2_report.json -Encoding UTF8
Get-Content .\data\asu_june_bot\index_v2_report.json -Encoding UTF8
Get-Content .\data\asu_june_bot\numpy_index_v2\manifest.json -Encoding UTF8
```

## 10. Watchdog для долгого embeddings cache

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

## 11. Что считать успешным завершением

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

## 12. Не делать

- Не удалять `data/asu_june_bot/`, если нужно продолжить после прерывания.
- Не запускать `--reset`, если нужна resume-сборка.
- Не менять старый `run_full_rag.ps1`.
- Не перезаписывать `data/chunks.jsonl`.
- Не индексировать `Система` в основной project-only корпус.
- Не переходить к Chat MVP до успешного hybrid smoke.
