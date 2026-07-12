# Scripts

This directory contains several generations of local automation scripts.

The canonical status of every `.py` and `.ps1` file is recorded in
`configs/runtime_inventory.yaml` and enforced by tests. Adding or removing a
script requires updating that inventory.

## Current Runtime

Use `scripts/asu_june_bot_*.py` for the current Project Knowledge Bot runtime:

- local API and UI;
- project-only search and chat;
- Telegram adapter;
- corpus health checks;
- guarded evaluation helpers.

Use the meeting scripts for the current meeting pipeline:

- `20_ingest_meeting.py`;
- `21_extract_audio.py`;
- `22_transcribe_meeting.py`;
- `23_diarize_meeting.py`;
- `24_merge_transcript_speakers.py`;
- `26_chunk_meeting.py`;
- `27_enrich_meeting_chunks.py`;
- `28_index_meeting_chunks.py`;
- `29_analyze_meeting.py`;
- `31_meeting_search.py`;
- `32_index_meeting_artifacts.py`;
- `33_live_transcribe_meeting.py` (optional draft live workflow).

## Legacy Baseline

Scripts `01_*` through `18_*`, `asu_june_bot_search.py`, and the `rag_*`
helpers belong to retained compatibility/evaluation contours. Their supported
replacements are listed in `scripts/legacy_entrypoint.py` and
`docs/en/runtime_ownership.md`.

Compatibility entrypoints print a visible deprecation and migration warning.
Existing unattended automation may temporarily set
`MEETINGAGENT_SUPPRESS_LEGACY_WARNING=1`, but new development must use the
current runtime paths.

The same inventory includes root PowerShell watchdog/build entrypoints. The old
v1 `monitor_rag.ps1`, `run_full_rag.ps1`, and `check_rag_status.ps1` are
compatibility-only; use their `asu_june_bot_*_v2` counterparts.

## Private / Runtime Data

Do not commit private corpora, generated chunks, embeddings cache, indexes, logs, transcripts, media files, or generated eval reports. Those belong under ignored runtime paths such as `data/`, `logs/`, `meetings/`, `vector_db/`, or `eval/reports/`.
