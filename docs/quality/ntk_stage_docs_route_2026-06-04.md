# NTK stage documents route

Дата: 2026-06-04.

## Проблема

Live-проверка Telegram/API показала, что проектные вопросы вида:

```text
Какие документы необходимы для этапа 2.1
Какие документы относятся к этапу 2
Какие документы относятся к этапу 1
Какая документация относится к этапу 1
Какие документы необходимы на этапе 2 по ФТТ
Что такое ФТТ
```

частично уходили в `clarify` или `no_answer`, хотя нужные данные есть в NTK-корпусе.

Корневая причина разделена на два слоя:

```text
1. Guard: stage/document questions не имели достаточно сильного project-сигнала.
2. Retrieval/context: вопросы по документам этапов должны маршрутизироваться в ФТТ Table 18 "Состав работ и сроки реализации".
```

## Решение

Добавлено:

```text
src/asu_june_bot/search/ftt_stage_route.py
```

Route обрабатывает:

```text
1. ftt_stage_deliverables:
   - вопросы про документы / документацию этапа 1, 1.1, 1.2, 1.3, 2, 2.1, 2.2, 2.3;
   - primary source строится из ФТТ Table 18.

2. ftt_glossary:
   - вопросы "Что такое ФТТ", "ФТТ что это", "расшифруй ФТТ";
   - primary source строится из строк ФТТ с расшифровкой "Функционально-технические требования".
```

Route подключён в:

```text
src/asu_june_bot/search/__init__.py
```

Guard stage markers подключены в:

```text
src/asu_june_bot/guardrails/__init__.py
```

Точечный targeted dataset:

```text
docs/quality/ntk_stage_docs_targeted_queries.jsonl
```

## Acceptance

```text
STAGE-DOCS-001 -> answered, primary: ФТТ / Table 18 / stage 2.1
STAGE-DOCS-002 -> answered, primary: ФТТ / Table 18 / stage 2 + 2.1-2.3
STAGE-DOCS-003 -> answered, primary: ФТТ / Table 18 / stage 1 + 1.1-1.3
STAGE-DOCS-004 -> answered, primary: ФТТ / Table 18 / stage 1 + 1.1-1.3
STAGE-DOCS-005 -> answered, primary: ФТТ / Table 18 / stage 1.2
STAGE-DOCS-006 -> answered, primary: ФТТ / Table 18 / stage 2 + 2.1-2.3
STAGE-DOCS-007 -> answered, primary: ФТТ / glossary
```

## Local verification commands

```powershell
cd "C:\Users\Сотрудник\Desktop\AI\MeetingAgent"

git pull --ff-only origin main

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:ASU_JUNE_BOT_ACTIVE_CORPUS = "ntk"

.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot -q
.\.venv\Scripts\python.exe -m compileall -q src\asu_june_bot

.\.venv\Scripts\python.exe scripts\14_run_realistic_100_eval.py `
  --dataset docs\quality\ntk_stage_docs_targeted_queries.jsonl `
  --output data\ntk_stage_docs_targeted_eval_report.jsonl `
  --chat-script scripts\asu_june_bot_chat.py `
  --mode hybrid `
  --top-k 8 `
  --max-tokens 900
```

## Ограничения

Это targeted route, а не полноценный общий table parent expansion. Он закрывает конкретный дефект по ФТТ Table 18 и glossary ФТТ без пересборки корпуса.

Если в будущем будет реализован общий table/parent expansion, этот route можно заменить на более универсальный механизм.
