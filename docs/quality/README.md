# Quality Artifacts Policy

This directory is public-safe by default.

Tracked files here must be one of:

- synthetic evaluation examples;
- generic report templates;
- documentation explaining how to run private evaluations locally.

Do not commit:

- real customer/project questions;
- private eval datasets;
- generated eval reports;
- manual review files based on private corpora;
- retrieval probes over private documents;
- runtime JSONL/CSV/SQLite/parquet outputs.

Private evaluation outputs should stay under ignored runtime paths such as `data/`, `logs/`, `eval/reports/`, or local ignored documentation folders.

The tracked allowlist is enforced by `tests/unit/test_public_repository_privacy.py`.
Adding another file under `docs/quality/` requires an explicit public-safe review.
