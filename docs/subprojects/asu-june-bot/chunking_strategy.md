# Chunking v2.1 для Project Knowledge Bot

Обновлено: 2026-05-16.

## Назначение

`chunking v2.1` — стратегия подготовки структурированных chunks для Project Knowledge Bot.

Цель: перейти от нарезки текста по символам к extraction/chunking по смысловым единицам проектных документов, чтобы бот мог отвечать с точными ссылками на документы, разделы, пункты, строки таблиц, интеграционные потоки и сценарии.

Историческое имя пакета и runtime-путей остается `asu_june_bot`.

## Текущий статус

Стратегия v2.1 реализована и используется в текущем runtime.

Подтвержденный срез:

```text
documents = 213
blocks = 31076
chunks_v2 = 31302
indexed_chunks = 31285
skipped_code_chunks = 17
embedding_model = bge-m3
embedding_dim = 1024
```

Дальнейшее развитие chunking/context связано с quality hardening:

```text
QH-1 baseline eval
QH-2 Source Quality Filter
QH-3 Parent Expansion
```

## Ключевое решение

Project Knowledge Bot строит собственный pipeline v2.1 и не зависит от старого extraction pipeline MeetingAgent.

Старый pipeline остается для MeetingAgent v1/baseline:

```text
run_full_rag.ps1
  -> scripts/01_inventory.py
  -> scripts/02_extract_text.py
  -> scripts/03_build_index.py
  -> scripts/05_build_numpy_index.py
```

Новый pipeline:

```text
scripts/asu_june_bot_apply_config_v2_1.py
  -> scripts/asu_june_bot_extract_text_v2.py
  -> scripts/asu_june_bot_build_chunks_v2.py
  -> scripts/asu_june_bot_audit_sources_v2.py
  -> scripts/asu_june_bot_build_index_v2.py
  -> scripts/asu_june_bot_health_v2.py
  -> scripts/asu_june_bot_search_v2.py
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

## Почему нужен v2.1

В раннем v2 при сканировании всей проектной папки в корпус попадали шумные технические выгрузки:

```text
system exports
HTML/text exports
HAR dumps
screenshots
playwright/site review exports
runtime exports
```

Для project-only бота эти источники вредят retrieval, потому что создают большое количество `html_text`, `system_export` и `unknown` chunks.

v2.1 фиксирует это:

- исключает шумные технические выгрузки из основного корпуса;
- понижает вес `system_export`;
- улучшает классификацию `document_type`;
- улучшает extraction таблиц DOCX/XLSX;
- добавляет локальный скрипт применения фильтров к `config.yaml`.

## Input Policy v2.1

Основной корпус должен включать:

```text
требования
целевая архитектура
проектные решения
программа и методика испытаний
паспорт информационной системы
соглашения об интеграции
руководства
протоколы
BPMN/PUML/Drawio схемы
рабочие markdown/txt/json/yaml материалы проекта
```

Основной корпус не должен включать:

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
  "document_name": "...",
  "document_type": "...",
  "source_type": "project_doc",
  "stage": "...",
  "module": "...",
  "section": "...",
  "sections": ["..."],
  "table_id": "Table 3",
  "row_id": "7",
  "headers": ["Код", "Требование", "Описание"],
  "cells": {
    "Код": "...",
    "Описание": "..."
  }
}
```

## Главный принцип chunking v2.1

```text
Не chunk по символам, а chunk по смысловой единице документа.
```

Смысловая единица зависит от типа документа:

| Тип документа | Atomic child chunk | Parent chunk |
| --- | --- | --- |
| Требования | одно требование / пункт / строка таблицы | раздел требований / таблица |
| Архитектура | строка таблицы / архитектурный пункт / поток | раздел архитектуры / таблица |
| Соглашение об интеграции | один блок / одна строка маппинга | раздел интеграции / таблица |
| Справочники / НСИ | одно поле маппинга / один справочник | справочник целиком / таблица |
| Паспорт ИС | один пункт / один компонент / одна строка таблицы | раздел паспорта |
| ПМИ | один шаг сценария / одно проверяемое требование | сценарий целиком |
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

