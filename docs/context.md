# Текущий Контекст

Обновлено: 2026-07-06.

## Now

- active task: MA-SPEAKER-MAPPING-UI (#122) — implemented on branch `122-speaker-mapping-ui`, awaiting review/PR.
- branch: `122-speaker-mapping-ui`.
- canonical main state: latest merged pipeline/UI work is in `origin/main` through PR #131.

## Done latest

- MA-WORKSPACE-QA-V2-UI (#113, PR #116): Workspace Q&A/Search показывает `retrieval_mode` (`semantic`/`lexical`) и `citation_label` вида `[00:12:34, Спикер]`; DOM/CSP-гигиена сохранена.
- MA-MEETING-STAGE-READINESS (#114, PR #117): `GET /meetings/{id}/pipeline/readiness` отдаёт карту стадий `done/ready/blocked`, `can_run`, machine-readable `reason`, required/produced artifacts без абсолютных путей.
- MA-MEETING-PIPELINE-RUN-ALL (#115, PR #118): `POST /meetings/{id}/jobs/pipeline` запускает последовательные профили `default`, `full`, `transcript_only`, `qa_ready`; готовые стадии skip без `force`; cancel останавливает текущую дочернюю стадию.
- MA-MEETING-ARTIFACT-CONTRACT (#119, PR #129): stable artifact manifest, shared catalog resolver, transcription report entry, default-path artifact serving.
- MA-MEETING-ERRORS-AND-RETRY (#120, PR #130): normalized public-safe `last_error`, stage retry, pipeline resume, `ready_for_retry` readiness. Issue #120 closed after merge.
- MA-WORKSPACE-FLOW (#121, PR #131): readiness/manifest-driven Workspace flow, run/resume/retry controls, pipeline-aware polling, Q&A gating, CSRF on every POST. Issue #121 closed after merge.
- MA-SPEAKER-MAPPING-UI (#122): manual `SPEAKER_XX` -> name/role mapping in `meeting.json`, speaker discovery API, Workspace editor and mapped transcript display.

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
- Speaker mapping (#122): `meeting.json.speaker_mapping` stores real names/roles for diarized labels; `GET /meetings/{id}/speakers` discovers labels from diarization/transcript artifacts; `PUT /meetings/{id}/speakers/mapping` requires `meetings.edit` + CSRF; Workspace transcript shows mapped names while preserving `speaker_label`.
- Meeting Q&A v2: vector retrieval over meeting chunks через Ollama `bge-m3`, fusion с lexical, lazy cache `data/meeting_embeddings_cache.jsonl`, graceful lexical fallback.
- Meeting Q&A citations содержат timestamps, speaker labels, `utterance_ids`, `citation_label`, `citations_basis`; результаты строго scoped по `meeting_id`.

### Project Knowledge Bot

- `src/asu_june_bot/` остаётся production-ready reference runtime для Project Knowledge Bot: API, Web UI, Telegram adapter, retrieval, chat, guardrails, review queue, eval/export harness.
- Review queue и guard cases export/regression harness реализованы; guard v2 runtime/pure decision API ещё не внедрён.
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

- #123 MA-MEETING-STRUCTURED-ARTIFACTS-V2 — source-grounded summary/protocol/decisions/tasks/risks/open questions.

## Open decisions / blockers

- #39/#40 auth evolution: per-user tokens/OIDC/admin console direction remains open.
- #106 guard pure decision API remains open before guard v2 runtime can be cleanly measured.
- #123 structured artifacts v2 is the next product gap before meeting outputs feel complete for non-technical users.
- Local/private runtime outputs under `meetings/`, `data/`, `logs/`, model caches, transcripts and indexes must remain out of Git.
