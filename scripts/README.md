# Scripts

This directory contains several generations of local automation scripts.

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
- `26_chunk_meeting.py`;
- `29_analyze_meeting.py`;
- `31_meeting_search.py`.

## Legacy Baseline

Scripts such as `01_inventory.py`, `02_extract_text.py`, `03_build_index.py`, `04_query.py`, and `09_chat.py` belong to the legacy MeetingAgent v1 RAG baseline.

They are kept for compatibility and migration reference. New development should target `src/asu_june_bot/`, `src/meeting_agent/transcription/`, and the documented public workflows.

## Private / Runtime Data

Do not commit private corpora, generated chunks, embeddings cache, indexes, logs, transcripts, media files, or generated eval reports. Those belong under ignored runtime paths such as `data/`, `logs/`, `meetings/`, `vector_db/`, or `eval/reports/`.
