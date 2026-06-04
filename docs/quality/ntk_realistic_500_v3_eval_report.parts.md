# NTK realistic 500 v3 eval report parts

`docs/quality/ntk_realistic_500_v3_eval_report.jsonl` was split because the single file exceeded GitHub's 100 MB file limit.

Parts:

```text
ntk_realistic_500_v3_eval_report.part1.jsonl
ntk_realistic_500_v3_eval_report.part2.jsonl
```

Recombine locally:

```powershell
Get-Content docs\quality\ntk_realistic_500_v3_eval_report.part1.jsonl, docs\quality\ntk_realistic_500_v3_eval_report.part2.jsonl | Set-Content docs\quality\ntk_realistic_500_v3_eval_report.jsonl -Encoding UTF8
```

The review and summary files remain unchanged:

```text
ntk_realistic_500_v3_eval_review.jsonl
ntk_realistic_500_v3_eval_review_summary.json
```
