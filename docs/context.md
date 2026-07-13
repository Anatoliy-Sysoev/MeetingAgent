# Текущий Контекст

Обновлено: 2026-07-13.

## Now

- MA-LIVE-PIPELINE-COORDINATION (#222) is implemented on its review branch:
  a shared cross-process advisory lock atomically arbitrates live capture and
  offline stage/pipeline reservations for the same meeting, while preserving
  concurrent MIC+SYS capture and independent work on different meetings.
- canonical main: `9f2e4a5` / `Refine live drafts with canonical offline ASR (#228)`.
- Next confirmed work: live-only browser meeting creation #223 and validation
  ctx sanitization #227.
  History purge #167 remains gated by explicit owner approval and backup.

## Done latest

- MA-LIVE-PIPELINE-COORDINATION (#222): browser and bearer callers now receive
  the same bounded server-side `live_session_active`/`offline_job_active`
  conflicts; readiness/preflight expose the block; thread/process races have
  exactly one winner and existing stale/terminal recovery releases ownership.
- MA-LIVE-OFFLINE-REFINEMENT-V1 (#208): canonical faster-whisper/GigaAM jobs can
  refine retained MIC/SYS audio without deleting or indexing the live draft;
  retry/resume is hash-guarded and the Workspace renders durable refinement
  status plus a path-free comparison summary.
- MA-LIVE-AUDIO-ARCHIVE-V1 (#225): added bounded pre-VAD PCM16 WAV streaming,
  atomic finalization, MIC/SYS media registration, no-index provenance and an
  explicit safe `--media-path` selector for canonical offline ASR.
- MA-LIVE-UI-V1 (#207): added an authenticated CSP-safe Workspace surface for
  MIC/SYS drafts, explicit blocked reasons and replace semantics, cursor-based
  polling, keyboard-native controls and UI-level live/offline mutual exclusion.
- MA-LIVE-SESSION-API-V1 (#206): added RBAC/CSRF-protected lifecycle routes,
  source preflight DTO sanitization, bounded polling, memory-only partials,
  durable final/status events, process-owner locking, graceful stop and stale
  restart recovery.
- MA-LIVE-DEPENDENCY-LOCK (#214): added platform-specific exact live locks,
  kept Torch/Vosk outside core/Docker, validated clean Windows and Linux
  installs plus real Silero model loads, and expanded scheduled advisory audit
  to core, live-linux and live-windows graphs.
- MA-LIVE-MIC-BACKPRESSURE (#215): bounded the MIC callback queue, added
  deterministic oldest-first overflow handling, absolute-frame gap recovery,
  path-free loss/queue metrics, report warnings and duration/Ctrl+C regression
  coverage.
- MA-LIVE-LOOPBACK-IDLE-SAFETY (#213): replaced unconditional native SYS reads
  with availability-gated polling, fixed-quantum wall-clock scheduling, idle PCM
  insertion, bounded path-free diagnostics and active/idle hardware smoke.
- MA-LIVE-STREAMING-VAD-V1 (#205): added 512-frame stateful Silero filtering for
  MIC/SYS, source-frame timestamp remapping, monotonic segment normalization,
  bounded configuration and report-level filtered-duration/warning metrics.
- MA-LIVE-LOOPBACK-CAPTURE-V1 (#204): added real Windows system-audio capture,
  source-specific device selection, native stereo downmix/resampling, bounded
  path-free runtime metrics and deterministic hardware/mocked coverage.
- TEST-DEPENDENCY-AUDIT-WINDOWS-UTF8 (#209): removed the locale-dependent
  `pip_api` startup failure without changing the parent shell environment.
- MA-LIVE-AUDIO-CAPTURE-V1 (#164): added no-capture source inventory/preflight,
  automation-friendly result codes and an honest hardware/backend readiness
  contract that prevents MIC audio from being mislabeled as SYS or MIX.
- MA-PRIVACY-RUNTIME-HARDENING (#162): closed the remaining public-surface
  privacy gaps without reviving the obsolete pre-CSP UI diff from PR #163.
- MA-MEETING-VECTOR-CACHE-LOCKING (#181): moved semantic cache I/O behind a
  shared advisory lock; first-query chunk embeddings are computed once across
  concurrent threads/processes; valid rows from all embedding models survive
  deterministic deduplication; malformed, invalid and truncated records are
  removed by atomic rewrite; storage failures retain lexical fallback.
- TEST-WORKSPACE-CRLF-PARSING (#200): Workspace UI static tests now behave the
  same for LF and CRLF checkouts while preserving all CSRF, polling, DOM and
  auth assertions.
- MA-UI-CSP-MODULARIZATION (#180): removed monolithic inline HTML/CSS/JS from
  API route modules; added allowlisted package-data templates and immutable
  `/assets/v1/*` delivery; product pages enforce a self-only CSP without
  `unsafe-inline`/`unsafe-eval`; Chromium tests execute the upload/pipeline and
  Workspace workflows. Browser execution also caught and fixed a mapping-save
  confirmation that was immediately cleared during refresh.
- MA-REPO-DEAD-CODE-CLEANUP (#179): empty apps/templates/packages were removed;
  `configs/runtime_inventory.yaml` owns every package/script; current CLI help
  and package imports are smoke-tested; retained v1 entrypoints point to their
  replacements; offline ASR defaults to `large-v3-turbo` everywhere.
- PKB-RETRIEVAL-CHARACTERIZATION (#178): BM25 intent boosts, hybrid fusion and
  post-rerank rules are decomposed into independently testable policies;
  customer vocabulary lives in `ranking_profile.yaml` plus ignored local
  overlay; every applied multiplier emits a deterministic trace; retrieval and
  source-routing coverage is enforced separately from LLM/API tests.
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
- UI delivery (#180): `/`, `/ui`, `/MeetingAgent` and meeting Workspace load
  packaged `/assets/v1` CSS/JS under a restrictive CSP; dynamic values are
  rendered through DOM/text APIs, credentials/CSRF remain memory/cookie based,
  and Playwright exercises the primary browser workflows in CI.
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
GET  /meetings/{id}/live/preflight
GET  /meetings/{id}/live/refinement
POST /meetings/{id}/live/refinement
GET  /meetings/{id}/live/sessions/active
POST /meetings/{id}/live/sessions
GET  /meetings/{id}/live/sessions/{session_id}
GET  /meetings/{id}/live/sessions/{session_id}/events
POST /meetings/{id}/live/sessions/{session_id}/stop
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

- MA-LIVE-OFFLINE-REFINEMENT-V1 (#208): preserve the draft and produce the
  canonical offline transcript without indexing live artifacts.
- MA-LIVE-PIPELINE-COORDINATION (#222): enforce cross-process server-side
  mutual exclusion between live capture and offline jobs.
- MA-LIVE-MEETING-CREATION (#223): create an ad-hoc live-only meeting from the
  browser without requiring a media upload.

## Open decisions / blockers

- #208 depends on merging the retained source-audio contract from #225.
- #167 rewrites published history and invalidates old clones; it is blocked on explicit owner approval and a verified backup.
- Admin console contract is defined; dedicated admin UI, aggregate jobs/audit/settings endpoints and destructive meeting admin actions remain future implementation work.
- Guard pure decision API is available for deterministic tests; future guard behavior changes must use it as a measurement boundary.
- Local preflight can fail until Ollama is running and exposes `bge-m3` + `qwen3.5:4b` through the active model store.
- Transcript anonymization is heuristic and requires manual review before publishing anonymized examples or eval fixtures; see `docs/operations/TRANSCRIPT_ANONYMIZATION.md`.
- Meeting summary benchmark is deterministic and lexical by design; it is a smoke gate, not a semantic judge. Reports under `eval/reports/` stay runtime-only.
- Local/private runtime outputs under `meetings/`, `data/`, `logs/`, model caches, transcripts and indexes must remain out of Git.
- `/MeetingAgent` is now the intended product entrypoint; `/ui` remains the separate Project Knowledge Bot surface.
