# NTK v2 targeted eval: false clarify / bad_refusal

Дата: 2026-06-03.

Статус:

```text
closed
```

Bucket:

```text
False clarify по проектным вопросам + out_of_scope false clarify
```

## Scope

Targeted dataset:

```text
data/ntk_v2_targeted_false_clarify_20_queries.jsonl
```

Eval report:

```text
data/ntk_v2_targeted_false_clarify_20_eval_report.jsonl
```

Кейсы:

```text
Project false clarify:
NTK100-V2-009
NTK100-V2-011
NTK100-V2-015
NTK100-V2-021
NTK100-V2-023
NTK100-V2-027
NTK100-V2-048
NTK100-V2-053
NTK100-V2-054
NTK100-V2-061
NTK100-V2-065
NTK100-V2-067
NTK100-V2-073
NTK100-V2-080
NTK100-V2-083
NTK100-V2-086
NTK100-V2-090

Out-of-scope false clarify:
NTK100-V2-093
NTK100-V2-095
NTK100-V2-096
```

## Code changes

Guard/scope fixes were implemented in:

```text
src/asu_june_bot/guardrails/scope_classifier.py
```

Main changes:

```text
- project markers expanded for inflected forms and v2 project language;
- generic out-of-scope markers expanded for neutral non-project queries;
- temporary hardcoded ProjectGuard override was removed;
- guard remains based on segmenter -> scope_classifier -> aggregator -> policy.
```

Relevant commits:

```text
57fa876 Fix NTK v2 false clarify guard markers
7d792ea Add NTK v2 false clarify guard regressions
73f7232 Fix NTK v2 false clarify guard inflections
bc90cae Remove temporary NTK guard overrides
9ecbf31 Fix remaining NTK v2 guard inflection markers
```

## Regression tests

Local verification:

```text
tests/asu_june_bot/test_project_guard_v2.py -> 12 passed
tests/asu_june_bot -> 172 passed
python -m compileall -q src\asu_june_bot -> ok
```

## Targeted eval result

Command:

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:ASU_JUNE_BOT_ACTIVE_CORPUS = "ntk"

.\.venv\Scripts\python.exe scripts\14_run_realistic_100_eval.py `
  --dataset data\ntk_v2_targeted_false_clarify_20_queries.jsonl `
  --output data\ntk_v2_targeted_false_clarify_20_eval_report.jsonl `
  --chat-script scripts\asu_june_bot_chat.py `
  --mode hybrid `
  --top-k 5 `
  --max-tokens 700
```

Summary:

```text
total: 20
failures: 0
parse_errors: 0
scopes:
  project: 17
  out_of_scope: 3
statuses:
  answered: 11
  no_answer: 6
  refused: 3
avg_duration_sec: 67.947
max_duration_sec: 110.161
min_duration_sec: 0.95
```

## Acceptance check

### Project false clarify

All 17 project cases passed the guard/scope acceptance:

```text
status != clarify
status != refused
search_status = ok
guard_decision = allow
guard_reason = all_relevant_segments_in_project_scope
retrieval_called = true
```

Per case:

```text
NTK100-V2-009  -> answered, retrieval_called=true
NTK100-V2-011  -> answered, retrieval_called=true
NTK100-V2-015  -> no_answer, retrieval_called=true
NTK100-V2-021  -> no_answer, retrieval_called=true
NTK100-V2-023  -> no_answer, retrieval_called=true
NTK100-V2-027  -> answered, retrieval_called=true
NTK100-V2-048  -> answered, retrieval_called=true
NTK100-V2-053  -> answered, retrieval_called=true
NTK100-V2-054  -> no_answer, retrieval_called=true
NTK100-V2-061  -> answered, retrieval_called=true
NTK100-V2-065  -> no_answer, retrieval_called=true
NTK100-V2-067  -> answered, retrieval_called=true
NTK100-V2-073  -> answered, retrieval_called=true
NTK100-V2-080  -> answered, retrieval_called=true
NTK100-V2-083  -> no_answer, retrieval_called=true
NTK100-V2-086  -> answered, retrieval_called=true
NTK100-V2-090  -> answered, retrieval_called=true
```

Important: `no_answer` for 6 project cases is not a guard failure anymore. These cases now reach retrieval and belong to the next retrieval/answer-quality buckets.

### Out-of-scope false clarify

All 3 out-of-scope cases passed:

```text
status = refused
search_status = refused
guard_decision = refuse
guard_reason = out_of_project_query
retrieval_called = false
```

Per case:

```text
NTK100-V2-093 -> refused, retrieval_called=false
NTK100-V2-095 -> refused, retrieval_called=false
NTK100-V2-096 -> refused, retrieval_called=false
```

## Result

```text
False clarify / bad_refusal bucket is closed.
```

Remaining quality work is outside the guard layer:

```text
1. false no_answer / low_score for project questions;
2. garbage_source / wrong retrieval;
3. missing_source / corpus gaps.
```
