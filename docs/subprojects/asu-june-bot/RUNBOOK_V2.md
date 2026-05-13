# Asu June Bot v2.1 Runbook

Обновлено: 2026-05-13.

## Назначение

Инструкция запуска независимого pipeline Asu June Bot v2.1:

```text
apply_config_v2_1 -> extract_text_v2 -> chunks_v2 -> audit_sources_v2 -> future index_v2
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

```powershell
Get-Content .\data\asu_june_bot\extracted_v2\extraction_v2_report.json
(Get-Content .\data\asu_june_bot\extracted_v2\documents.jsonl).Count
(Get-Content .\data\asu_june_bot\extracted_v2\blocks.jsonl).Count
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
Get-Content .\data\asu_june_bot\chunking_v2_report.json
(Get-Content .\data\asu_june_bot\chunks_v2.jsonl).Count
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
$report = Get-Content .\data\asu_june_bot\source_audit_v2_report.json -Raw | ConvertFrom-Json
$report.excluded_by_reason.path_pattern_excluded.sample | Select-String "Система"
```

## 8. Watchdog / мониторинг каждые 15 минут

### 8.1. Один ручной тик мониторинга

```powershell
.\monitor_asu_june_bot_v2.ps1
```

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
source_audit_v2_report.json показывает, что Система исключена
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

## 12. Следующий этап после v2.1

После успешной проверки v2.1 можно делать:

```text
scripts/asu_june_bot_build_index_v2.py
```

Целевые выходы:

```text
data/asu_june_bot/embeddings_cache_v2.jsonl
data/asu_june_bot/numpy_index_v2/
```

До проверки v2.1 index v2 собирать не нужно.

## 13. Не делать

- Не удалять `data/asu_june_bot/`, если нужно продолжить после прерывания.
- Не запускать `--reset`, если нужна resume-сборка.
- Не менять старый `run_full_rag.ps1`.
- Не перезаписывать `data/chunks.jsonl`.
- Не подключать `chunks_v2` к search до проверки качества extraction/chunking.
- Не индексировать `Система` в основной project-only корпус.
