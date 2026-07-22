# Meeting summary benchmark

This benchmark is a small public smoke dataset for comparing MeetingAgent meeting artifacts across local and hosted model providers.

The dataset is synthetic. It contains no private transcripts, customer names, paths, logs, or runtime meeting cards.

## Files

```text
eval/cases/meeting_summary_synthetic.jsonl
scripts/44_evaluate_meeting_summary.py
src/meeting_agent/evaluation/summary_benchmark.py
```

Each case contains:

- synthetic transcript segments;
- expected summary terms;
- expected decision/task/risk/open-question coverage;
- minimum structured item counts.

## What The Evaluator Checks

The evaluator reads candidate artifacts from either:

```text
candidate-dir/
  summary.md
  protocol.md
  decisions.json
  tasks.json
  risks.json
  open_questions.json
```

or case-scoped folders:

```text
candidate-dir/<case_id>/artifacts/
  summary.md
  protocol.md
  decisions.json
  tasks.json
  risks.json
  open_questions.json
```

It checks:

- summary/protocol contains required case terms;
- structured artifacts meet minimum item counts;
- expected decision/task/risk/question terms are present;
- every structured item has grounded `source_refs` with path, anchor and timestamp;
- every structured item has `confidence` and `needs_review`.

## Run

```powershell
python scripts/44_evaluate_meeting_summary.py `
  --cases eval/cases/meeting_summary_synthetic.jsonl `
  --candidate-dir path\to\candidate_outputs `
  --provider ollama `
  --model qwen3.5:4b `
  --out-dir eval\reports\meeting_summary `
  --fail-under 1.0
```

The command writes:

```text
meeting_summary_benchmark_report.json
meeting_summary_benchmark_report.md
```

`eval/reports/` is runtime output and is not committed.

## Comparing Providers

Run the same cases for each provider/model and store each report in a separate output folder:

```powershell
python scripts/44_evaluate_meeting_summary.py --candidate-dir outputs\ollama --provider ollama --model qwen3.5:4b --out-dir eval\reports\meeting_summary\ollama
python scripts/44_evaluate_meeting_summary.py --candidate-dir outputs\groq --provider groq --model llama --out-dir eval\reports\meeting_summary\groq
python scripts/44_evaluate_meeting_summary.py --candidate-dir outputs\gigachat --provider gigachat --model giga --out-dir eval\reports\meeting_summary\gigachat
```

The report format is provider-neutral: `provider`, `model`, case scores, check-level details.

## Limitations

- This is a smoke benchmark, not a full semantic judge.
- It uses lexical required-term checks to remain deterministic in CI.
- Passing the benchmark does not prove production summary quality.
- Failing a term check can be legitimate if the model uses a synonym; add a curated case update only after manual review.
- Private meeting outputs must not be copied into `eval/cases/` or committed.
