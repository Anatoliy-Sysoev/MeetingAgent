# Runbook v2: Запуск И Мониторинг Asu June Bot

Обновлено: 2026-05-12.

## Назначение

Документ описывает запуск независимого pipeline Asu June Bot v2:

```text
extract_text_v2 -> chunks_v2 -> future index_v2
```

Pipeline v2 не использует старый `scripts/02_extract_text.py`, не запускает `run_full_rag.ps1` и не изменяет старые файлы:

```text
data/chunks.jsonl
data/embeddings_cache.jsonl
data/numpy_index/
```

Все runtime-данные v2 пишутся в:

```text
data/asu_june_bot/
```

## Файлы Pipeline v2

### Скрипты

```text
scripts/asu_june_bot_extract_text_v2.py
scripts/asu_june_bot_build_chunks_v2.py
run_asu_june_bot_rebuild_v2.ps1
run_asu_june_bot_chunks_v2.ps1
monitor_asu_june_bot_v2.ps1
register_asu_june_bot_v2_watchdog.ps1
```

### Выходные файлы extraction v2

```text
data/asu_june_bot/extracted_v2/documents.jsonl
data/asu_june_bot/extracted_v2/blocks.jsonl
data/asu_june_bot/extracted_v2/errors.jsonl
data/asu_june_bot/extracted_v2/extraction_v2_progress.json
data/asu_june_bot/extracted_v2/extraction_v2_report.json
data/asu_june_bot/extracted_v2/extraction_v2_report.md
```

### Выходные файлы chunking v2

```text
data/asu_june_bot/chunks_v2.jsonl
data/asu_june_bot/chunking_v2_report.json
data/asu_june_bot/chunking_v2_report.md
```

### Логи и маркеры

```text
logs/asu_june_bot_rebuild_v2_*.log
logs/asu_june_bot_rebuild_v2_*.done.txt
logs/asu_june_bot_rebuild_v2_*.failed.txt
logs/asu_june_bot_v2_watchdog.log
logs/.asu_june_bot_v2_watchdog_state.json
```

## Важное Правило Resume

Extractor v2 поддерживает продолжение после прерывания.

Механизм:

1. При успешной обработке файла extractor сразу дописывает source в `documents.jsonl`.
2. Blocks этого source сразу дописываются в `blocks.jsonl`.
3. При следующем запуске extractor читает `documents.jsonl`.
4. Уже обработанные `source_id` пропускаются.
5. Обрабатываются только недостающие файлы.

Это значит, что повторный запуск не начинает сканирование заново.

Если нужно начать полностью с нуля, использовать только явный флаг:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_extract_text_v2.py --reset
```

Без `--reset` работает resume.

## Ручной Запуск

### 1. Перейти в проект

```powershell
cd C:\Users\Сотрудник\Desktop\AI\MeetingAgent
```

### 2. Обновить ветку

```powershell
git pull
```

### 3. Dry-run extraction v2

Ничего не записывает, только проверяет запуск:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_extract_text_v2.py --dry-run --limit 5
```

### 4. Запуск extraction v2 только по ФТТ

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_extract_text_v2.py --path-contains "ФТТ"
```

### 5. Проверка результата extraction

```powershell
Get-Content .\data\asu_june_bot\extracted_v2\extraction_v2_report.json
(Get-Content .\data\asu_june_bot\extracted_v2\documents.jsonl).Count
(Get-Content .\data\asu_june_bot\extracted_v2\blocks.jsonl).Count
Select-String -Path .\data\asu_june_bot\extracted_v2\blocks.jsonl -Pattern '"block_type": "table_row"' | Select-Object -First 10
```

### 6. Chunking v2 после extraction

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py --dry-run --limit 5
```

