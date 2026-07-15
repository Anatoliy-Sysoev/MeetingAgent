# Todo

Обновлено: 2026-07-15.

## Done

- [x] MA-JOB-RUNTIME-PYTHON-SELECTION (#269): select explicit local Python
  workers for offline stages/ASR engines, retain backward-compatible fallback,
  report path-free readiness and preserve rejected dry-run diagnostics.
- [x] MA-LIVE-VOSK-WINDOWS-PATH-READINESS (#267): block unsupported native
  Windows Vosk model paths before capture and document the live API runtime.
- [x] MA-API-MEETINGS-RESTORE (#30): read-only Meeting API restored.
- [x] MA-INGEST-DEDUP (#34): `POST /meetings/ingest`, sha256 dedup, auth guard.
- [x] MA-JOB-API (#35): concurrency=1 job runner and base job endpoints.
- [x] MA-AUTH-FOUNDATION-MVP (#44): local users, sessions, RBAC, CSRF, bootstrap/admin API, deployment safety.
- [x] DOC-GIT-WORKFLOW (#45/#46): issue -> branch -> commit -> PR workflow documented.
- [x] MA-ARTIFACT-SIZE-LIMITS (#52): bounded transcript/artifact text reads.
- [x] DOC-API-AUTH-SETUP (#53): bilingual API/auth setup docs.
- [x] DOC-REPO-CLEANUP (#59): stale docs cleanup and public-safe repository rules.
- [x] MA-PRODUCT-SPLIT-PREP (#63): product boundary documentation and migration phases.
- [x] MA-MEETING-WORKSPACE (#68): Workspace page, media streaming, normalized transcript segments, artifact viewer.
- [x] MA-WORKSPACE-JOB-CONTROLS (#70): stage controls, cancel/refresh/polling, CSRF-safe browser actions.
- [x] MA-MEETING-SCOPED-QA (#74): meeting-scoped search/chat over indexed meeting chunks.
- [x] MA-PIPELINE-STAGES-EXPANSION (#76): runner stages `extract_audio`, `chunk`, `enrich`, `index`, `analyze`.
- [x] MA-POST-PIPELINE-HARDENING (#78): product ASR model pin, Workspace DOM/CSP hygiene, honest Q&A citations.
- [x] MA-PIPELINE-E2E-SMOKE (#80): deterministic meeting pipeline smoke coverage.
- [x] MA-RUNTIME-HARDENING-BUGFIX-PACK (#84-#91, #99): validation redaction, path leakage fix, secret/proxy hardening, UTF-8, artifact guards, subtitle duration, prompt boundaries.
- [x] MA-REVIEW-QUEUE (#36): manual review queue over chat runs.
- [x] MA-GUARD-V2-CASES-EXPORT (#102): reviewed chat runs -> guard/eval regression cases.
- [x] MA-GUARD-V2-REGRESSION-TESTS (#104): guard case loader and regression harness.
- [x] MA-UI-CHAT-AUTH (#107): Web UI local login/auth badge/CSRF for chat.
- [x] MA-PROMPT-DELIMITER-ESCAPING (#108): neutralize fake untrusted-source delimiters in retrieved content.
- [x] MA-MEETING-QA-V2 (#111): semantic vector retrieval for meeting Q&A with lexical fallback.
- [x] MA-WORKSPACE-QA-V2-UI (#113): retrieval mode and precise citation labels in Workspace Q&A.
- [x] MA-MEETING-STAGE-READINESS (#114): readiness map API.
- [x] MA-MEETING-PIPELINE-RUN-ALL (#115): one-click sequential pipeline job.
- [x] DOC-CURRENT-STATE-REFRESH (#127): current documentation refresh.
- [x] MA-MEETING-ARTIFACT-CONTRACT (#119, PR #129): stable artifact manifest + shared catalog resolver.
- [x] MA-MEETING-ERRORS-AND-RETRY (#120, PR #130): normalized last_error, stage retry, pipeline resume, ready_for_retry readiness.
- [x] MA-WORKSPACE-FLOW (#121, PR #131): readiness/manifest-driven workspace flow, run/resume/retry controls, result chips, Q&A gating, pipeline-aware polling.
- [x] MA-SPEAKER-MAPPING-UI (#122): manual `SPEAKER_XX` -> name/role mapping, API endpoints, Workspace editor and mapped transcript display.
- [x] MA-MEETING-STRUCTURED-ARTIFACTS-V2 (#123): source-grounded summary/protocol and structured decisions/tasks/risks/open questions with speaker refs, confidence and needs_review.
- [x] MA-MEETING-QA-SEGMENT-CITATIONS (#126): meeting Q&A/search citations resolve to exact transcript segment refs when available, with chunk-level fallback.
- [x] MA-MEETING-PACKAGING-LOCAL (#124): local all-in-one runbook, Docker healthcheck and preflight CLI for Docker/Ollama/models/ffmpeg/optional ASR — 2be1f89.
- [x] MA-PRODUCT-SPLIT-PHASE-1 (#125, PR #136): shared utilities extracted into `meeting_agent.shared`; meeting-owned code imports shared layer directly; old bot imports remain compatibility shims.
- [x] MA-GUARD-PURE-DECISION-API (#106): pure deterministic `evaluate_guard_decision()` API for regression tests, wrapping existing guard behavior without retrieval/LLM/network/chat orchestration.
- [x] MA-ADR-AUTH-PROVIDERS (#39): ADR-0039 defines provider-agnostic browser auth, Yandex ID as first planned external provider, local RBAC as authoritative and machine token as separate fallback.
- [x] MA-ADMIN-CONSOLE (#40): admin console IA/API contract for users/roles, access settings, jobs, meetings admin, audit/diagnostics and runtime settings.
- [x] MA-TRANSCRIPT-ANONYMIZATION (#22): local JSONL/Markdown transcript anonymization CLI, public-safe report, optional private mapping and custom terms.
- [x] MA-MEETING-SUMMARY-BENCHMARK (#24): public synthetic meeting-summary benchmark and deterministic artifact evaluator for provider comparison.
- [x] PUBLIC-SAMPLE-MEETING-DATASET (#19): schema-valid synthetic meeting card with transcript, speaker transcript, expected summary/protocol and structured artifacts.
- [x] TRANSCRIPT-TO-PROTOCOL-QUICKSTART (#20): public sample transcript-to-protocol CLI guide with e2e smoke over the synthetic dataset.
- [x] CODEX-SECURITY-REVIEW-CHECKLIST (#21): public AI-assisted security review checklist linked from SECURITY and PR template.
- [x] RELEASE-WORKFLOW-CHANGELOG (#23): release checklist, reusable changelog format, bilingual changelog validator and manual release-validation workflow.
- [x] DOCS-PARITY (#25): bilingual parity guide plus tests for paired docs, language switches and public example parity.
- [x] GITHUB-PAGES-DOCS (#26): MkDocs Material documentation site config, local build instructions and GitHub Pages workflow.
- [x] WINDOWS-UTF8-DOC-NOTE (#92): useful external PR note incorporated into Docker docs with conflict-free wording.
- [x] MA-MEETINGAGENT-HOME-UI: `/MeetingAgent` primary product shell with meeting registry, upload form, pipeline launch actions, active job panel and separate `/ui` Project Knowledge Bot tab.
- [x] MA-MEETING-LAST-ERROR-SCHEMA-FIX: `meeting.json.last_error` accepts runner `code`/`job_id`, so failed API jobs no longer block direct CLI recovery/validation.
- [x] MA-UI-ASR-ENGINE-SELECTOR (#150): `/MeetingAgent` upload/pipeline flow can choose `faster-whisper` or `gigaam` and passes the choice to the runner API.
- [x] MA-SPEAKER-TRANSCRIPT-MAPPED-TXT (#152): human-readable `speaker_transcript.txt` uses saved speaker names/roles; JSONL keeps stable technical labels.
- [x] MA-MEETING-QA-BAD-ANSWER-FALLBACK (#151): malformed short Meeting Q&A LLM fragments return controlled `no_answer`, not successful `answered`.
- [x] MA-MEETING-INDEX-ATOMIC-UPDATES (#153): meeting chunks/artifacts index upserts skip malformed runtime JSONL lines and write through lock + atomic replace.
- [x] MA-WORKSPACE-AUTH-STATE-CLARITY (#154): Workspace header shows explicit auth state and CSRF 403 does not trigger misleading login overlay.
- [x] MA-DIARIZATION-RUNTIME-PREFLIGHT (#160): canonical diarization dry-run/job
  preflight checks sherpa-onnx dependencies; #269 moves that check into the
  selected isolated worker instead of importing it from the API runtime.
- [x] MA-ADMIN-CONSOLE-USERS-V1 (#234): protected `/admin` user/role lifecycle,
  explicit account status confirmation, real bounded pagination, redacted
  security/bootstrap summary and permission-gated product navigation.
- [x] MA-PRODUCT-SPLIT-PHASE-2 (#235): MeetingAgent API/auth/meetings/jobs/live
  ownership moved to the independently startable core; integrated PKB runtime
  and deprecated legacy imports remain backward compatible.

## Active / Next

- [x] MA-AUTH-DB-WORK-ROOT-RESOLUTION (#264): resolve relative auth SQLite paths
  under configured `work_root_path` so local admins survive alternate CWDs.
- [ ] MA-MEETINGS-ROOT-WORK-ROOT-RESOLUTION (#265): resolve the meeting registry
  root consistently for MeetingsService, jobs and live sessions.
- [x] SEC-P0-PUBLIC-TREE-CLEANUP (#166, PR #182): current public HEAD cleaned; private corpus overlays and privacy regression guards added — dd4d0a4.
- [ ] SEC-P0-GIT-HISTORY-PURGE (#167): purge deleted private blobs after backup and explicit force-push approval.
- [x] MA-TELEGRAM-AUTH-HARDENING (#168, PR #183): authenticated Chat API calls and fail-closed Telegram policy — 529b8b3.
- [x] MA-BOOTSTRAP-HOST-VALIDATION (#169, PR #184): strict Host allowlist and DNS-rebinding-safe local bootstrap — afd4ede.
- [x] MA-HEALTH-RESPONSE-HARDENING (#170): minimal public liveness, admin-only detailed diagnostics, bounded Telegram rendering and redacted dependency errors.
- [x] MA-CONTAINER-DEPLOYMENT-HARDENING (#171): allowlisted build context, non-root/read-only runtime, localhost publish, self-hosted opt-in and real container smoke.
- [x] MA-CI-FULL-TEST-MATRIX (#172): canonical local/CI verifier runs whitespace, compileall and the full pytest suite with minimal workflow permissions and pip cache.
- [x] MA-MEETING-API-METADATA-REDACTION (#173): explicit path-safe meeting DTOs,
  stable artifact/media URLs, bounded machine errors and admin-only raw-card diagnostics.
- [x] MA-INGEST-LIMITS-ATOMIC-DEDUP (#174): validated 2 GiB default upload
  limit, full temp cleanup, bounded metadata/errors and thread/process-safe SHA dedup.
- [x] PKB-SEARCH-SOURCE-PROMOTION-DEDUP (#175): deterministic first-wins source
  identity, no cross-bucket duplicates and diagnostics limited to actual promotions.
- [x] MA-JOB-DURABILITY-RECOVERY (#176): atomic locked job/pipeline snapshot,
  bounded history/events, restart orphan detection, cross-runner reservation,
  verified process-tree cancellation and Workspace recovery status.
- [x] TEST-CSRF-TOKEN-FLAKE (#193): assert parsed CSRF response fields instead
  of forbidden substrings inside random token entropy.
- [x] MA-DEPENDENCY-LOCK-AND-AUDIT (#177): separated core/transcription/
  diarization/dev groups, reviewed Python 3.12 constraints lock, clean pinned
  audit, scheduled and release gates, expiring exception policy and Dependabot
  updates.
- [x] PKB-RETRIEVAL-CHARACTERIZATION (#178): public characterization cases,
  typed ranking policies, config-driven terminology, deterministic traces and
  retrieval/source-routing coverage gates.
- [x] MA-REPO-DEAD-CODE-CLEANUP (#179): machine-checked runtime inventory,
  supported CLI/import smoke, visible legacy migration warnings, empty scaffold
  removal and canonical ASR defaults.
- [x] MA-UI-CSP-MODULARIZATION (#180): packaged versioned frontend assets,
  restrictive self-only CSP, immutable asset delivery and browser-level smoke
  coverage for upload/pipeline/Workspace workflows.
- [x] TEST-WORKSPACE-CRLF-PARSING (#200): Workspace static UI assertions are
  newline-agnostic on Windows and Linux checkouts.
- [x] MA-MEETING-VECTOR-CACHE-LOCKING (#181): locked and atomic semantic cache,
  concurrent first-fill deduplication, malformed-tail recovery and rebuild CLI.
- [x] MA-PRIVACY-RUNTIME-HARDENING (#162): no speaker/source PII or original
  hashes in public anonymization output, relative-only meeting index rows,
  bounded path-safe preflight errors, atomic last_error and correct readiness status.
- [x] MA-LIVE-AUDIO-CAPTURE-V1 (#164): no-capture MIC/SYS/MIX inventory and
  preflight, separate device/backend readiness, fail-closed SYS/MIX runtime and
  deterministic file-smoke compatibility.
- [x] MA-LIVE-LOOPBACK-CAPTURE-V1 (#204): real Windows SYS capture through
  PyAudioWPatch plus stateful SoXR stereo 44.1/48 kHz -> mono 16 kHz conversion.
- [x] MA-LIVE-STREAMING-VAD-V1 (#205): apply Silero VAD to microphone/loopback streams
  while preserving real-time timestamps.
- [x] MA-LIVE-SESSION-API-V1 (#206): authenticated preflight/start/stop/status/
  event lifecycle, bounded durable state, duplicate protection, graceful stop
  and deterministic stale recovery.
- [x] MA-LIVE-UI-V1 (#207): Workspace MIC/SYS preflight, device/VAD controls,
  graceful start/stop, bounded partial/final draft, elapsed time and warnings.
- [x] MA-LIVE-AUDIO-ARCHIVE-V1 (#225): retain bounded source-scoped MIC/SYS WAV
  with atomic publication, media registration and no-index provenance.
- [x] MA-LIVE-OFFLINE-REFINEMENT-V1 (#208): retain the live draft, run canonical
  offline ASR through the durable runner and expose safe source-scoped status/
  comparison without indexing the draft.
- [x] MA-LIVE-PIPELINE-COORDINATION (#222): shared cross-process reservation
  enforces server-side mutual exclusion between live capture and offline
  stage/pipeline jobs while preserving MIC+SYS capture.
- [x] MA-LIVE-MEETING-CREATION (#223): create a schema-valid live-only meeting
  from `/MeetingAgent` without uploading media first; atomic ID allocation,
  RBAC/CSRF, list/detail/readiness and browser-to-Workspace preflight covered.
- [x] MA-LIVE-UNIFIED-TIMELINE-V1 (#233): derive atomic no-index MIX transcript
  artifacts from clock-aligned MIC/SYS final segments and render one bounded,
  source-aware Conversation view through an authenticated timeline API.
- [x] MA-LIVE-UNIFIED-CAPTURE-UI (#255): one Workspace start/stop operation for
  selected MIC and SYS devices, with atomic-style rollback on partial start,
  aggregate status/warnings/partials and separate internal source provenance.
- [x] API-VALIDATION-CTX-SANITIZATION (#227): recursively sanitize non-JSON
  Pydantic validation context so malformed requests return bounded 422, not 500;
  exception-derived/custom sensitive messages and local paths are redacted.
- [x] MA-CI-ACTIONS-NODE24 (#220): upgrade all official workflow actions to
  reviewed Node 24-compatible majors and prevent stale refs with a contract test.
- [x] MA-LIVE-LOOPBACK-IDLE-SAFETY (#213): make bounded SYS capture and Ctrl+C
  interruptible when the Windows output device emits no loopback packets.
- [x] MA-LIVE-DEPENDENCY-LOCK (#214): exact CPU-only Python 3.12 Windows/Linux
  live locks, clean-install contract and scheduled audit matrix without adding
  Torch/Vosk to core or the base image.
- [x] MA-LIVE-MIC-BACKPRESSURE (#215): bounded non-blocking MIC callback queue,
  deterministic oldest-block eviction, absolute-frame silence recovery and
  path-free queue/loss metrics with report warnings.
- [x] TEST-DEPENDENCY-AUDIT-WINDOWS-UTF8 (#209): force deterministic UTF-8
  subprocess semantics for pip-audit under Cyrillic Windows profile paths.
- [x] MA-MEETINGAGENT-UI-MOCKUPS (#237): approved responsive registry,
  upload/live, processing and Workspace mockups plus API state/role/accessibility
  contract.
- [x] MA-MEETINGAGENT-UI-V2 (#253): production table-first registry,
  addressable create/processing routes and tabbed Workspace on isolated
  `/assets/v2/*`, with role-aware writes, strict CSP and Chromium workflow tests.

## Meeting Product Backlog

- [x] MA-DIART-CACHE-PATHS (#259): route all optional Diart model/runtime caches
  into the writable ignored volume without weakening the read-only container.
- [x] MA-LIVE-DIART-PILOT (#257): isolated CPU-only Diart runtime with exact
  Python 3.10/Linux lock, hardened container, deterministic streaming smoke and
  explicit gated-model preflight.
- [x] MA-LIVE-DIART-INTEGRATION-V1 (#261): localhost-only sidecar labels the
  finalized SYS live WAV, maps speaker turns to Vosk segments and publishes
  preliminary labels in the no-index MIX timeline without weakening capture.
- [ ] MA-LIVE-DIART-STREAMING-V2 (#262): feed bounded PCM chunks to Diart while capture
  is active, reconcile evolving labels and benchmark Russian meeting quality;
  offline sherpa remains canonical.
- [x] MA-DEPS-MAJOR-COMPATIBILITY (#236): validate core/transcription/
  diarization/live/GigaAM/docs separately and prohibit catch-all Python
  Dependabot grouping.
- [x] MA-DEPS-NUMPY2-COMPAT (#241): validate NumPy 2.5.1 with exact Python 3.12
  constraints, cross-major persisted-index coverage and real ONNX/sherpa smoke.
- [x] MA-DEPS-SOUNDDEVICE05-COMPAT (#242): review sounddevice 0.5.x with exact
  platform locks and non-persisting Windows device/callback smoke.
- [x] MA-DEPS-GIGAAM-RUNTIME-COMPAT (#243): exact isolated Windows/Python 3.12
  CPU lock, zero-advisory audit and real local GigaAM short-speech model smoke.
- [x] MA-DEPS-DOCS-MATERIAL97 (#244): Material 9.7.6 exact lock, clean docs
  install, strict target/anchor validation and zero-advisory audit.

## Project Knowledge Bot / Guard / Auth Backlog

- Admin jobs/audit/runtime-settings views remain later independently scoped
  slices; the users/roles surface is complete in #234.

## Documentation / OSS Backlog


## Operating Rules

- Public Git must not include real transcripts, customer documents, runtime meeting cards, indexes, caches, logs, local configs or secrets.
- Long offline ASR jobs must run as background/status workflows, not short shell/API timeouts.
- GigaAM remains an optional isolated local runtime; do not commit GigaAM venv/cache/chunks/raw outputs.
- `data/meeting_embeddings_cache.jsonl`, `data/meeting_chunks.jsonl`, private review labels and real eval outputs are runtime data.
