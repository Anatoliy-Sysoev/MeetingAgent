# NTK realistic 500 v3 query set

Дата: 2026-06-03.

Назначение: новый независимый 500-question eval set после targeted fixes по NTK100-V2.

## Files

```text
docs/quality/ntk_realistic_500_v3_queries_2026-06-03.jsonl
docs/quality/ntk_realistic_500_v3_queries_2026-06-03.overview.csv
docs/quality/ntk_realistic_500_v3_queries_2026-06-03.summary.md
```

## Counts

```text
total: 500
scope:
  harmful_security: 20
  out_of_scope: 30
  project: 450
category:
  admin_security: 35
  cta: 45
  executive_docs: 35
  ftt: 45
  harmful_security: 20
  mto: 35
  nsi_regulation_reference: 40
  operations_audit: 25
  out_of_scope_generic: 30
  passport: 25
  pr_sk: 50
  soi_ad: 35
  soi_nsi: 40
  testing: 40
```

## Notes

```text
project: 450
out_of_scope: 30
harmful_security: 20
id prefix: NTK500-V3-*
model: qwen2.5:7b-instruct
questions are generated from v3 topic banks and are not copied from NTK100-V2.
```
