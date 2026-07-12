from __future__ import annotations

import os
import sys
from pathlib import Path


MIGRATION_GUIDE = "docs/en/runtime_ownership.md"

LEGACY_ENTRYPOINTS: dict[str, str] = {
    "01_inventory.py": "scripts/asu_june_bot_extract_text_v2.py",
    "02_extract_text.py": "scripts/asu_june_bot_extract_text_v2.py",
    "03_build_index.py": "scripts/asu_june_bot_build_index_v2.py",
    "04_build_fts_index.py": "scripts/asu_june_bot_build_index_v2.py",
    "04_query.py": "scripts/asu_june_bot_search_v2.py",
    "05_build_numpy_index.py": "scripts/asu_june_bot_build_index_v2.py",
    "06_transcribe_meeting.py": "scripts/22_transcribe_meeting.py",
    "07_generate_meeting_artifacts.py": "scripts/29_analyze_meeting.py",
    "08_process_meeting_pipeline.py": "POST /meetings/{id}/jobs/pipeline",
    "09_chat.py": "scripts/asu_june_bot_chat.py",
    "09_chat_quality.py": "scripts/asu_june_bot_chat_eval.py",
    "10_review_queries.py": "GET /admin/review/chat-runs",
    "11_run_synthetic_seed.py": "scripts/asu_june_bot_chat_eval.py",
    "12_analyze_seed_report.py": "scripts/asu_june_bot_chat_eval.py",
    "13_build_eval_candidates.py": "scripts/40_export_guard_v2_cases.py",
    "14_run_realistic_100_eval.py": "scripts/asu_june_bot_chat_eval.py",
    "15_prepare_realistic_eval_review.py": "GET /admin/review/chat-runs",
    "16_build_approved_regression.py": "scripts/40_export_guard_v2_cases.py",
    "18_targeted_bucket_eval.py": "scripts/asu_june_bot_chat_eval.py",
    "asu_june_bot_search.py": "scripts/asu_june_bot_search_v2.py",
}


def warn_legacy_entrypoint(source_file: str) -> None:
    """Print a visible migration warning without blocking retained workflows."""
    if os.getenv("MEETINGAGENT_SUPPRESS_LEGACY_WARNING", "").strip() == "1":
        return
    name = Path(source_file).name
    replacement = LEGACY_ENTRYPOINTS.get(name)
    if replacement is None:
        raise ValueError(f"unregistered compatibility entrypoint: {name}")
    print(
        f"DEPRECATED: scripts/{name} is retained for compatibility only. "
        f"Use {replacement}. Migration guide: {MIGRATION_GUIDE}",
        file=sys.stderr,
    )
