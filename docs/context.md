# Текущий Контекст

Обновлено: 2026-07-12.

## Now

- MA-DEPENDENCY-LOCK-AND-AUDIT (#177) is implemented and locally verified on
  `codex/177-dependency-lock-audit`; PR #192 is awaiting its rebased CI run.
- canonical main state: `6646224` / `Make CSRF response safety test deterministic (#194)`.
- next audit focus after #177: characterize and decompose retrieval ranking (#178).

## Done latest

- MA-DEPENDENCY-LOCK-AND-AUDIT (#177): Python 3.12 now has a reviewed exact
  constraints graph; core, offline ASR, optional diarization and dev/audit
  groups are separated;
  Docker/CI/release use the lock; scheduled `pip-audit` and Dependabot are
  enabled; exceptions require an issue, reason and expiry and currently none
  are active.
- TEST-CSRF-TOKEN-FLAKE (#193): CSRF response safety is asserted from parsed
  response fields; random token entropy can no longer fail CI by containing the
  English substring `hash`.
- MA-JOB-DURABILITY-RECOVERY (#176): stage and pipeline state now uses an
  atomic, locked and size-bounded local snapshot; API restart recovers live
  children as cancellable `orphaned` jobs, marks missing children failed and
  ready for retry, blocks duplicate work across runner instances and safely
  terminates verified process trees on Windows/Linux.
- PKB-SEARCH-SOURCE-PROMOTION-DEDUP (#175): AD role-mapping source promotion
  now keeps every source key in exactly one primary/supporting bucket, preserves
  stable first-wins order and reports only sources actually promoted from
  supporting to primary.
- MA-INGEST-LIMITS-ATOMIC-DEDUP (#174): API uploads are bounded by validated
  `meetings.max_upload_bytes`, partial temp files are removed on every exit,
  metadata/errors are bounded and path-free, and SHA dedup + card creation are
  serialized across threads/processes by a service-level transaction lock.
- MA-MEETING-API-METADATA-REDACTION (#173): meeting list/detail, artifact and
  media metadata use explicit path-safe DTOs and stable IDs/API URLs; malformed
  cards return bounded machine codes; raw card/storage diagnostics require an
  admin browser session at `GET /admin/diagnostics/meetings/{meeting_id}`.
- MA-CI-FULL-TEST-MATRIX (#172): PR/push CI uses the same canonical verifier as local development, checks the actual commit range for whitespace, compiles all Python and runs the full pytest suite with minimal permissions, pip cache, timeout and stale-run cancellation.
- MA-CONTAINER-DEPLOYMENT-HARDENING (#171, PR #186): deny-by-default Docker context, explicit runtime COPY allowlist, non-root UID 10001, read-only/capability-free Compose services, localhost-only publish and fail-closed self-hosted opt-in; real image and Compose smoke passed.
- MA-HEALTH-RESPONSE-HARDENING (#170, PR #185): public `/health` is dependency-free and path-free; detailed corpus/index/Ollama diagnostics require an admin browser session; Telegram consumes only the bounded liveness contract.
- MA-TELEGRAM-AUTH-HARDENING (#168, PR #183): Telegram uses machine Bearer auth, fail-closed chat allowlist and redacted health/error messages.
- MA-BOOTSTRAP-HOST-VALIDATION (#169, PR #184): strict HTTP/WebSocket Host allowlist, robust hostname/port/IPv6 parser, DNS-rebinding-safe local bootstrap and self-hosted fail-fast policy.
- SEC-P0-PUBLIC-TREE-CLEANUP (#166, PR #182): current public HEAD is cleaned, private corpus uses ignored local overlay, and privacy regression tests are active; history remediation remains #167.
- MA-TELEGRAM-AUTH-HARDENING (#168): Telegram `/chat` calls send machine Bearer auth; startup requires a real API token and allowlist or explicit allow-all; user-facing health/errors are path-free and do not echo response bodies.
- Repository acquisition/security audit: full pytest 1269 passed / 13 skipped; compileall, Docker Compose config and strict MkDocs build passed; dependency, Bandit, Ruff, dead-code, coverage, Git-history and manual API/auth/pipeline/RAG/UI reviews completed.
- SEC-P0-PUBLIC-TREE-CLEANUP (#166): removed tracked customer-specific eval/reference outputs and private model-comparison script; replaced real names and project queries with synthetic fixtures; public corpus/hotword defaults are generic.
- Private corpus configuration now uses ignored `configs/asu_june_bot/*.local.yaml` overlays; public-safety tests enforce the quality-doc allowlist, known private-marker absence and path hygiene.
- Confirmed follow-up risks are tracked in GitHub issues #167-#181; destructive history rewrite remains explicitly separate and requires owner approval.

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
- MA-MEETING-QA-BAD-ANSWER-FALLBACK (#151): meeting-scoped Q&A now treats degenerate one-word/fragment LLM outputs as controlled `no_answer` instead of successful `answered`.
- MA-MEETING-INDEX-ATOMIC-UPDATES (#153): meeting chunk/artifact index upserts now skip malformed runtime JSONL lines and write `data/meeting_chunks.jsonl` through lock + temp file + `os.replace`.
- MA-WORKSPACE-AUTH-STATE-CLARITY (#154): Workspace header shows signed-in/auth-unavailable/not-signed-in state; 403 CSRF failures no longer show the login-required overlay as if the session were absent.
- MA-DIARIZATION-RUNTIME-PREFLIGHT (#160, PR #161): sherpa-onnx diarization now checks optional runtime dependencies during dry-run/readiness/job preflight; missing `sherpa_onnx` blocks the UI stage with `diarization_runtime_missing` instead of allowing a failed job.

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
- Job state persists in ignored `logs/jobs_state.json`: records are written
  atomically under an OS advisory lock, histories/events are bounded, and a
  corrupt or oversized snapshot fails API startup closed. After an API restart,
  a verified live child is exposed as `orphaned` for explicit cancellation;
  a missing child becomes `failed` and the stage becomes `ready_for_retry`.
- Diarization is optional-runtime gated: if sherpa-onnx dependencies are not installed in the active API environment, readiness returns `blocked` / `diarization_runtime_missing` and the Workspace should not start the stage. Use the isolated diarization environment or install `requirements-diarization.txt` before enabling it.
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
GET  /admin/diagnostics/health
GET  /admin/diagnostics/meetings/{meeting_id}
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

- MA-MEETING-API-METADATA-REDACTION (#173): path-safe meeting DTOs and errors.
- SEC-P0-GIT-HISTORY-PURGE (#167): backup, verify and coordinate the force rewrite; do not execute implicitly.

## Open decisions / blockers

- #167 rewrites published history and invalidates old clones; it is blocked on explicit owner approval and a verified backup.
- PR #163 for #162 is currently conflict-dirty and must be rebased before merge; do not duplicate its scoped anonymization/index/runner fixes.
- Admin console contract is defined; dedicated admin UI, aggregate jobs/audit/settings endpoints and destructive meeting admin actions remain future implementation work.
- Guard pure decision API is available for deterministic tests; future guard behavior changes must use it as a measurement boundary.
- Local preflight can fail until Ollama is running and exposes `bge-m3` + `qwen3.5:4b` through the active model store.
- Transcript anonymization is heuristic and requires manual review before publishing anonymized examples or eval fixtures; see `docs/operations/TRANSCRIPT_ANONYMIZATION.md`.
- Meeting summary benchmark is deterministic and lexical by design; it is a smoke gate, not a semantic judge. Reports under `eval/reports/` stay runtime-only.
- Local/private runtime outputs under `meetings/`, `data/`, `logs/`, model caches, transcripts and indexes must remain out of Git.
- `/MeetingAgent` is now the intended product entrypoint; `/ui` remains the separate Project Knowledge Bot surface.
