# Текущий Контекст

Обновлено: 2026-07-08.

## Now

- active task: merge small MeetingAgent follow-up PRs (#151, #152, #153, #154) after #150 landed.
- branch: `codex/152-speaker-transcript-mapped-txt` while resolving PR #155 against current `origin/main`.
- canonical main state: `/MeetingAgent` shell and ASR engine selector are pushed; current work is public-safe follow-up cleanup.

## Done latest

- MA-WORKSPACE-QA-V2-UI (#113, PR #116): Workspace Q&A/Search показывает `retrieval_mode` (`semantic`/`lexical`) и `citation_label` вида `[00:12:34, Спикер]`; DOM/CSP-гигиена сохранена.
- MA-MEETING-STAGE-READINESS (#114, PR #117): `GET /meetings/{id}/pipeline/readiness` отдаёт карту стадий `done/ready/blocked`, `can_run`, machine-readable `reason`, required/produced artifacts без абсолютных путей.
- MA-MEETING-PIPELINE-RUN-ALL (#115, PR #118): `POST /meetings/{id}/jobs/pipeline` запускает последовательные профили `default`, `full`, `transcript_only`, `qa_ready`; готовые стадии skip без `force`; cancel останавливает текущую дочернюю стадию.
- MA-MEETING-ARTIFACT-CONTRACT (#119, PR #129): stable artifact manifest, shared catalog resolver, transcription report entry, default-path artifact serving.
- MA-MEETING-ERRORS-AND-RETRY (#120, PR #130): normalized public-safe `last_error`, stage retry, pipeline resume, `ready_for_retry` readiness. Issue #120 closed after merge.
- MA-WORKSPACE-FLOW (#121, PR #131): readiness/manifest-driven Workspace flow, run/resume/retry controls, pipeline-aware polling, Q&A gating, CSRF on every POST. Issue #121 closed after merge.
- MA-SPEAKER-MAPPING-UI (#122, PR #132): manual `SPEAKER_XX` -> name/role mapping in `meeting.json`, speaker discovery API, Workspace editor and mapped transcript display.
- MA-MEETING-STRUCTURED-ARTIFACTS-V2 (#123, PR #133): structured JSON artifacts now include source-grounded `confidence`, `needs_review`, chunk/timecode, speaker names and utterance refs; summary/protocol render source labels.
- MA-MEETING-QA-SEGMENT-CITATIONS (#126, PR #134): meeting Q&A/search source refs now resolve chunk/utterance citations to exact transcript segment targets when available (`segment_id`, `segment_refs[]`, precise `start_sec/end_sec`, mapped speaker fields); missing transcripts fall back to chunk-level citations.
- MA-MEETING-PACKAGING-LOCAL (#124, PR #135): local/Docker runbook, API container healthcheck and `scripts/42_local_preflight.py` for Docker, Ollama/model, ffmpeg and optional ASR dependency checks.
- MA-PRODUCT-SPLIT-PHASE-1 (#125, PR #136): shared config/limits/prompt-safety/hashing/JSONL/path-filter/LLM helpers extracted into `meeting_agent.shared`; meeting-owned Q&A/vector/scripts import shared modules directly; old bot package imports remain compatibility shims.
- MA-GUARD-PURE-DECISION-API (#106): pure `asu_june_bot.guard.evaluate_guard_decision()` adapter over existing `guardrails/` pipeline; no behavior change, no retrieval/LLM/network/disk I/O; fixture/runtime eval integration added.
- MA-ADR-AUTH-PROVIDERS (#39): ADR-0039 defines provider-agnostic browser auth adapters, Yandex ID as first planned external provider, local RBAC as authoritative, and `MEETINGAGENT_API_TOKEN` as separate machine/API fallback.
- MA-ADMIN-CONSOLE (#40): admin console contract defines Users/Roles, Access Settings, Jobs, Meetings Admin, Audit/Diagnostics and Runtime Settings surfaces; current admin API coverage and planned follow-up endpoints are documented.
- MA-TRANSCRIPT-ANONYMIZATION (#22): local transcript anonymization CLI for JSONL/Markdown, public-safe replacement report, optional private mapping, custom terms and meeting speaker-mapping terms.
- MA-MEETING-SUMMARY-BENCHMARK (#24): public synthetic meeting-summary benchmark cases and deterministic evaluator for summary/protocol + decisions/tasks/risks/open_questions source-grounding.
- PUBLIC-SAMPLE-MEETING-DATASET (#19): `examples/meeting_dataset/synthetic-support-handoff/` contains a schema-valid synthetic meeting card, transcript JSONL/Markdown and expected summary/protocol/structured artifacts with source refs.
- TRANSCRIPT-TO-PROTOCOL-QUICKSTART (#20): reproducible public guide from sample `segments.jsonl` through import, merge, chunk, enrich and extractive analyze; e2e test runs the documented flow.
- CODEX-SECURITY-REVIEW-CHECKLIST (#21): public checklist for AI-assisted security review; linked from `SECURITY.md`, `SECURITY.ru.md` and PR template.
- RELEASE-WORKFLOW-CHANGELOG (#23): documented release checklist, reusable changelog format, bilingual changelog validator and manual GitHub Actions release-validation workflow.
- DOCS-PARITY (#25): added bilingual documentation parity guide and tests that enforce paired `docs/en`/`docs/ru` files, language switches and public example parity.
- GITHUB-PAGES-DOCS (#26): added MkDocs Material config, docs landing page, local docs build dependencies and GitHub Pages deployment workflow.
- WINDOWS-UTF8-DOC-NOTE (#92): incorporated the useful external PR note into `docs/docker.md`; PowerShell smoke sessions should set UTF-8 output and `PYTHONIOENCODING=utf-8`.
- MA-MEETINGAGENT-HOME-UI: added `/MeetingAgent` as the primary product page with meeting registry, upload form, transcript/full pipeline launch actions, active job panel and separate navigation to `/ui` for the Project Knowledge Bot.
- MA-UI-ASR-ENGINE-SELECTOR (#150): `/MeetingAgent` upload/pipeline flow exposes ASR engine selection (`faster-whisper` default or `gigaam`) and sends it to the pipeline API as `asr_engine`.
- MA-SPEAKER-TRANSCRIPT-MAPPED-TXT (#152): `transcript/speaker_transcript.txt` renders saved speaker names/roles from `meeting.json.speaker_mapping`, while `speaker_transcript.jsonl` keeps stable technical `SPEAKER_XX` labels for downstream chunking/indexing.

## Current Product State

### Auth / security

- Machine Bearer token (`MEETINGAGENT_API_TOKEN`) остаётся основным способом для скриптов, CLI, Telegram adapter и service-to-service вызовов.
- Browser path работает через local login: `POST /admin/bootstrap` создаёт первого admin, `POST /auth/local/login` выдаёт HttpOnly session cookie и CSRF token.
- CSRF обязателен для cookie-authenticated write/action routes; Bearer callers exempt.
- RBAC: `viewer`, `editor`, `admin`; unknown roles grant nothing.
- Web UI chat auth интегрирован: login panel, auth badge, `GET /auth/csrf`, `X-CSRF-Token` на `POST /chat`; no localStorage/sessionStorage для credentials/CSRF.
- Validation errors sanitized; prompt/source delimiter escaping включён; trusted proxy и secret-strength hardening реализованы.

### Meeting processing / Workspace

- Meeting cards живут в ignored runtime `meetings/<meeting_id>/` и не публикуются в Git, если содержат реальные данные.
- Offline ASR product profile: `faster-whisper large-v3-turbo`, `language=ru`, `compute_type=int8`; `small` остаётся только явным draft/dev CLI выбором.
- Optional engines: GigaAM как внешний локальный backend; sherpa-onnx для diarization; Vosk для draft live transcription.
- Job runner поддерживает стадии `extract_audio`, `transcribe`, `diarize`, `merge`, `chunk`, `enrich`, `index`, `analyze`.
- Workspace UI: media player, clickable transcript, artifact viewer, job controls, readiness map, one-click pipeline profiles, meeting-scoped Search/Q&A.
- Workspace flow (#121): state panel (status + active job + public-safe last error), readiness-gated stage buttons (blocked → disabled with reason; done → explicit Force rerun; failed → Retry), pipeline actions (Run full / Resume when partially done / Retry failed stage), manifest-driven result chips (Transcript/Speaker transcript/Summary/Protocol/Tasks), Q&A disabled until chunks/index exist, panels auto-refresh after a job finishes; CSRF on every POST.
- Job failure recovery: `meeting.json.last_error` schema accepts normalized runner fields `code` and `job_id`, so CLI stages and retry flows can validate and recover cards after failed API jobs.
- Speaker mapping (#122): `meeting.json.speaker_mapping` stores real names/roles for diarized labels; `GET /meetings/{id}/speakers` discovers labels from diarization/transcript artifacts; `PUT /meetings/{id}/speakers/mapping` requires `meetings.edit` + CSRF; Workspace transcript shows mapped names while preserving `speaker_label`.
- Structured artifacts (#123): analyze stage keeps decisions/tasks/risks/open_questions source-grounded with `source_refs[]` that include `chunk_id`, timecodes, speakers, mapped speaker names and `utterance_ids`; each item carries `confidence` and `needs_review`; markdown summary/protocol surface the same source labels.
- Meeting Q&A v2: vector retrieval over meeting chunks через Ollama `bge-m3`, fusion с lexical, lazy cache `data/meeting_embeddings_cache.jsonl`, graceful lexical fallback.
- Meeting Q&A citations содержат timestamps, speaker labels, `utterance_ids`, `citation_label`, `citations_basis`; когда доступен transcript/speaker_transcript, citations дополнительно содержат exact `segment_id`, `segment_refs[]` и точный target для клика в Workspace; результаты строго scoped по `meeting_id`.

### Project Knowledge Bot

- `src/asu_june_bot/` остаётся production-ready reference runtime для Project Knowledge Bot: API, Web UI, Telegram adapter, retrieval, chat, guardrails, review queue, eval/export harness.
- Review queue, guard cases export/regression harness and pure guard decision API are implemented; guard v2 runtime behavior changes remain out of scope.
- Product split prep завершён документацией; code-level extraction перенесён в #125.

## API Surface Snapshot

```text
GET  /meetings
GET  /meetings/{id}
GET  /meetings/{id}/transcript
GET  /meetings/{id}/transcript/segments
GET  /meetings/{id}/speakers
PUT  /meetings/{id}/speakers/mapping
GET  /meetings/{id}/artifacts
GET  /meetings/{id}/artifacts/manifest
GET  /meetings/{id}/artifacts/{name}
GET  /meetings/{id}/media
GET  /meetings/{id}/media/{media_id}
GET  /meetings/{id}/workspace
POST /meetings/ingest
POST /meetings/{id}/search
POST /meetings/{id}/chat
GET  /meetings/{id}/jobs/stages
GET  /meetings/{id}/pipeline/readiness
POST /meetings/{id}/jobs/pipeline
POST /meetings/{id}/jobs/{stage}
POST /meetings/{id}/jobs/{stage}/retry
GET  /meetings/{id}/jobs/{job_id}
POST /meetings/{id}/jobs/{job_id}/cancel
GET  /jobs/active
POST /search
POST /chat
GET  /health
POST /auth/local/login
GET  /auth/me
GET  /auth/csrf
POST /auth/logout
POST /admin/bootstrap
GET  /admin/users
GET  /admin/users/{id}
POST /admin/users
PATCH /admin/users/{id}
POST /admin/users/{id}/disable
POST /admin/users/{id}/enable
GET  /admin/security/status
GET  /admin/review/chat-runs
POST /admin/review/chat-runs/{id}/label
GET  /admin/review/chat-runs/export
```

## Next

- Polish `/MeetingAgent` visual design and split monolithic HTML into maintainable frontend assets after mockups are approved.
- Add Meeting Q&A answer validation/fallback so short malformed model outputs do not surface as successful answers.
- Make meeting index updates atomic/locked to prevent JSONL corruption under overlapping index jobs.
- Improve `/MeetingAgent` visual consistency after mockups are approved.

## Open decisions / blockers

- Admin console contract is defined; dedicated admin UI, aggregate jobs/audit/settings endpoints and destructive meeting admin actions remain future implementation work.
- Guard pure decision API is available for deterministic tests; future guard behavior changes must use it as a measurement boundary.
- Local preflight can fail until Ollama is running and exposes `bge-m3` + `qwen3.5:4b` through the active model store.
- Transcript anonymization is heuristic and requires manual review before publishing anonymized examples or eval fixtures; see `docs/operations/TRANSCRIPT_ANONYMIZATION.md`.
- Meeting summary benchmark is deterministic and lexical by design; it is a smoke gate, not a semantic judge. Reports under `eval/reports/` stay runtime-only.
- Local/private runtime outputs under `meetings/`, `data/`, `logs/`, model caches, transcripts and indexes must remain out of Git.
- `/MeetingAgent` is now the intended product entrypoint; `/ui` remains the separate Project Knowledge Bot surface.
