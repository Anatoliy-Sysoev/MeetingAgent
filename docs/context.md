# Текущий Контекст

Обновлено: 2026-08-03.

## Now

- MA-LIVE-RUNTIME-STARTUP-GUARD (#307) устраняет повторяющийся отказ live UI
  после запуска API из core-only `.venv`. Штатный PowerShell launcher выбирает
  только проверенное live-окружение, валидирует Vosk-модель и аудиозависимости,
  блокирует конфликт порта; `MEETINGAGENT_LIVE_MODEL_PATH` позволяет держать
  native-модель в безопасном ASCII-пути без изменения публичного конфига.

- MA-SPEAKER-DOWNSTREAM-REBUILD (#297, parent #285) materializes a curated
  speaker transcript and tracks source/output revision hashes through chunks,
  enrichment, both indexes and structured artifacts. Speaker mapping or
  override edits immediately make dependent outputs stale; Workspace offers
  one CSRF-protected targeted rebuild action. The fixed rebuild plan never
  runs audio extraction, ASR, diarization or raw speaker merge.
- MA-PIPELINE-PROGRESS-AND-ETA (#286) now has its first product slice:
  faster-whisper publishes processed media seconds against the real source
  duration, GigaAM publishes completed chunks against the generated chunk
  count, and JobRunner exposes only a bounded normalized snapshot. The
  MeetingAgent registry and Workspace show determinate or indeterminate
  progress, elapsed time, honest nullable ETA and stale-update warnings.
  Remaining pipeline stages stay under #286 until they have measurable worker
  progress sources instead of UI guesses.
- MA-PROJECT-HIERARCHY (#304) records the product contract for assigning
  offline/live meetings to projects and bounded nested logical folders, for
  example `Проект АСУ -> Этап 3 -> Модуль ТДО`. The hierarchy must remain
  independent from physical runtime paths and support project-scoped search.
- MA-WORKSPACE-DIARIZE-RECOVERY (#301) fixes two failures observed in a real
  Workspace run: the mutable v5 bundle now has a new revisioned asset URL so
  browsers cannot reuse pre-speaker-count JavaScript, and cancellation clears
  a recovered orphan that exits after API startup. A local UI smoke confirmed
  that selecting six speakers launches the worker with `--num-speakers 6`.
- MA-RESOLVED-SPEAKER-TURNS (#296, parent #285) provides a deterministic
  resolved transcript view and TXT/Markdown exports. Adjacent corrected turns
  merge only for the same known speaker/source without overlap or a meaningful
  pause, while every source utterance ID remains available for citations and
  bounded Workspace expansion.
- MA-SPEAKER-OVERRIDES (#295, parent #285) adds audited, bounded and atomic
  corrections for one transcript utterance or a selected range. Workspace
  editors can assign an existing technical speaker label or restore automatic
  attribution; raw ASR and diarization artifacts remain immutable.
- MA-SPEAKER-DIRECTORY (#294, parent #285) adds a bounded private runtime
  profile store with CRUD API and Workspace select/create flow. Meeting
  mappings retain `speaker_id` plus reproducible name/role/company snapshots;
  profile deletion does not rewrite historical meetings.
- MA-DIARIZATION-SPEAKER-COUNT (#292, parent #285) exposes auto or an exact
  `1..20` speaker count in both MeetingAgent UI surfaces. The strict API and
  JobRunner pass it to sherpa-onnx before reservation; the meeting card and
  diarization report preserve requested and actual counts.
- MA-PIPELINE-STRUCTURED-ARTIFACT-INDEX-STAGE (#279) adds the explicit
  `index_artifacts` stage after `analyze` in the full pipeline. Chunk and
  structured index completion are tracked independently, including valid
  meetings whose structured artifact lists are empty.
- MA-MEETINGS-ROOT-WORK-ROOT-RESOLUTION (#265) resolves relative meeting
  registry paths under `work_root_path`. MeetingsService, JobRunner and live
  sessions now share one absolute root even when the API starts from another
  current working directory.
- MA-WORKSPACE-TRANSCRIPT-VIRTUALIZATION (#278) keeps large meeting
  transcripts responsive by rendering at most 150 filtered segments per page.
  Search still covers the complete transcript, citations reveal off-page
  segments, and playback highlighting no longer scans the full transcript DOM.
- MA-EXTRACTIVE-ARTIFACT-OVERCLASSIFICATION (#277) makes heuristic enrichment
  classify sentence-local evidence instead of promoting every sentence from a
  chunk-level semantic type. Summary and protocol now identify extractive
  output honestly instead of presenting it as LLM map-reduce.
- MA-DIARIZATION-REAL-RUN-VALIDATION-REGRESSION (#275) keeps dry-run and real
  diarization on the same native validation helper and adds direct coverage of
  the output-publication path.
- MA-DIARIZATION-ASCII-MODEL-PATH-READINESS (#273) makes the offline sherpa
  model root configurable and rejects unsupported native Windows Unicode paths
  before job reservation. Diarization dry-run now validates the real native
  configuration instead of checking only Python imports and file existence.
- MA-WINDOWS-SAFE-PROCESS-LIVENESS (#271) replaces the POSIX-style
  `os.kill(pid, 0)` probe on Windows with `OpenProcess/GetExitCodeProcess`.
  API-launched workers now survive process identity capture, while cancellation
  still uses verified PID + creation-time identity.
- MA-JOB-RUNTIME-PYTHON-SELECTION (#269) removes implicit `sys.executable`
  coupling from API-launched offline stages. Local config can select separate
  default, transcription, GigaAM and diarization Python workers; live capture
  remains in the API live runtime. Missing workers block readiness with a
  path-free reason before reservation, while rejected dry-runs retain bounded
  redacted diagnostics.
- MA-LIVE-VOSK-WINDOWS-PATH-READINESS (#267) prevents the native Windows Vosk
  runtime from starting with a non-ASCII model path that only passes the file
  layout check. Preflight now returns a bounded path-free reason, Workspace
  explains the block, and the runbook requires the API and model to use the
  Python 3.12 live/ASCII runtime boundary.
- MA-AUTH-DB-WORK-ROOT-RESOLUTION (#264) makes a relative `paths.auth_db`
  resolve under configured `work_root_path`, preventing a second empty auth
  database when the API starts from another CWD or worktree. The analogous
  meetings-root inconsistency is tracked separately as #265.
- MA-LIVE-DIART-INTEGRATION-V1 (#261) wires the isolated localhost sidecar into
  finalized SYS live capture. Speaker turns are overlap-mapped to Vosk segments,
  persisted atomically as a no-index artifact and exposed in the unified
  timeline; failures remain non-fatal. True during-capture streaming remains a
  separately scoped follow-up.
- MA-DIART-CACHE-PATHS (#259) routes Hugging Face, Torch, XDG and Matplotlib
  caches into the writable ignored `/cache` volume while retaining a non-root,
  read-only container. Real gated-model loading now completes with `ok: true`;
  legacy embedding compatibility warnings remain a quality-benchmark input.
- MA-LIVE-DIART-PILOT (#257) packages Diart as an isolated CPU-only Python 3.10
  sidecar. The exact dependency lock, non-root container and deterministic
  streaming smoke are verified; real pyannote model loading remains an explicit
  operator step that requires accepted model conditions and a local `HF_TOKEN`.
- MA-LIVE-UNIFIED-CAPTURE-UI (#255) makes MIC and SYS one user-level recording
  operation in Workspace while preserving separate source sessions, WAV files
  and provenance internally. The incompatible Workspace update uses immutable
  `/assets/v3/*`; the registry remains on `/assets/v2/*`.
- SEC-P0-GIT-HISTORY-PURGE (#167) completed the backup, local history rewrite,
  full verification and force-update of every public branch and tag. A fresh
  GitHub clone contains no targeted paths, known private markers or removed
  large blobs. GitHub still retains old commits through internal pull-request
  refs, so server-side Support cleanup is the only remaining closure step.
- UI interaction model approval is tracked as #237.

## Done latest

- SEC-P0-GIT-HISTORY-PURGE (#167): created and verified an offline mirror and
  bundle, rewrote 983 commits, restored the exact public-safe product tree,
  force-updated 46 branches plus `v0.1.0`, and validated a new GitHub clone.
  The post-rewrite suite passed with 2016 tests and 13 explicit skips.
- MA-RESOLVED-SPEAKER-TURNS (#296): added configurable resolved-turn merging,
  provenance-preserving API/exports and bounded source-utterance expansion in
  the virtualized Workspace transcript.
- MA-SPEAKER-OVERRIDES (#295): added editor-only CSRF-protected correction and
  reset APIs, a private event journal, resolved transcript fields that preserve
  the automatic label, and a range-capable Workspace editor.
- MA-SPEAKER-DIRECTORY (#294): added atomic bounded profile storage under
  `work_root_path`, editor-only path-free CRUD, duplicate detection and
  backward-compatible Workspace mapping snapshots.
- MA-DIARIZATION-SPEAKER-COUNT (#292): added strict single-stage, retry and
  pipeline option propagation, explicit diarization force-rerun wording and
  backward-compatible report/card metadata without mutating raw ASR.
- MA-PIPELINE-STRUCTURED-ARTIFACT-INDEX-STAGE (#279): the one-click full
  profile now runs `enrich -> index -> analyze -> index_artifacts`; readiness,
  manifest status, resume/force semantics and end-to-end meeting retrieval
  cover the final structured rows without duplicates.
- MA-MEETINGS-ROOT-WORK-ROOT-RESOLUTION (#265): removed CWD-dependent meeting
  discovery without copying or moving runtime meeting cards; absolute
  `meetings_root` values remain unchanged.
- MA-WORKSPACE-TRANSCRIPT-VIRTUALIZATION (#278): introduced immutable
  Workspace assets v5, bounded transcript pagination, full-data search and
  citation/seek navigation to segments outside the current page. Browser smoke
  now exercises a 1,505-segment transcript while asserting a 150-row DOM cap.
- MA-EXTRACTIVE-ARTIFACT-OVERCLASSIFICATION (#277): added conservative
  sentence-local candidate extraction, filtered meeting setup chatter and
  added honest analysis-mode labels to generated Markdown artifacts.
- MA-DIARIZATION-REAL-RUN-VALIDATION-REGRESSION (#275): removed the stale
  validation-helper call left after #273 and added a `dry_run=false` entrypoint
  regression test.
- MA-DIARIZATION-ASCII-MODEL-PATH-READINESS (#273): reproduced native model
  path corruption under a Cyrillic Windows profile, added an ASCII model-root
  contract and propagated it through API-launched workers.
- MA-WINDOWS-SAFE-PROCESS-LIVENESS (#271): reproduced the UI-only
  `0xC0000142` worker failure, proved that `process_identity()` terminated the
  child, added typed Win32 handle calls and a real subprocess regression test.
- MA-JOB-RUNTIME-PYTHON-SELECTION (#269): added validated stage/engine runtime
  selection, env overrides, selected-worker dry-runs, path-safe readiness and
  persisted exit/stderr diagnostics. Diarization dependency checks no longer
  import sherpa-onnx from the API environment.
- MA-LIVE-VOSK-WINDOWS-PATH-READINESS (#267): reproduced empty device lists
  from a core-only API environment and immediate worker failure from a complete
  Vosk model under a Cyrillic path; verified simultaneous MIC/SYS capture after
  moving the runtime and model to short ASCII paths.
- MA-LIVE-DIART-INTEGRATION-V1 (#261): added a loopback-only bounded HTTP
  client, hardened read-only `diart-api` Compose service, finalized-WAV speaker
  mapping, MIX/UI labels, schema/catalog registration and real 25-second model
  smoke. Offline sherpa remains canonical.
- MA-DIART-CACHE-PATHS (#259): real model loading no longer attempts to write
  `/home/meetingagent/.cache`; a Compose contract test preserves the hardened
  cache layout.
- MA-LIVE-DIART-PILOT (#257): added an exact CUDA-free Diart/pyannote/Torch CPU
  lock, hardened optional Compose profile, synthetic streaming preflight and an
  operations runbook. Diart remains a pilot and is not wired into live sessions
  until a real Russian meeting quality/latency comparison passes.
- MA-LIVE-UNIFIED-CAPTURE-UI (#255): Workspace has one start/stop control,
  shared VAD/replace settings, MIC and SYS device selectors, one elapsed timer,
  aggregated warnings/partials and one source-aware conversation. Group API
  start rolls MIC back if SYS cannot start; group stop attempts both sources.
- MA-MEETINGAGENT-UI-MOCKUPS (#237): approved responsive registry, creation,
  processing and Workspace prototypes plus the API/state/role matrix are now
  the production UI v2 baseline.
- MA-MEETINGAGENT-UI-V2 (#253): `/MeetingAgent` is a dense authenticated
  registry; `/MeetingAgent/new` supports offline/live creation and ASR/profile
  selection; `/MeetingAgent/processing` monitors/cancels the active job; the
  Workspace is split into Overview, Transcript, Artifacts, Q&A, Live and
  Pipeline tabs without removing existing API features. Browser smoke covers
  upload, pipeline, transcript mapping, artifacts, Q&A and live refinement.
- MA-DEPS-MAJOR-COMPATIBILITY (#236): NumPy/retrieval, transcription,
  diarization, live audio, isolated GigaAM and docs now have explicit matrix
  rows and rollback boundaries. Python Dependabot PRs are ungrouped so one bot
  update cannot again mix unrelated runtime majors; a unit test enforces it.
- MA-DEPS-DOCS-MATERIAL97 (#244): pins Material 9.7.6, adds MkDocs 1.6 strict
  target/anchor validation and makes Pages use `mkdocs build --strict`; clean
  docs install, `pip check`, zero-advisory audit and strict build pass. Material
  is maintenance-only; 9.5.50 is the rollback and Zensical remains a later ADR.
- MA-DEPS-GIGAAM-RUNTIME-COMPAT (#243): pins the isolated CPU graph to NumPy
  2.5.1, ONNX 1.22.0, ONNX Runtime 1.23.2, Torch 2.13.0 and TorchAudio 2.11.0;
  clean install, `pip check`, zero-advisory audit, upstream source/model load,
  ONNX utility import and deterministic short-speech inference pass. ONNX 1.22
  deliberately replaces upstream 1.19 because the old line has advisories.
- MA-DEPS-SOUNDDEVICE05-COMPAT (#242): locks sounddevice 0.5.5 and NumPy 2.5.1
  on both platforms; clean Windows/Linux installs pass `pip check` and advisory
  audit; 101 live tests and a non-persisting one-second 16 kHz Windows MIC smoke
  pass. A contract test now rejects any shared core/live pin conflict, and docs
  require core+live inputs plus a short Windows venv path when long paths are off.
- MA-DEPS-NUMPY2-COMPAT (#241): widened only the core/diarization NumPy range to
  `<3`, locked Python 3.12 to 2.5.1, added persisted-index cross-major coverage
  and validated a clean install, `pip check`, advisory audit, retrieval tests
  and both real diarization ONNX models. Rollback remains NumPy 1.26.4.
- MA-PRODUCT-SPLIT-PHASE-2 (#235): core routes/state start without PKB search,
  chat, retrieval, health or Telegram imports; integrated routes and HTTP
  contracts remain stable; moved legacy imports are explicit deprecated aliases;
  runtime inventory, package data, Docker core profile and ownership docs are
  synchronized and covered by core-only/integrated regression tests.
- MA-ADMIN-CONSOLE-USERS-V1 (#234): protected `/admin` requires a local browser
  user with `users.manage`; all writes use session CSRF, user pagination reports
  the real total, status changes require explicit confirmation, last-admin
  protections remain authoritative and admin navigation stays hidden from
  unauthorized users across MeetingAgent, Workspace and Project Knowledge Bot.
- MA-LIVE-UNIFIED-TIMELINE-V1 (#233): final MIC/SYS segments are clock-aligned
  into atomic no-index MIX artifacts; the authenticated bounded timeline API
  and Workspace Conversation view retain source/origin references, tolerate one
  missing source and refresh after either session completes.
- MA-CI-ACTIONS-NODE24 (#220): checkout/setup-python/Pages actions now use
  reviewed Node 24-compatible majors; a repository-wide test rejects stale or
  newly introduced unreviewed official action references without changing
  workflow permissions, cache inputs or topology.
- API-VALIDATION-CTX-SANITIZATION (#227): recursive bounded validation-context
  sanitization drops exceptions, non-finite/non-JSON objects, sensitive keys
  and local locations; exception/input-derived messages become stable generic
  text while normal built-in validation messages and safe numeric context stay
  compatible.
- MA-LIVE-MEETING-CREATION (#223): added CSRF/RBAC-protected `POST /meetings/live`,
  collision-safe atomic card publication, language/source-kind public metadata,
  a `/MeetingAgent` create-and-open flow and browser coverage through Workspace
  MIC/SYS preflight without invented media, artifacts or index rows.
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
- MA-DIARIZATION-RUNTIME-PREFLIGHT (#160, PR #161): sherpa-onnx dependency and
  model checks run in the canonical diarization dry-run; #269 executes that
  dry-run with the selected isolated worker rather than the API interpreter.

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
- Job runner поддерживает стадии `extract_audio`, `transcribe`, `diarize`,
  `merge`, `resolve_speakers`, `chunk`, `enrich`, `index`, `analyze`,
  `index_artifacts`. Обычные pipeline-профили материализуют resolved speaker
  transcript после merge; профиль `speaker_rebuild` запускает только
  speaker-dependent хвост.
- Job state persists in ignored `logs/jobs_state.json`: records are written
  atomically under an OS advisory lock, histories/events are bounded, and a
  corrupt or oversized snapshot fails API startup closed. After an API restart,
  a verified live child is exposed as `orphaned` for explicit cancellation;
  a missing child becomes `failed` and the stage becomes `ready_for_retry`.
- Diarization is optional-runtime gated through `jobs.runtimes.diarization`.
  The API checks the configured worker executable without exposing its path;
  the canonical worker-side dry-run validates sherpa-onnx and ONNX models.
- Workspace UI: media player, clickable transcript, artifact viewer, job controls, readiness map, one-click pipeline profiles, meeting-scoped Search/Q&A.
- UI delivery (#180): `/`, `/ui`, `/MeetingAgent` and meeting Workspace load
  packaged `/assets/v1` CSS/JS under a restrictive CSP; dynamic values are
  rendered through DOM/text APIs, credentials/CSRF remain memory/cookie based,
  and Playwright exercises the primary browser workflows in CI.
- Workspace flow (#121): state panel (status + active job + public-safe last error), readiness-gated stage buttons (blocked → disabled with reason; done → explicit Force rerun; failed → Retry), pipeline actions (Run full / Resume when partially done / Retry failed stage), manifest-driven result chips (Transcript/Speaker transcript/Summary/Protocol/Tasks), Q&A disabled until chunks/index exist, panels auto-refresh after a job finishes; CSRF on every POST.
- Job failure recovery: `meeting.json.last_error` schema accepts normalized runner fields `code` and `job_id`, so CLI stages and retry flows can validate and recover cards after failed API jobs.
- Speaker mapping (#122/#294): `meeting.json.speaker_mapping` stores real
  name/role/company snapshots and optional private `speaker_id`; Workspace can
  select/create profiles from the ignored runtime directory while preserving
  stable technical labels.
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
GET  /meetings/{id}/live/timeline
GET  /meetings/{id}/live/refinement
POST /meetings/{id}/live/refinement
GET  /meetings/{id}/live/sessions/active
POST /meetings/{id}/live/capture
POST /meetings/{id}/live/capture/stop
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

- MA-PIPELINE-PROGRESS-AND-ETA (#286): the real ASR progress slice is
  implemented; extend the same bounded worker contract only to stages with a
  defensible denominator or leave them indeterminate.
- MA-LIVE-DIART-STREAMING-V2 (#262): evaluate bounded streaming diarization
  during capture while keeping offline sherpa-onnx canonical.

## Open decisions / blockers

- #167 awaits GitHub Support removal of internal pull-request refs and cached
  commit views under Support ticket #4593146. All operator-controlled public
  branches and tags are already rewritten and fresh-clone verification is
  clean.
- #237 intentionally does not change production UI before owner approval.
- Admin users/roles and redacted security status are available at `/admin`;
  aggregate jobs/audit/settings endpoints and destructive meeting admin actions
  remain future implementation work.
- Guard pure decision API is available for deterministic tests; future guard behavior changes must use it as a measurement boundary.
- Local preflight can fail until Ollama is running and exposes `bge-m3` + `qwen3.5:4b` through the active model store.
- Transcript anonymization is heuristic and requires manual review before publishing anonymized examples or eval fixtures; see `docs/operations/TRANSCRIPT_ANONYMIZATION.md`.
- Meeting summary benchmark is deterministic and lexical by design; it is a smoke gate, not a semantic judge. Reports under `eval/reports/` stay runtime-only.
- Local/private runtime outputs under `meetings/`, `data/`, `logs/`, model caches, transcripts and indexes must remain out of Git.
- `/MeetingAgent` is now the intended product entrypoint; `/ui` remains the separate Project Knowledge Bot surface.
