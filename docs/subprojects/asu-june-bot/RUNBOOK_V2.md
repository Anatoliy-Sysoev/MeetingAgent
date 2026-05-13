# Asu June Bot v2.1 Runbook

Обновлено: 2026-05-13.

## Назначение

Инструкция запуска независимого pipeline Asu June Bot v2.1:

```text
apply_config_v2_1 -> extract_text_v2 -> chunks_v2 -> audit_sources_v2 -> build_index_v2 -> search_v2
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

## 1. Обновить ветку

```powershell
cd C:\Users\Сотрудник\Desktop\AI\MeetingAgent
git checkout docs/asu-june-bot-subproject
git pull
```

## 2. Применить локальный config v2.1

`config.yaml` локальный и обычно не хранится в GitHub, поэтому его нужно обновить отдельной командой.

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_apply_config_v2_1.py --project-root "C:\Users\Сотрудник\Desktop\!Проектные документы АСУ"
```

Скрипт делает backup:

```text
config.yaml.bak_v2_1_YYYYMMDD_HHMMSS
```

Проверка:

```powershell
Select-String -Path .\config.yaml -Pattern "^project_root:"
Select-String -Path .\config.yaml -Pattern "\*\*/Система/\*\*"
Select-String -Path .\config.yaml -Pattern "\.har"
```

Ожидаемый `project_root`:

```yaml
project_root: C:/Users/Сотрудник/Desktop/!Проектные документы АСУ
```

## 3. Первый безопасный dry-run

Dry-run ничего не пишет на диск.

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_extract_text_v2.py --dry-run --limit 5
```

Ожидаемо:

- команда завершается без ошибки;
- в выводе есть `candidate_sources_total`, `pending_sources_this_run`, `blocks_extracted_this_run`;
- файлы в `data/asu_june_bot/extracted_v2/` не создаются.

## 4. Полная пересборка v2.1

После изменения фильтров нужно пересобрать extraction с нуля. Иначе будут смешаны старые chunks с шумной папкой `Система` и новые chunks без неё.

```powershell
Remove-Item .\logs\asu_june_bot_rebuild_v2_*.done.txt -ErrorAction SilentlyContinue
Remove-Item .\logs\asu_june_bot_rebuild_v2_*.failed.txt -ErrorAction SilentlyContinue

.\.venv\Scripts\python.exe scripts\asu_june_bot_extract_text_v2.py --reset
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py
.\.venv\Scripts\python.exe scripts\asu_june_bot_audit_sources_v2.py
```

Или wrapper:

```powershell
Remove-Item .\logs\asu_june_bot_rebuild_v2_*.done.txt -ErrorAction SilentlyContinue
Remove-Item .\logs\asu_june_bot_rebuild_v2_*.failed.txt -ErrorAction SilentlyContinue

.\run_asu_june_bot_rebuild_v2.ps1
.\.venv\Scripts\python.exe scripts\asu_june_bot_audit_sources_v2.py
```

## 5. Проверка extraction

Для Windows PowerShell 5.1 всегда указывать `-Encoding UTF8` при чтении отчетов.

```powershell
Get-Content .\data\asu_june_bot\extracted_v2\extraction_v2_report.json -Encoding UTF8
(Get-Content .\data\asu_june_bot\extracted_v2\documents.jsonl -Encoding UTF8).Count
(Get-Content .\data\asu_june_bot\extracted_v2\blocks.jsonl -Encoding UTF8).Count
Select-String -Path .\data\asu_june_bot\extracted_v2\blocks.jsonl -Pattern '"block_type": "table_row"' | Select-Object -First 10
```

Ключевой контроль:

```powershell
Select-String -Path .\data\asu_june_bot\extracted_v2\documents.jsonl -Pattern '/Система/'
Select-String -Path .\data\asu_june_bot\extracted_v2\documents.jsonl -Pattern 'asu_admin_export|asu_docs_export|site_review_runs|playwright|\.har'
```

Ожидаемо: команды не должны находить строки.

## 6. Проверка chunking

```powershell
Get-Content .\data\asu_june_bot\chunking_v2_report.json -Encoding UTF8
(Get-Content .\data\asu_june_bot\chunks_v2.jsonl -Encoding UTF8).Count
Select-String -Path .\data\asu_june_bot\chunks_v2.jsonl -Pattern '"requirement_id": "4.2.5"'
Select-String -Path .\data\asu_june_bot\chunks_v2.jsonl -Pattern '"document_type": "ФТТ"' | Select-Object -First 5
Select-String -Path .\data\asu_june_bot\chunks_v2.jsonl -Pattern '"document_type": "ЦТА"' | Select-Object -First 5
Select-String -Path .\data\asu_june_bot\chunks_v2.jsonl -Pattern '"document_type": "Паспорт ИС"' | Select-Object -First 5
```

## 7. Аудит покрытия источников

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_audit_sources_v2.py
```

Подробный JSON:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_audit_sources_v2.py --json
```

Отчет сохраняется в:

```text
data/asu_june_bot/source_audit_v2_report.json
```

Ключевые поля:

```text
summary.all_files_seen                  все файлы, увиденные в project_root
summary.included_by_config              файлы, прошедшие фильтры config.yaml
summary.documents_jsonl                 файлы, успешно записанные в documents.jsonl
summary.blocks_jsonl                    количество extracted blocks
summary.chunks_jsonl                    количество chunks
summary.included_not_extracted          прошли фильтры, но не попали в documents.jsonl
excluded_by_reason                      почему файлы исключены
```

Проверка исключения `Система`:

```powershell
$report = Get-Content .\data\asu_june_bot\source_audit_v2_report.json -Encoding UTF8 -Raw | ConvertFrom-Json
$report.excluded_by_reason.hard_excluded_directory.sample | Select-String "Система"
$report.excluded_by_reason.hard_excluded_path.sample | Select-String "Система"
```

## 8. BM25 smoke до embeddings

До долгой векторизации можно проверить качество `chunks_v2` через BM25:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Что входит в Паспорт ИС?" --mode bm25 --top-k 5
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Какие интеграции заявлены в проекте?" --mode bm25 --top-k 5
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "ФТТ 4.2.5 НОВАДОК ЭЦП" --mode bm25 --top-k 5
```

