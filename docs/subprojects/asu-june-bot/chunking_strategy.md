# Chunking v2 Для Asu June Bot

Обновлено: 2026-05-12.

## Назначение

`chunking v2` — новая стратегия подготовки проектных chunks для Asu June Bot.

Цель: перейти от нарезки текста по символам к структурному chunking по смысловым единицам проектных документов, чтобы бот мог отвечать с точными ссылками на документы, разделы, пункты, строки таблиц и сценарии.

## Почему Нужен v2

Текущий RAG MeetingAgent использует универсальную нарезку текста по размеру chunk. Это подходит для базового поиска, но недостаточно для AI-агента системного аналитика.

Проблемы v1:

1. Один chunk может содержать сразу несколько требований ФТТ.
2. Таблицы превращаются в общий текст и теряют структуру строк.
3. Номера пунктов определяются эвристически уже на этапе поиска.
4. Для точных вопросов вроде `ФТТ 4.2.5` бот получает широкий фрагмент, а не атомарное требование.
5. Для обзорных вопросов вроде `Что входит в Паспорт ИС?` не хватает parent-level chunks по разделам.
6. Нельзя уверенно формировать citations уровня `[ФТТ, п. 4.2.5]`, если metadata не была извлечена при chunking.

Вывод: v1 оставить как стабильный baseline, v2 строить параллельно.

## Главный Принцип v2

```text
Не chunk по символам, а chunk по смысловой единице документа.
```

Смысловая единица зависит от типа документа:

| Тип документа | Atomic child chunk | Parent chunk |
| --- | --- | --- |
| ФТТ | одно требование / пункт | раздел требований |
| ЦТА | строка таблицы / архитектурный пункт / поток | раздел архитектуры |
| СоИ AD | один блок / одна строка маппинга | раздел интеграции |
| СоИ Справочники | одно поле маппинга / один справочник | справочник целиком |
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

## Правила По Типам Документов

### ФТТ

Правило:

```text
одно требование = один child chunk
раздел требований = parent chunk
```

Metadata:

```text
document_type = ФТТ
requirement_id = номер требования, например 4.2.5
section = requirement_id
module = модуль, если определяется по тексту/пути
```

Критерий качества:

- запрос `ФТТ 4.2.5` должен возвращать chunk, где `requirement_id = 4.2.5`;
- chunk не должен включать весь раздел 4.2 целиком, если можно выделить отдельное требование.

### ЦТА

Правило:

```text
раздел архитектуры = parent chunk
строка таблицы / поток / сервис / порт = child chunk
```

Metadata:

```text
document_type = ЦТА
section = номер раздела
module = архитектурная область
integration/protocol/source_system/target_system — если определяется
```

### СоИ AD

Правило:

```text
логический раздел интеграции = parent chunk
строка атрибутного состава / маппинга = child chunk
```

Metadata:

```text
document_type = СоИ AD
integration = Active Directory
protocol = LDAPS, если найден
source_system = AD
target_system = ЦП УПКС
```

### СоИ Справочники

Правило:

```text
справочник = parent chunk
поле / строка маппинга = child chunk
```

Metadata:

```text
document_type = СоИ Справочники
dictionary = наименование справочника
source_system = MDR / КШД / СОИ
target_system = ЦП УПКС
```

### Паспорт ИС

Правило:

```text
раздел паспорта = parent chunk
пункт / сервис / компонент / строка таблицы = child chunk
```

Критерий качества:

- вопрос `Что входит в Паспорт ИС?` должен поднимать parent chunks по структуре документа;
- вопрос про PostgreSQL/Minio/AD должен поднимать конкретные child chunks.

### ПМИ

Правило:

```text
сценарий СФТ/СНТ = parent chunk
шаг сценария / проверяемое требование = child chunk
```

Metadata:

```text
document_type = ПМИ
test_type = СФТ / СНТ
scenario_id = СФТ 1 / СНТ 5
requirement_id = ФТТ пункт, если найден
```

## Таблицы

Таблицы — главный источник атомарных chunks.

Правило:

```text
одна строка таблицы = один child chunk
```

При этом в текст child chunk обязательно включать:

```text
- document_name
- table_id
- header row
- row values
```

Пример текста child chunk:

```text
Документ: ФТТ.docx
Таблица: Table 5
Заголовки: Код | Наименование | Описание
Строка: 4.2.5 | Формирование акта проверки | ... НОВАДОК ... ЭЦП ...
```

Такой формат нужен, чтобы chunk был понятен без просмотра всей таблицы.

## Размеры

### Child chunk

Целевой размер:

```text
300–1200 токенов / примерно 500–2500 символов
```

Но смысл важнее длины.

### Parent chunk

Целевой размер:

```text
1200–3000 токенов / примерно 2500–7000 символов
```

### Overlap

Overlap используется только для обычного текста.

```text
100–200 токенов / 300–600 символов
```

Для таблиц overlap не нужен.

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
data/asu_june_bot/chunks_v2.jsonl
data/asu_june_bot/chunking_v2_report.json
data/asu_june_bot/chunking_v2_report.md
```

Индекс v2 будет добавлен отдельно:

```text
data/asu_june_bot/numpy_index_v2/
```

## Скрипты

Новый скрипт:

```text
scripts/asu_june_bot_build_chunks_v2.py
```

Скрипт должен:

1. Читать `data/extracted_text/_metadata.jsonl`.
2. Читать извлеченный текст из `extracted_path`.
3. Строить parent/child chunks.
4. Сохранять результат в `data/asu_june_bot/chunks_v2.jsonl`.
5. Сохранять отчет.
6. Не трогать `data/chunks.jsonl`.
7. Не трогать `data/embeddings_cache.jsonl`.
8. Не трогать `data/numpy_index`.

## Команды

Dry-run:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py --dry-run --limit 5
```

Полная сборка chunks v2:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py
```

Сборка только по ФТТ:

```powershell
.\.venv\Scripts\python.exe scripts\asu_june_bot_build_chunks_v2.py --path-contains "ФТТ"
```

## Acceptance Criteria

`chunking v2` считается готовым для первого сравнения с v1, если:

- создан `data/asu_june_bot/chunks_v2.jsonl`;
- создан отчет `chunking_v2_report.json`;
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
- Не делать DOCX/PDF re-extraction заново.
- Не менять `run_full_rag.ps1`.
- Не добавлять v2 в production search до сравнения с v1.
