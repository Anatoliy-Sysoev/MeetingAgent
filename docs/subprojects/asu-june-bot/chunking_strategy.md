# Chunking v2 Для Asu June Bot

Обновлено: 2026-05-12.

## Назначение

`chunking v2` — новая стратегия подготовки проектных chunks для Asu June Bot.

Цель: перейти от нарезки текста по символам к структурному extraction/chunking по смысловым единицам проектных документов, чтобы бот мог отвечать с точными ссылками на документы, разделы, пункты, строки таблиц и сценарии.

## Ключевое Решение

Asu June Bot строит собственный pipeline v2 и больше не зависит от старого extraction pipeline MeetingAgent.

Старый pipeline остается для MeetingAgent v1:

```text
run_full_rag.ps1
  -> scripts/01_inventory.py
  -> scripts/02_extract_text.py
  -> scripts/03_build_index.py
  -> scripts/05_build_numpy_index.py
```

Новый pipeline Asu June Bot v2:

```text
run_asu_june_bot_rebuild_v2.ps1
  -> scripts/asu_june_bot_extract_text_v2.py
  -> scripts/asu_june_bot_build_chunks_v2.py
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

## Почему Нужен v2

Текущий RAG MeetingAgent использует универсальную нарезку текста по размеру chunk. Это подходит для базового поиска, но недостаточно для AI-агента системного аналитика.

Проблемы v1:

1. Один chunk может содержать сразу несколько требований ФТТ.
2. Таблицы превращаются в общий текст и теряют структуру строк.
3. DOCX-таблицы в старом extractor переносились после всех paragraph, что ломало исходный порядок документа.
4. Номера пунктов определяются эвристически уже на этапе поиска.
5. Для точных вопросов вроде `ФТТ 4.2.5` бот получает широкий фрагмент, а не атомарное требование.
6. Для обзорных вопросов вроде `Что входит в Паспорт ИС?` не хватает parent-level chunks по разделам.
7. Нельзя уверенно формировать citations уровня `[ФТТ, п. 4.2.5]`, если metadata не была извлечена при extraction/chunking.

Вывод: v1 оставить как стабильный baseline, v2 строить параллельно и независимо.

## Extraction v2

Extractor v2 создает структурные blocks, а не plain text.

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

### Поддерживаемые форматы extraction v2

| Формат | Стратегия |
| --- | --- |
| `.docx` | чтение paragraph/table в исходном порядке Word-документа |
| `.xlsx` | лист + строка таблицы как block |
| `.xlsb` | лист + строка таблицы как block через `pyxlsb` engine |
| `.pdf` | page block по текстовому слою PDF |
| `.pptx` | slide и shape_text blocks |
| `.html` | heading/text blocks после удаления script/style/noscript |
| `.md/.txt/.json/.yml/.yaml/.drawio/.puml/.srt/.py/.js/.ts/.css` | text blocks |

### Block Schema v2

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

## Главный Принцип Chunking v2

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

## Parent / Child Модель

### Parent chunk

Parent chunk описывает крупный логический блок:

```text
документ -> раздел -> подраздел / таблица / сценарий
```

Пример:

```json
{
  "chunk_level": "parent",
  "document_type": "Паспорт ИС",
  "section": "5",
  "title": "Сведения о программном обеспечении информационной системы",
  "text": "..."
}
```

### Child chunk

Child chunk содержит атомарный факт:

```text
требование, строка таблицы, интеграционный поток, атрибут маппинга, шаг ПМИ, сервис, роль, порт
```

Пример:

```json
{
  "chunk_level": "child",
  "parent_chunk_id": "...",
  "document_type": "ФТТ",
  "requirement_id": "4.2.5",
  "section": "4.2.5",
  "text": "Функциональность формирования актов проверки... Интеграция с НОВАДОК с использованием ЭЦП."
}
```

## Retrieval После v2

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

## Metadata Schema v2

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
  "document_version": null,
  "source_type": "project_doc",
  "source_path": "...",
  "relative_path": "...",
  "source_url": null,

  "stage": "Этап 1",
  "module": "СМР / Строительный контроль",

  "section": "4.2.5",
  "sections": ["4.2.5"],
  "requirement_id": "4.2.5",
  "scenario_id": null,

  "block_id": "...",
  "block_type": "table_row",
  "table_id": "Table 3",
  "table_title": null,
  "row_id": "7",
  "row_header": "Код | Требование | Описание",

  "source_system": null,
  "target_system": null,
  "integration": null,
  "protocol": null,

  "text": "...",
  "text_hash": "...",
  "chars": 1000,
  "mtime": 0,
  "sha256": "..."
}
```

## Выходные Файлы

v2 не должен перезаписывать текущий индекс MeetingAgent.

Текущий pipeline:

```text
data/chunks.jsonl
data/embeddings_cache.jsonl
data/numpy_index/
```

v2 pipeline:

```text
data/asu_june_bot/extracted_v2/documents.jsonl
data/asu_june_bot/extracted_v2/blocks.jsonl
data/asu_june_bot/extracted_v2/extraction_v2_report.json
data/asu_june_bot/extracted_v2/extraction_v2_report.md
data/asu_june_bot/chunks_v2.jsonl
data/asu_june_bot/chunking_v2_report.json
data/asu_june_bot/chunking_v2_report.md
```

Индекс v2 будет добавлен отдельно:

```text
data/asu_june_bot/numpy_index_v2/
```

## Скрипты

Extraction v2:

```text
scripts/asu_june_bot_extract_text_v2.py
```

Chunking v2:

```text
scripts/asu_june_bot_build_chunks_v2.py
```

Full rebuild v2:

```text
run_asu_june_bot_rebuild_v2.ps1
```

Chunk-only wrapper:

```text
run_asu_june_bot_chunks_v2.ps1
```

## Команды

Extraction dry-run:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_extract_text_v2.py --dry-run --limit 5
```

Extraction только по ФТТ:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_extract_text_v2.py --path-contains "ФТТ"
```

Chunking dry-run после extraction:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py --dry-run --limit 5
```

Полная v2-пересборка:

```powershell
.\run_asu_june_bot_rebuild_v2.ps1
```

## Acceptance Criteria

`extraction/chunking v2` считается готовым для первого сравнения с v1, если:

- создан `data/asu_june_bot/extracted_v2/blocks.jsonl`;
- создан `data/asu_june_bot/chunks_v2.jsonl`;
- созданы отчеты extraction и chunking;
- старые `data/chunks.jsonl` и `data/numpy_index` не изменены;
- у каждого chunk есть `chunker_version = v2`;
- у каждого chunk есть `chunk_level = parent | child`;
- у child chunk из таблицы есть `table_id` и `row_id`;
- у ФТТ chunk по возможности заполнен `requirement_id`;
- у всех chunks есть `source_type`, `document_type`, `relative_path`, `chunk_id`, `text_hash`;
- dry-run выводит статистику и не пишет файлы;
- можно сравнить v1 и v2 на baseline-вопросах.

## Baseline Для Сравнения v1/v2

Минимум:

```text
1. ФТТ 4.2.5 НОВАДОК ЭЦП
2. Какие интеграции заявлены в проекте?
3. Что входит в Паспорт ИС?
4. Как работает интеграция с AD?
5. Какие справочники передаются через MDR?
6. Какие сценарии ПМИ покрывают ФТТ 4.1?
```

## Не Делать В Первой Версии

- Не заменять текущий RAG индекс.
- Не считать embeddings v2 в этом же скрипте.
- Не подключать LLM.
- Не менять `run_full_rag.ps1`.
- Не добавлять v2 в production search до сравнения с v1.
