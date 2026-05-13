# Chunking v2.1 Для Asu June Bot

Обновлено: 2026-05-13.

## Назначение

`chunking v2.1` — стратегия подготовки проектных chunks для Asu June Bot.

Цель: перейти от нарезки текста по символам к структурному extraction/chunking по смысловым единицам проектных документов, чтобы бот мог отвечать с точными ссылками на документы, разделы, пункты, строки таблиц и сценарии.

## Ключевое Решение

Asu June Bot строит собственный pipeline v2.1 и не зависит от старого extraction pipeline MeetingAgent.

Старый pipeline остается для MeetingAgent v1:

```text
run_full_rag.ps1
  -> scripts/01_inventory.py
  -> scripts/02_extract_text.py
  -> scripts/03_build_index.py
  -> scripts/05_build_numpy_index.py
```

Новый pipeline Asu June Bot v2.1:

```text
scripts/asu_june_bot_apply_config_v2_1.py
  -> scripts/asu_june_bot_extract_text_v2.py
  -> scripts/asu_june_bot_build_chunks_v2.py
  -> scripts/asu_june_bot_audit_sources_v2.py
  -> future: scripts/asu_june_bot_build_index_v2.py
```

Новый pipeline пишет только в:

```text
data/asu_june_bot/
```

и не трогает:

```text
data/chunks.jsonl
data/embeddings_cache.jsonl
data/numpy_index/
run_full_rag.ps1
```

## Почему Нужен v2.1

В v2 был собран независимый extractor/chunker, но при сканировании всей проектной папки в корпус попадали шумные технические выгрузки:

```text
Система/asu_docs_export
Система/asu_admin_export
site_review_runs
playwright exports
HTML/text exports
HAR dumps
screenshots
```

Для project-only бота эти источники вредят retrieval, потому что создают большое количество `html_text`, `system_export` и `unknown` chunks.

v2.1 фиксирует это:

- исключает шумные технические выгрузки из основного корпуса;
- понижает вес `system_export`;
- улучшает классификацию `document_type`;
- улучшает extraction таблиц DOCX/XLSX;
- добавляет локальный скрипт применения фильтров к `config.yaml`.

## Input Policy v2.1

Основной корпус Asu June Bot должен включать:

```text
ФТТ
ЦТА
ПР
ПМИ
Паспорт ИС
СоИ AD
СоИ Справочники
Руководства
Протоколы
BPMN/PUML/Drawio схемы
рабочие markdown/txt/json/yaml материалы проекта
```

Основной корпус Asu June Bot не должен включать:

```text
**/Система/**
**/asu_docs_export/**
**/asu_admin_export/**
**/docs_html/**
**/docs_text/**
**/pages_html/**
**/pages_text/**
**/site_review_runs/**
**/playwright/**
**/exports/**
**/screenshots/**
**/*.har
**/~$*
**/.~*
**/*.tmp
```

Технические выгрузки могут быть вынесены в отдельный корпус позже:

```text
system_export_corpus
```

Но они не должны попадать в основной project-only corpus.

## Extraction v2.1

Extractor v2.1 создает структурные blocks, а не plain text.

Скрипт:

```text
scripts/asu_june_bot_extract_text_v2.py
```

Выходные файлы:

```text
data/asu_june_bot/extracted_v2/documents.jsonl
data/asu_june_bot/extracted_v2/blocks.jsonl
data/asu_june_bot/extracted_v2/extraction_v2_report.json
data/asu_june_bot/extracted_v2/extraction_v2_report.md
```

### Поддерживаемые форматы extraction v2.1

| Формат | Стратегия |
| --- | --- |
| `.docx` | чтение paragraph/table в исходном порядке Word-документа; эвристика заголовочной строки таблицы |
| `.xlsx` | `openpyxl`; лист + строка таблицы как block; эвристика заголовочной строки |
| `.xlsb` | `pandas` + `pyxlsb`; лист + строка таблицы как block; эвристика заголовочной строки |
| `.pdf` | page block по текстовому слою PDF |
| `.pptx` | slide и shape_text blocks |
| `.html` | формально поддержан, но HTML exports исключаются фильтрами для основного корпуса |
| `.md/.txt/.json/.yml/.yaml/.drawio/.puml/.bpmn/.srt` | text blocks |