Если BM25 не находит ожидаемые документы, index v2 строить рано.

## 9. Smoke embeddings на малом лимите

Перед полной векторизацией проверить Ollama embeddings на 20 chunks:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_index_v2.py --limit 20 --embed-only
```

Проверить отчет:

```powershell
Get-Content .\data\asu_june_bot\index_v2_report.json -Encoding UTF8
```

Если `missing_after = 0` для limit 20, можно переходить к полному cache.

## 10. Полный embeddings cache v2

Это долгий этап на CPU. Resume встроен через `embeddings_cache_v2.jsonl`: при повторном запуске уже посчитанные chunks пропускаются.

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_index_v2.py --embed-only
```

Проверять прогресс:

```powershell
(Get-Content .\data\asu_june_bot\embeddings_cache_v2.jsonl -Encoding UTF8).Count
```

## 11. Построить numpy_index_v2 из готового cache

Когда cache заполнен:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_index_v2.py --index-only
```

Ожидаемые файлы:

```text
data/asu_june_bot/numpy_index_v2/manifest.json
data/asu_june_bot/numpy_index_v2/embeddings.npy
data/asu_june_bot/numpy_index_v2/metadata.jsonl
data/asu_june_bot/index_v2_report.json
```

Проверка:

```powershell
Get-Content .\data\asu_june_bot\numpy_index_v2\manifest.json -Encoding UTF8
```

## 12. Hybrid/vector smoke по v2 index

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Что входит в Паспорт ИС?" --mode hybrid --top-k 8
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "Какие интеграции заявлены в проекте?" --mode hybrid --top-k 8
.\.venv\Scripts\python.exe scripts\asu_june_bot_search_v2.py "ФТТ 4.2.5 НОВАДОК ЭЦП" --mode hybrid --top-k 8
```

## 13. Watchdog / мониторинг каждые 15 минут

### 13.1. Один ручной тик мониторинга

```powershell
.\monitor_asu_june_bot_v2.ps1
```

### 13.2. Зарегистрировать задачу Windows Task Scheduler

```powershell
.\register_asu_june_bot_v2_watchdog.ps1
```

По умолчанию создается задача:

```text
AsuJuneBotV2Watchdog
```

Интервал:

```text
каждые 15 минут
```

### 13.3. Запустить задачу сразу

```powershell
Start-ScheduledTask -TaskName AsuJuneBotV2Watchdog
```

### 13.4. Проверить задачу

```powershell
Get-ScheduledTask -TaskName AsuJuneBotV2Watchdog
Get-ScheduledTaskInfo -TaskName AsuJuneBotV2Watchdog
```

### 13.5. Удалить задачу

```powershell
Unregister-ScheduledTask -TaskName AsuJuneBotV2Watchdog -Confirm:$false
```

## 14. Проверка статуса

### Последний watchdog log

```powershell
Get-Content .\logs\asu_june_bot_v2_watchdog.log -Encoding UTF8 -Tail 80
```

### Последний rebuild log

```powershell
Get-ChildItem .\logs\asu_june_bot_rebuild_v2_*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content -Encoding UTF8 -Tail 120
```

### Done / failed markers

```powershell
Get-ChildItem .\logs\asu_june_bot_rebuild_v2_*.done.txt | Sort-Object LastWriteTime -Descending | Select-Object -First 3
Get-ChildItem .\logs\asu_june_bot_rebuild_v2_*.failed.txt | Sort-Object LastWriteTime -Descending | Select-Object -First 3
```

### Counts

```powershell
'documents=' + (Get-Content .\data\asu_june_bot\extracted_v2\documents.jsonl -Encoding UTF8).Count
'blocks=' + (Get-Content .\data\asu_june_bot\extracted_v2\blocks.jsonl -Encoding UTF8).Count
'chunks=' + (Get-Content .\data\asu_june_bot\chunks_v2.jsonl -Encoding UTF8).Count
'embeddings=' + (Get-Content .\data\asu_june_bot\embeddings_cache_v2.jsonl -Encoding UTF8).Count
```

## 15. Что считать успешным завершением

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
manifest.count = chunks_total
search_v2 --mode hybrid возвращает релевантные ФТТ/ЦТА/ПР/Паспорт/СоИ
```

## 16. Что делать при ошибке

1. Посмотреть последний failed marker:

```powershell
Get-ChildItem .\logs\asu_june_bot_rebuild_v2_*.failed.txt | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content -Encoding UTF8
```

2. Посмотреть лог:

```powershell
Get-ChildItem .\logs\asu_june_bot_rebuild_v2_*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content -Encoding UTF8 -Tail 200
```

3. Запустить watchdog tick вручную:

```powershell
.\monitor_asu_june_bot_v2.ps1
```

Если ошибка была временной, следующий запуск продолжит extraction с необработанных файлов.

## 17. Не делать

- Не удалять `data/asu_june_bot/`, если нужно продолжить после прерывания.
- Не запускать `--reset`, если нужна resume-сборка.
- Не менять старый `run_full_rag.ps1`.
- Не перезаписывать `data/chunks.jsonl`.
- Не индексировать `Система` в основной project-only корпус.
- Не собирать полный embeddings cache, если BM25 smoke уже показывает плохое качество chunks.
