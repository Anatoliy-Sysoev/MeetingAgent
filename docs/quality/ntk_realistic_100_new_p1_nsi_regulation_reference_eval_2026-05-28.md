# NTK realistic-100 new P1 targeted eval: NSI regulation/reference

Дата: 2026-05-28.

Bucket:

```text
NSI regulation/reference
```

Кейсы:

```text
NTK100-NEW-053
NTK100-NEW-054
NTK100-NEW-055
NTK100-NEW-056
NTK100-NEW-057
NTK100-NEW-059
```

## До исправления

Симптом bucket был связан не с отсутствием корпуса НСИ, а с недостаточно точным routing между типами источников:

```text
- запросы про регламенты/методики ведения НСИ могли поднимать короткие registry/note chunks;
- запросы про справочники/атрибутные составы смешивались с регламентными документами;
- query expansion имел общий nsi_registers bucket и не разделял regulation/reference сценарии;
- для 053/054/055/056 ожидался Методика/Регламент НСИ как primary/supporting источник;
- для 057/059 ожидался Реестр НСИ / Справочник НСИ / атрибутный состав / модель данных НСИ.
```

## Что изменено

В `configs/asu_june_bot/query_expansion.yaml` добавлены отдельные группы:

```text
nsi_regulation
nsi_reference
```

Логика разделения:

```text
nsi_regulation:
  регламент ведения / регламентные документы НСИ / методики ведения НСИ / методика ведения данных справочника / методика нормализации / правила ведения объектов НСИ / объект НСИ / МВД
  -> Методика/Регламент НСИ, Методика ведения данных справочника, Методика нормализации данных справочника, Регламент ведения объекта НСИ, правила ведения объекта НСИ

nsi_reference:
  какие справочники НСИ / справочники НСИ перечислены / реестр объектов НСИ / атрибутные составы / модель данных НСИ / маппинг справочников / СВОК РД
  -> Реестр НСИ, Справочник НСИ, Атрибутный состав, Модель данных НСИ, маппинг атрибутов, единицы измерения, должности, отделы, контрагенты, организации, объекты строительства
```

Старый `nsi_registers` оставлен для обратной совместимости smoke-кейсов, но новые targeted cases должны матчиться более точными группами.

## Проверка, которую нужно выполнить локально

Search-level targeted dataset:

```powershell
$ids = @(
  "NTK100-NEW-053",
  "NTK100-NEW-054",
  "NTK100-NEW-055",
  "NTK100-NEW-056",
  "NTK100-NEW-057",
  "NTK100-NEW-059"
)

Get-Content ".\docs\quality\ntk_realistic_100_new_queries.jsonl" |
  ForEach-Object {
    $row = $_ | ConvertFrom-Json
    if ($ids -contains $row.id) {
      $row | ConvertTo-Json -Compress
    }
  } |
  Set-Content ".\data\ntk_targeted_nsi_6_queries.jsonl" -Encoding utf8
```

Chat-level targeted eval:

```powershell
$env:ASU_JUNE_BOT_ACTIVE_CORPUS = "ntk"

.\.venv\Scripts\python.exe scripts\14_run_realistic_100_eval.py `
  --dataset data\ntk_targeted_nsi_6_queries.jsonl `
  --output data\ntk_targeted_nsi_6_eval_report.jsonl `
  --chat-script scripts\asu_june_bot_chat.py `
  --mode hybrid `
  --top-k 5 `
  --max-tokens 700
```

Regression slice:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot\retrieval\test_bm25_ntk_routes.py -q
```

## Acceptance criteria

```text
053/054/055/056:
  top-1..top-5 содержит Методика/Регламент НСИ или конкретные документы методики/регламента;
  короткие registry/note chunks не должны быть единственным primary основанием;
  ответ не должен подменяться общим Реестром НСИ, если вопрос про регламент/методику ведения.

057/059:
  top-1..top-5 содержит Реестр НСИ / Справочник НСИ / атрибутный состав / модель данных НСИ;
  СоИ Справочники может быть supporting source, но не должен вытеснять точный reference источник при наличии атрибутного состава.
```

## Ограничение

Этот коммит фиксирует query-expansion/routing contract. Полный targeted eval нужно прогнать локально на актуальном `data/asu_june_bot_ntk/chunks_v2.jsonl` и `numpy_index_v2`, потому что runtime corpus не хранится в GitHub.

## Следующий шаг

После локального targeted eval:

```text
1. Если 6/6 пройдено — закрыть bucket в docs/context.md, docs/todo.md и NTK_YANDEX_CORPUS.md.
2. Если остаются weak primary fallback cases — усилить BM25/PostRerank для Методика/Регламент НСИ и атрибутных составов.
3. Затем переходить к P1 Passport.
```