`system_export` не входит в default corpus. Он доступен только при явном запросе по маркерам технических выгрузок.

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

## Parent / Child модель

### Parent chunk

Parent chunk описывает крупный логический блок:

```text
документ -> раздел -> подраздел / таблица / сценарий
```

### Child chunk

Child chunk содержит атомарный факт:

```text
требование, строка таблицы, интеграционный поток, атрибут маппинга, шаг сценария, сервис, роль, порт
```

## Retrieval после v2.1

### Точный вопрос

Пример:

```text
пункт требования + название интеграции / технологии
```

Должен работать так:

```text
1. exact match по requirement_id / section
2. BM25 по ключевым словам
3. vector search
4. подтянуть parent chunk при необходимости
```

### Обзорный вопрос

Пример:

```text
Что входит в Паспорт ИС?
```

Должен работать так:

```text
1. Найти parent chunks документа
2. Сгруппировать разделы
3. Подтянуть child chunks только для уточнения
4. Ответить по структуре документа
```

### Aggregation-вопрос

Пример:

```text
Какие интеграции заявлены в проектных документах?
```

Должен работать так:

```text
1. Искать по document_type = архитектура / соглашение / требования / проектное решение
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
  "project": "...",
  "document_name": "...",
  "document_type": "...",
  "source_type": "project_doc",
  "relative_path": "...",
  "stage": "...",
  "module": "...",
  "section": "...",
  "sections": ["..."],
  "requirement_id": "...",
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

## Выходные файлы

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
data/asu_june_bot/embeddings_cache_v2.jsonl
data/asu_june_bot/numpy_index_v2/
```

## Скрипты

```text
scripts/asu_june_bot_apply_config_v2_1.py
scripts/asu_june_bot_extract_text_v2.py
scripts/asu_june_bot_build_chunks_v2.py
scripts/asu_june_bot_audit_sources_v2.py
scripts/asu_june_bot_build_index_v2.py
scripts/asu_june_bot_health_v2.py
scripts/asu_june_bot_search_v2.py
run_asu_june_bot_rebuild_v2.ps1
run_asu_june_bot_chunks_v2.ps1
monitor_asu_june_bot_v2.ps1
register_asu_june_bot_v2_watchdog.ps1
monitor_asu_june_bot_index_v2.ps1
register_asu_june_bot_index_v2_watchdog.ps1
```

## Acceptance Criteria

`extraction/chunking v2.1` считается готовым, если:

```text
data/asu_june_bot/extracted_v2/blocks.jsonl создан
data/asu_june_bot/chunks_v2.jsonl создан
data/asu_june_bot/source_audit_v2_report.json создан
старые data/chunks.jsonl и data/numpy_index не изменены
технические выгрузки исключены из documents.jsonl
у каждого chunk есть chunker_version = v2
у каждого chunk есть chunk_level = parent | child
у child chunk из таблицы есть table_id и row_id
у требований по возможности заполнен requirement_id
у всех chunks есть source_type, document_type, relative_path, chunk_id, text_hash
unknown и system_export не доминируют в chunking_v2_report.json
dry-run выводит статистику и не пишет файлы
можно сравнить v1 и v2.1 на baseline-вопросах
```

## Baseline для сравнения v1/v2.1

Минимум:

```text
1. Точный пункт требования + ключевые слова интеграции.
2. Какие интеграции заявлены в проектных документах?
3. Что входит в Паспорт ИС?
4. Как работает интеграция с каталогом пользователей?
5. Какие справочники передаются через слой интеграции НСИ?
6. Какие сценарии испытаний покрывают конкретное требование?
```

## Не делать

```text
не заменять текущий RAG индекс без проверки
не считать embeddings v2 до очистки корпуса
не подключать LLM до готового search/context
не менять run_full_rag.ps1
не индексировать technical/system exports в основной project-only corpus
```