Если dry-run успешен:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py
```

### 7. Полный rebuild v2

Запускает extraction v2 и chunking v2:

```powershell
.\run_asu_june_bot_rebuild_v2.ps1
```

## Мониторинг Каждые 15 Минут

### Что делает monitor

`monitor_asu_june_bot_v2.ps1` — single-tick watchdog.

Один запуск делает одну проверку:

1. Проверяет, есть ли живой процесс `run_asu_june_bot_rebuild_v2.ps1`.
2. Проверяет, есть ли живой extractor `asu_june_bot_extract_text_v2.py`.
3. Проверяет, есть ли живой chunker `asu_june_bot_build_chunks_v2.py`.
4. Считает строки в:
   - `documents.jsonl`;
   - `blocks.jsonl`;
   - `chunks_v2.jsonl`.
5. Если процесс жив — пишет статус и ничего не перезапускает.
6. Если есть валидный `.done.txt` и результаты существуют — завершает проверку и больше ничего не запускает.
7. Если процесс не жив и `.done.txt` нет — запускает rebuild v2.
8. Если был сбой — следующий запуск продолжит extraction по resume-механизму.

Важно: monitor сам не висит постоянно. Его нужно запускать планировщиком каждые 15 минут.

### Ручной одинарный запуск monitor

```powershell
.\monitor_asu_june_bot_v2.ps1
```

### Регистрация задачи Windows Task Scheduler

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

### Запустить задачу сразу

```powershell
Start-ScheduledTask -TaskName AsuJuneBotV2Watchdog
```

### Проверить задачу

```powershell
Get-ScheduledTask -TaskName AsuJuneBotV2Watchdog
Get-ScheduledTaskInfo -TaskName AsuJuneBotV2Watchdog
```

### Смотреть watchdog log

```powershell
Get-Content .\logs\asu_june_bot_v2_watchdog.log -Tail 80
```

### Смотреть последний rebuild log

```powershell
Get-ChildItem .\logs\asu_june_bot_rebuild_v2_*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content -Tail 100
```

### Остановить задачу

```powershell
Stop-ScheduledTask -TaskName AsuJuneBotV2Watchdog
```

### Удалить задачу

```powershell
Unregister-ScheduledTask -TaskName AsuJuneBotV2Watchdog -Confirm:$false
```

## Как Понять, Что Сканирование Завершено

Условия готовности:

1. Есть done marker:

```powershell
Get-ChildItem .\logs\asu_june_bot_rebuild_v2_*.done.txt | Sort-Object LastWriteTime -Descending | Select-Object -First 1
```

2. Есть blocks:

```powershell
Test-Path .\data\asu_june_bot\extracted_v2\blocks.jsonl
```

3. Есть chunks:

```powershell
Test-Path .\data\asu_june_bot\chunks_v2.jsonl
```

4. Есть chunking report:

```powershell
Test-Path .\data\asu_june_bot\chunking_v2_report.json
```

Если все условия выполнены, monitor пишет:

```text
Asu June Bot v2 rebuild complete. Watchdog will not restart it.
```

## Как Продолжить После Прерывания

Ничего специального делать не нужно.

Если процесс прервался, следующий запуск:

```powershell
.\monitor_asu_june_bot_v2.ps1
```

или Task Scheduler через 15 минут запустит:

```powershell
.\run_asu_june_bot_rebuild_v2.ps1
```

Extractor v2 увидит уже обработанные `source_id` в `documents.jsonl` и пропустит их.

## Как Начать Полностью Заново

Остановить задачу:

```powershell
Stop-ScheduledTask -TaskName AsuJuneBotV2Watchdog
```

Удалить runtime-данные v2:

```powershell
Remove-Item .\data\asu_june_bot\extracted_v2 -Recurse -Force
Remove-Item .\data\asu_june_bot\chunks_v2.jsonl -Force -ErrorAction SilentlyContinue
Remove-Item .\data\asu_june_bot\chunking_v2_report.json -Force -ErrorAction SilentlyContinue
Remove-Item .\data\asu_june_bot\chunking_v2_report.md -Force -ErrorAction SilentlyContinue
```

Запустить заново:

```powershell
.\run_asu_june_bot_rebuild_v2.ps1
```

## Что Проверить После Первого Полного Прогона

```powershell
Get-Content .\data\asu_june_bot\extracted_v2\extraction_v2_report.json
Get-Content .\data\asu_june_bot\chunking_v2_report.json
(Get-Content .\data\asu_june_bot\extracted_v2\documents.jsonl).Count
(Get-Content .\data\asu_june_bot\extracted_v2\blocks.jsonl).Count
(Get-Content .\data\asu_june_bot\chunks_v2.jsonl).Count
```

Проверить таблицы:

```powershell
Select-String -Path .\data\asu_june_bot\extracted_v2\blocks.jsonl -Pattern '"block_type": "table_row"' | Select-Object -First 20
```

Проверить требования ФТТ:

```powershell
Select-String -Path .\data\asu_june_bot\chunks_v2.jsonl -Pattern '"requirement_id": "4.2.5"'
```

## Ограничения Текущей Версии

- Monitor не убивает зависший python-процесс автоматически; он только фиксирует stall-warning.
- Resume работает на уровне успешно записанных `source_id`.
- Если файл был частично обработан, но source не записался в `documents.jsonl`, он будет обработан повторно.
- Chunking v2 пока пересобирает `chunks_v2.jsonl` целиком из готовых blocks.
- Vector index v2 еще не реализован.
