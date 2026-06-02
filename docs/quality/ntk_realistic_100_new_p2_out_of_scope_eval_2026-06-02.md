# NTK realistic-100 new P2 targeted eval: out_of_scope

Дата: 2026-06-02.

Статус:

```text
in_progress
```

Bucket:

```text
P2 out_of_scope
```

Кейсы:

```text
NTK100-NEW-093
NTK100-NEW-094
NTK100-NEW-095
NTK100-NEW-096
```

## Целевое поведение

```text
Все 4 кейса должны получить refused/out_of_scope на уровне guard до retrieval.

Ожидаемо:
  status = refused
  guard.decision = refuse
  guard.reason = out_of_project_query
  retrieval_called = false
  search_status = refused
  clarify = 0
```

## Исходная проблема

В realistic-100 manual review эти вопросы относились к out_of_scope, но могли уходить в clarify, потому что rule-based scope classifier не имел явных бытовых маркеров для растений, медицины, shopping/Taobao и general software/Chrome.

Кейсы:

```text
NTK100-NEW-093: Как подрезать фикус, чтобы он распушился?
NTK100-NEW-094: Что делать, если застудил шею?
NTK100-NEW-095: Найди ракетку для бадминтона на Taobao.
NTK100-NEW-096: Почему Chrome тормозит и какой браузер лучше?
```

## Что изменено

Файл:

```text
src/asu_june_bot/guardrails/scope_classifier.py
```

В `OUT_OF_PROJECT_MARKERS` добавлены бытовые маркеры:

```text
медицина
симптом
шея
шею
застудил
застудил шею
фикус
растение
растения
подрезать
распушился
taobao
таобао
бадминтон
ракетка
ракетку
chrome
хром
какой браузер лучше
браузер лучше
тормозит
```

Файл:

```text
tests/asu_june_bot/test_project_guard_v2.py
```

Добавлен regression test:

```text
test_ntk_p2_out_of_scope_queries_refused_not_clarified
```

Проверяет, что все 4 P2 query получают:

```text
GuardAction.REFUSE
reason = out_of_project_query
scope = OUT_OF_PROJECT
```

## Коммиты

```text
fb4a65b Fix NTK P2 out-of-scope guard markers
75a3ae9 Add P2 out-of-scope guard regression cases
```

## Локальная проверка

Сначала подтянуть `main`:

```powershell
git checkout main
git pull --ff-only origin main
git log --oneline -7
```

Targeted dataset:

```powershell
@'
import json
from pathlib import Path

ids = {
    "NTK100-NEW-093",
    "NTK100-NEW-094",
    "NTK100-NEW-095",
    "NTK100-NEW-096",
}

src = Path("docs/quality/ntk_realistic_100_new_queries.jsonl")
out = Path("data/ntk_targeted_p2_out_of_scope_4_queries.jsonl")

count = 0
with src.open("r", encoding="utf-8-sig") as f, out.open("w", encoding="utf-8", newline="\n") as w:
    for line in f:
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("id") in ids:
            w.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            count += 1

print(f"written={count}")
'@ | .\.venv\Scripts\python.exe -
```

Run:

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:ASU_JUNE_BOT_ACTIVE_CORPUS = "ntk"

.\.venv\Scripts\python.exe scripts\14_run_realistic_100_eval.py `
  --dataset data\ntk_targeted_p2_out_of_scope_4_queries.jsonl `
  --output data\ntk_targeted_p2_out_of_scope_4_eval_report.jsonl `
  --chat-script scripts\asu_june_bot_chat.py `
  --mode hybrid `
  --top-k 5 `
  --max-tokens 700
```

Summary:

```powershell
Get-Content ".\data\ntk_targeted_p2_out_of_scope_4_eval_report.jsonl" -Encoding utf8 |
  ForEach-Object {
    $row = $_ | ConvertFrom-Json
    $parsed = $row.parsed
    [PSCustomObject]@{
      id = $row.id
      status = $parsed.status
      answer = (($parsed.answer -replace "\s+", " ").Substring(0, [Math]::Min(180, ($parsed.answer -replace "\s+", " ").Length)))
      search_status = $parsed.search.status
      guard_decision = $parsed.search.guard.decision
      guard_reason = $parsed.search.guard.reason
      retrieval_called = $parsed.search.diagnostics.search_service.retrieval_called
    }
  } |
  Format-List
```

Regression:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\asu_june_bot -q
.\.venv\Scripts\python.exe -m compileall -q src\asu_june_bot
```

## Acceptance criteria

```text
NTK100-NEW-093 -> refused
NTK100-NEW-094 -> refused
NTK100-NEW-095 -> refused
NTK100-NEW-096 -> refused
clarify = 0
answered = 0
parse_errors = 0
failures = 0
retrieval_called = false for all 4
```

## Runtime data

Runtime reports не коммитятся:

```text
data/ntk_targeted_p2_out_of_scope_4_queries.jsonl
data/ntk_targeted_p2_out_of_scope_4_eval_report.jsonl
```
