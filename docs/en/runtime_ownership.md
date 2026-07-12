# Runtime Ownership And Entrypoints

[English](runtime_ownership.md) | [Русский](../ru/runtime_ownership.md)

## Canonical Inventory

`configs/runtime_inventory.yaml` is the machine-checked source of truth for
every Python package and every `.py`/`.ps1` file under `scripts/`. Each path is
classified as `current`, `compatibility`, or `planned`. Removed empty scaffolds
are recorded separately. CI fails when a new path is not classified or a path
appears in more than one category.

## Product Ownership

| Area | Owner | Status |
|---|---|---|
| `meeting_agent.transcription` | MeetingAgent Core | Current canonical offline ASR contract |
| `meeting_agent.diarization` | MeetingAgent Core | Current optional speaker diarization |
| `meeting_agent.live_transcription` | MeetingAgent Core | Current optional draft live helpers |
| `meeting_agent.evaluation` | MeetingAgent Core | Current meeting artifact evaluation |
| `meeting_agent.shared` | Shared | Current config, limits, path safety, JSONL, hashing, prompt safety, LLM clients |
| `asu_june_bot.api/auth/jobs/meetings` | Integrated runtime | Current MeetingAgent API/UI and local security |
| `asu_june_bot.chat/retrieval/search/guardrails` | Project Knowledge Bot | Current project-memory assistant |
| `asu_june_bot.core`, `asu_june_bot.llm` | Compatibility | Import shims over `meeting_agent.shared` |

The integrated HTTP application remains in `asu_june_bot.api` until the
documented product-split phases move MeetingAgent-owned routes. This placement
does not make meeting processing bot-owned.

## Supported Public Entrypoints

- API/UI: `scripts/asu_june_bot_api.py`;
- project chat/search: `scripts/asu_june_bot_chat.py` and
  `scripts/asu_june_bot_search_v2.py`;
- Telegram adapter: `scripts/asu_june_bot_telegram.py`;
- meeting pipeline: `scripts/20_ingest_meeting.py`, then `21`, `22`, `23`,
  `24`, `26`, `27`, `28`, and `29` as required;
- meeting search/index extensions: `31_meeting_search.py` and
  `32_index_meeting_artifacts.py`;
- optional draft live transcription: `33_live_transcribe_meeting.py`;
- verification: `42_local_preflight.py`, `46_ci_verify.py`,
  `47_dependency_audit.py`, and `48_retrieval_coverage.py`.

The inventory defines the exact CLI `--help` smoke list. Those commands are
started in subprocesses during tests without network or model calls.

## Compatibility And Migration

The v1 RAG/evaluation scripts `01_*` through `18_*` remain executable for local
migration and historical reproducibility. They are not supported for new
product development. Running a compatibility entrypoint prints a visible
replacement plus this guide. The warning can be suppressed temporarily with
`MEETINGAGENT_SUPPRESS_LEGACY_WARNING=1` for existing unattended automation.

Important migrations:

| Compatibility path | Current replacement |
|---|---|
| `01_inventory.py`, `02_extract_text.py` | `asu_june_bot_extract_text_v2.py` plus `asu_june_bot_build_chunks_v2.py` |
| `03_build_index.py`, `04_build_fts_index.py`, `05_build_numpy_index.py` | `asu_june_bot_build_index_v2.py` |
| `04_query.py`, `asu_june_bot_search.py` | `asu_june_bot_search_v2.py` |
| `06_transcribe_meeting.py` | `22_transcribe_meeting.py` |
| `07_generate_meeting_artifacts.py` | `29_analyze_meeting.py` |
| `08_process_meeting_pipeline.py` | `POST /meetings/{id}/jobs/pipeline` |
| `09_chat.py` | `asu_june_bot_chat.py` |
| legacy review/eval scripts | Review API, guard-case exporter, and current eval CLIs |

Compatibility paths use the same product defaults where they remain relevant.
Offline faster-whisper defaults to `large-v3-turbo`; `small` is available only
as an explicit draft/dev CLI choice.

## Removed Scaffolds

Empty `apps/*`, `templates/*`, unused `meeting_agent` placeholder packages, and
empty `tests/integration` / `tests/evaluation` placeholders were removed. They
had no runtime contract or near-term committed implementation. Reintroduce a
directory only together with working code, tests, ownership, and documentation.
The broken `set_asu_june_bot_project_root.ps1` wrapper was also removed because
its target script did not exist; use ignored local YAML overlays directly.