### Block Schema v2.1

Минимальная структура block:

```json
{
  "block_id": "...",
  "source_id": "...",
  "block_index": 1,
  "block_type": "table_row",
  "text": "...",
  "relative_path": "...",
  "document_name": "ФТТ.docx",
  "document_type": "ФТТ",
  "source_type": "project_doc",
  "stage": "Этап 1",
  "module": "СМР / Строительный контроль",
  "section": "4.2.5",
  "sections": ["4.2.5"],
  "table_id": "Table 3",
  "row_id": "7",
  "headers": ["Код", "Требование", "Описание"],
  "cells": {
    "Код": "4.2.5",
    "Описание": "..."
  }
}
```

## Главный Принцип Chunking v2.1

```text
Не chunk по символам, а chunk по смысловой единице документа.
```

Смысловая единица зависит от типа документа:

| Тип документа | Atomic child chunk | Parent chunk |
| --- | --- | --- |
| ФТТ | одно требование / пункт / строка таблицы | раздел требований / таблица |
| ЦТА | строка таблицы / архитектурный пункт / поток | раздел архитектуры / таблица |
| СоИ AD | один блок / одна строка маппинга | раздел интеграции / таблица |
| СоИ Справочники | одно поле маппинга / один справочник | справочник целиком / таблица |
| Паспорт ИС | один пункт / один компонент / одна строка таблицы | раздел паспорта |
| ПМИ | один шаг сценария / одно проверяемое требование | сценарий СФТ/СНТ целиком |
| Руководства | один пункт инструкции | раздел руководства |
| Протоколы | одно решение / задача / риск / вопрос | вся встреча / повестка |

## Source Policy v2.1

Default corpus:

```text
project_doc
meeting_artifact
analytical_note
instruction
```

`system_export` не входит в default corpus. Он доступен только при явном запросе по маркерам:

```text
система
системная выгрузка
админка
django admin
asu_admin_export
asu_docs_export
site_review
html export
экспорт сайта
```

Весовые коэффициенты:

```text
project_doc: 1.0
meeting_artifact: 0.9
analytical_note: 0.82
instruction: 0.82
system_export: 0.12
runtime_export: 0.1
code: 0.25
unknown: 0.5
```

Приоритеты типов документов:

```text
ФТТ: 1.25
ЦТА: 1.22
ПР: 1.18
СоИ AD: 1.16
СоИ Справочники: 1.16
Паспорт ИС: 1.12
ПМИ: 1.08
Руководство: 0.98
Протокол: 0.92
Реестр НСИ: 0.88
BPMN / Процесс: 0.84
API: 0.8
Wiki: 0.72
```

## Parent / Child Модель

### Parent chunk

Parent chunk описывает крупный логический блок:

```text
документ -> раздел -> подраздел / таблица / сценарий
```

### Child chunk

Child chunk содержит атомарный факт:

```text
требование, строка таблицы, интеграционный поток, атрибут маппинга, шаг ПМИ, сервис, роль, порт
```

## Retrieval После v2.1

### Точный вопрос

Вопрос:

```text
ФТТ 4.2.5 НОВАДОК ЭЦП
```

Должен работать так:

```text
1. exact match по requirement_id = 4.2.5
2. BM25 по словам НОВАДОК / ЭЦП
3. vector search
4. подтянуть parent chunk раздела 4.2 при необходимости
```

### Обзорный вопрос

Вопрос:

```text
Что входит в Паспорт ИС?
```

Должен работать так:

```text
1. Найти parent chunks Паспорта ИС
2. Сгруппировать разделы
3. Подтянуть child chunks только для уточнения
4. Ответить по структуре документа
```

### Aggregation-вопрос

Вопрос:

```text
Какие интеграции заявлены в проекте?
```

Должен работать так:

```text
1. Искать по document_type = ЦТА / СоИ / ФТТ / ПР
2. Поднимать child chunks с integration/source_system/target_system/protocol
3. Группировать по интеграции
4. Исключать неподтвержденные интеграции
```

## Metadata Schema v2.1

Минимальная схема chunk:

```json
{
  "chunk_id": "...",
  "chunker_version": "v2",
  "chunk_level": "child",
  "parent_chunk_id": "...",
  "project": "ЦП УПКС",
  "document_name": "ФТТ.docx",
  "document_type": "ФТТ",
  "source_type": "project_doc",
  "relative_path": "...",
  "stage": "Этап 1",
  "module": "СМР / Строительный контроль",
  "section": "4.2.5",
  "sections": ["4.2.5"],
  "requirement_id": "4.2.5",
  "scenario_id": null,
  "block_id": "...",
  "block_type": "table_row",
  "table_id": "Table 3",
  "row_id": "7",
  "headers": ["Код", "Требование", "Описание"],
  "cells": {},
  "integration": null,
  "protocol": null,
  "text": "...",
  "text_hash": "..."
}
```

## Выходные Файлы

v2.1 не должен перезаписывать текущий индекс MeetingAgent.

Текущий pipeline:

```text
data/chunks.jsonl
data/embeddings_cache.jsonl
data/numpy_index/
```

v2.1 pipeline:

```text
data/asu_june_bot/extracted_v2/documents.jsonl
data/asu_june_bot/extracted_v2/blocks.jsonl
data/asu_june_bot/extracted_v2/extraction_v2_report.json
data/asu_june_bot/extracted_v2/extraction_v2_report.md
data/asu_june_bot/chunks_v2.jsonl
data/asu_june_bot/chunking_v2_report.json
data/asu_june_bot/chunking_v2_report.md
data/asu_june_bot/source_audit_v2_report.json
```

Индекс v2 будет добавлен отдельно:

```text
data/asu_june_bot/embeddings_cache_v2.jsonl
data/asu_june_bot/numpy_index_v2/
```

## Скрипты

```text
scripts/asu_june_bot_apply_config_v2_1.py
scripts/asu_june_bot_extract_text_v2.py
scripts/asu_june_bot_build_chunks_v2.py
scripts/asu_june_bot_audit_sources_v2.py
run_asu_june_bot_rebuild_v2.ps1
run_asu_june_bot_chunks_v2.ps1
monitor_asu_june_bot_v2.ps1
register_asu_june_bot_v2_watchdog.ps1
```

## Команды

Применить локальный config v2.1:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_apply_config_v2_1.py --project-root "C:\Users\Сотрудник\Desktop\!Проектные документы АСУ"
```

Extraction dry-run:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_extract_text_v2.py --dry-run --limit 5
```

Полная v2.1-пересборка:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_extract_text_v2.py --reset
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py
.\.venv\Scripts\python.exe scripts\asu_june_bot_audit_sources_v2.py
```

## Acceptance Criteria

`extraction/chunking v2.1` считается готовым для первого сравнения с v1, если:

- создан `data/asu_june_bot/extracted_v2/blocks.jsonl`;
- создан `data/asu_june_bot/chunks_v2.jsonl`;
- создан `data/asu_june_bot/source_audit_v2_report.json`;
- старые `data/chunks.jsonl` и `data/numpy_index` не изменены;
- `documents.jsonl` не содержит `/Система/`, `asu_admin_export`, `asu_docs_export`, `site_review_runs`, `playwright`, `.har`;
- у каждого chunk есть `chunker_version = v2`;
- у каждого chunk есть `chunk_level = parent | child`;
- у child chunk из таблицы есть `table_id` и `row_id`;
- у ФТТ chunk по возможности заполнен `requirement_id`;
- у всех chunks есть `source_type`, `document_type`, `relative_path`, `chunk_id`, `text_hash`;
- `unknown` и `system_export` не доминируют в `chunking_v2_report.json`;
- dry-run выводит статистику и не пишет файлы;
- можно сравнить v1 и v2.1 на baseline-вопросах.

## Baseline Для Сравнения v1/v2.1

Минимум:

```text
1. ФТТ 4.2.5 НОВАДОК ЭЦП
2. Какие интеграции заявлены в проекте?
3. Что входит в Паспорт ИС?
4. Как работает интеграция с AD?
5. Какие справочники передаются через MDR?
6. Какие сценарии ПМИ покрывают ФТТ 4.1?
```

## Не Делать До Проверки v2.1

- Не заменять текущий RAG индекс.
- Не считать embeddings v2 до очистки корпуса.
- Не подключать LLM.
- Не менять `run_full_rag.ps1`.
- Не индексировать папку `Система` в основной project-only corpus.
