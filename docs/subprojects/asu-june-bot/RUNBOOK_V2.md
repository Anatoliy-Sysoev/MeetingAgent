# Asu June Bot v2 Runbook

Обновлено: 2026-05-13.

## Назначение

Инструкция запуска независимого pipeline Asu June Bot v2:

```text
extract_text_v2 -> chunks_v2 -> future index_v2
```

Pipeline v2 не использует старый `scripts/02_extract_text.py` и не меняет старые runtime-файлы MeetingAgent:

```text
data/chunks.jsonl
data/embeddings_cache.jsonl
data/numpy_index/
```

Все новые данные пишутся в:

```text
data/asu_june_bot/
```

## 1. Обновить ветку

```powershell
cd C:\Users\Сотрудник\Desktop\AI\MeetingAgent
git checkout docs/asu-june-bot-subproject
git pull
```

## 2. Первый безопасный dry-run

Dry-run ничего не пишет на диск.

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_extract_text_v2.py --dry-run --limit 5
```

Ожидаемо:

- команда завершается без ошибки;
- в выводе есть `candidate_sources_total`, `pending_sources_this_run`, `blocks_extracted_this_run`;
- файлы в `data/asu_june_bot/extracted_v2/` не создаются.

## 3. Extraction v2 только по ФТТ

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_extract_text_v2.py --path-contains "ФТТ"
```

Проверка:

```powershell
Get-Content .\data\asu_june_bot\extracted_v2\extraction_v2_report.json
(Get-Content .\data\asu_june_bot\extracted_v2\blocks.jsonl).Count
Select-String -Path .\data\asu_june_bot\extracted_v2\blocks.jsonl -Pattern '"block_type": "table_row"' | Select-Object -First 10
```

## 4. Chunking v2 после extraction

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py --dry-run --limit 5
```

Если dry-run без ошибок:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py --path-contains "ФТТ"
```

Проверка:

```powershell
Get-Content .\data\asu_june_bot\chunking_v2_report.json
(Get-Content .\data\asu_june_bot\chunks_v2.jsonl).Count
Select-String -Path .\data\asu_june_bot\chunks_v2.jsonl -Pattern '"requirement_id": "4.2.5"'
```

## 5. Полная пересборка v2 вручную

```powershell
.\run_asu_june_bot_rebuild_v2.ps1
```

Этот wrapper запускает:

```text
scripts/asu_june_bot_extract_text_v2.py
scripts/asu_june_bot_build_chunks_v2.py
```

Логи:

```text
logs/asu_june_bot_rebuild_v2_*.log
logs/asu_june_bot_rebuild_v2_*.done.txt
logs/asu_june_bot_rebuild_v2_*.failed.txt
```

## 6. Resume-поведение

Extractor v2 поддерживает resume.

При повторном запуске он:

1. читает `data/asu_june_bot/extracted_v2/documents.jsonl`;
2. определяет уже успешно обработанные `source_id`;
3. пропускает их;
4. дописывает только недостающие документы и blocks.

То есть при прерывании не нужно удалять папку `data/asu_june_bot/`.

Для принудительного полного старта с нуля:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_extract_text_v2.py --reset
```

Использовать `--reset` только осознанно: он удаляет output-директорию extraction v2.

## 7. Аудит покрытия источников

После extraction/chunking нужно проверить, какие файлы реально попали в v2 pipeline, а какие были исключены фильтрами.

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

Проверка отчета:

```powershell
Get-Content .\data\asu_june_bot\source_audit_v2_report.json
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

Если `included_not_extracted > 0`, нужно смотреть `included_not_extracted_sample`.

## 8. Watchdog / мониторинг каждые 15 минут

### 8.1. Один ручной тик мониторинга

```powershell
.\monitor_asu_june_bot_v2.ps1
```

Что делает tick:

- проверяет, запущен ли `run_asu_june_bot_rebuild_v2.ps1`;
- проверяет, запущен ли `asu_june_bot_extract_text_v2.py`;
- проверяет, запущен ли `asu_june_bot_build_chunks_v2.py`;
- считает строки в:
  - `documents.jsonl`;
  - `blocks.jsonl`;
  - `chunks_v2.jsonl`;
- если всё завершено и есть done marker — больше не перезапускает;
- если процесс не запущен и done marker отсутствует — запускает rebuild;
- если был сбой — следующий tick продолжит extraction за счет resume-режима.

### 8.2. Зарегистрировать задачу Windows Task Scheduler

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

### 8.3. Запустить задачу сразу

```powershell
Start-ScheduledTask -TaskName AsuJuneBotV2Watchdog
```

### 8.4. Проверить задачу

```powershell
Get-ScheduledTask -TaskName AsuJuneBotV2Watchdog
Get-ScheduledTaskInfo -TaskName AsuJuneBotV2Watchdog
```

### 8.5. Удалить задачу

```powershell
Unregister-ScheduledTask -TaskName AsuJuneBotV2Watchdog -Confirm:$false
```

## 9. Проверка статуса

### Последний watchdog log

```powershell
Get-Content .\logs\asu_june_bot_v2_watchdog.log -Tail 80
```

### Последний rebuild log

```powershell
Get-ChildItem .\logs\asu_june_bot_rebuild_v2_*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content -Tail 120
```

### Done / failed markers

```powershell
Get-ChildItem .\logs\asu_june_bot_rebuild_v2_*.done.txt | Sort-Object LastWriteTime -Descending | Select-Object -First 3
Get-ChildItem .\logs\asu_june_bot_rebuild_v2_*.failed.txt | Sort-Object LastWriteTime -Descending | Select-Object -First 3
```

### Progress extraction

```powershell
Get-Content .\data\asu_june_bot\extracted_v2\extraction_v2_progress.json
```

### Counts

```powershell
'documents=' + (Get-Content .\data\asu_june_bot\extracted_v2\documents.jsonl).Count
'blocks=' + (Get-Content .\data\asu_june_bot\extracted_v2\blocks.jsonl).Count
'chunks=' + (Get-Content .\data\asu_june_bot\chunks_v2.jsonl).Count
```

## 10. Что считать успешным завершением

Успешное завершение:

```text
logs/asu_june_bot_rebuild_v2_*.done.txt существует
logs/asu_june_bot_rebuild_v2_*.failed.txt отсутствует или старее done marker
существует data/asu_june_bot/extracted_v2/blocks.jsonl
существует data/asu_june_bot/chunks_v2.jsonl
существует data/asu_june_bot/chunking_v2_report.json
```

Watchdog после этого должен писать:

```text
Current status: done
Action taken: none
```

## 11. Что делать при ошибке

1. Посмотреть последний failed marker:

```powershell
Get-ChildItem .\logs\asu_june_bot_rebuild_v2_*.failed.txt | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content
```

2. Посмотреть лог:

```powershell
Get-ChildItem .\logs\asu_june_bot_rebuild_v2_*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content -Tail 200
```

3. Запустить watchdog tick вручную:

```powershell
.\monitor_asu_june_bot_v2.ps1
```

Если ошибка была временной, следующий запуск продолжит extraction с необработанных файлов.

## 12. Не делать

- Не удалять `data/asu_june_bot/`, если нужно продолжить после прерывания.
- Не запускать `--reset`, если нужна resume-сборка.
- Не менять старый `run_full_rag.ps1`.
- Не перезаписывать `data/chunks.jsonl`.
- Не подключать `chunks_v2` к search до проверки качества extraction/chunking.
