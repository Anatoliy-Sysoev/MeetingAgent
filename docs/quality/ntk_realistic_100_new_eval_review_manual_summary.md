# NTK realistic 100 new — manual review summary

Created: 2026-05-28T07:14:05.992158+00:00

## Verdict counts
- ok: 34
- missing_source: 27
- low_score: 23
- bad_refusal: 8
- needs_clarification: 4
- garbage_source: 2
- out_of_scope: 2

## Runtime statuses
- no_answer: 46
- answered: 35
- clarify: 12
- refused: 6
- validation_failed: 1

## Main findings
- Основная проблема: retrieval/source grounding, а не стабильность runner — все 100 строк отработали с returncode=0 по исходному summary.
- Крупнейший класс дефектов: missing_source и low_score по проектным вопросам.
- Project-scope guard всё ещё даёт clarify на части проектных запросов: export, integration, MTO/MTR, исполнительная документация, аудит/logging/debug.
- AD/app_ccpm: явный mapping уже находится, но ответы по app_ccpm_ul_cc неполные и требуют усиления primary mapping chunk.
- NSI regulation/reference: остаётся слабый routing к Методика/Регламент НСИ, атрибутным составам, маппингам и конкретным справочникам.
- Out-of-scope guard: карбонара/калории отказаны корректно, но растения/медицина/shopping/Chrome уходят в clarify вместо refused/out_of_scope.
- Harmful-security guard: SQLi/JWT exploit/LDAPS exploit/system prompt отказаны корректно; отдельный проектный запрос про пароли/секреты ушёл в clarify и должен hard-refuse.

## Priority buckets
- project_scope_clarify_or_sensitive_guard: 8 — NTK100-NEW-071, NTK100-NEW-073, NTK100-NEW-077, NTK100-NEW-079, NTK100-NEW-080, NTK100-NEW-085, NTK100-NEW-086, NTK100-NEW-090
- missing_source_cta: 4 — NTK100-NEW-025, NTK100-NEW-026, NTK100-NEW-027, NTK100-NEW-028
- missing_source_pr: 4 — NTK100-NEW-014, NTK100-NEW-016, NTK100-NEW-019, NTK100-NEW-020
- missing_source_passport: 3 — NTK100-NEW-063, NTK100-NEW-064, NTK100-NEW-065
- missing_source_nsi_regulation: 3 — NTK100-NEW-054, NTK100-NEW-055, NTK100-NEW-056
- missing_source_nsi_reference: 2 — NTK100-NEW-057, NTK100-NEW-059
- missing_source_soi_nsi: 3 — NTK100-NEW-047, NTK100-NEW-050, NTK100-NEW-051
- low_score_soi_ad: 3 — NTK100-NEW-034, NTK100-NEW-039, NTK100-NEW-040
- low_score_cta: 4 — NTK100-NEW-024, NTK100-NEW-030, NTK100-NEW-031, NTK100-NEW-032
- low_score_soi_nsi: 3 — NTK100-NEW-046, NTK100-NEW-048, NTK100-NEW-049
- out_of_scope_clarify_instead_of_refused: 4 — NTK100-NEW-093, NTK100-NEW-094, NTK100-NEW-095, NTK100-NEW-096

## Files
- filled review JSONL: `ntk_realistic_100_new_eval_review_filled.jsonl`
- overview CSV: `ntk_realistic_100_new_eval_review_filled_overview.csv`
- machine summary JSON: `ntk_realistic_100_new_eval_review_manual_summary.json`