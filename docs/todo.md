# Todo

Обновлено: 2026-07-02.

## Done

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

## Active / Next

- [ ] MA-MEETING-ARTIFACT-CONTRACT (#119): stable artifact manifest — branch 119-meeting-artifact-contract (awaiting review).
- [ ] MA-MEETING-ERRORS-AND-RETRY (#120): product-grade stage errors, retry, and resume.
- [ ] MA-MEETING-WORKSPACE-FLOW (#121): end-to-end upload, run, monitor, and review UX.

## Meeting Product Backlog

- [ ] MA-SPEAKER-MAPPING-UI (#122): map diarized `SPEAKER_XX` labels to names and roles.
- [ ] MA-MEETING-STRUCTURED-ARTIFACTS-V2 (#123): source-grounded summary, protocol, decisions, tasks, risks and open questions.
- [ ] MA-MEETING-PACKAGING-LOCAL (#124): local all-in-one runbook and Docker profile.
- [ ] MA-MEETING-QA-SEGMENT-CITATIONS (#126): map meeting Q&A citations to transcript segments.
- [ ] Add anonymization pipeline for sensitive transcripts (#22).
- [ ] Add evaluation benchmark for meeting summaries (#24).

## Project Knowledge Bot / Guard / Auth Backlog

- [ ] MA-GUARD-PURE-DECISION-API (#106): deterministic guard decision API for regression tests.
- [ ] MA-ADR-AUTH-PROVIDERS (#39): decide provider evolution, per-user tokens, OIDC/local provider roadmap.
- [ ] MA-ADMIN-CONSOLE (#40): define/implement admin UI for users, roles, settings, jobs, audit and health.
- [ ] MA-PRODUCT-SPLIT-PHASE-1 (#125): extract shared utilities before separating Project Knowledge Bot.

## Documentation / OSS Backlog

- [ ] Add public sample meeting dataset (#19).
- [ ] Add transcript-to-protocol CLI quickstart (#20).
- [ ] Add Codex security review checklist (#21).
- [ ] Add release workflow and changelog automation (#23).
- [ ] Improve English/Russian documentation parity (#25).
- [ ] Add GitHub Pages documentation site (#26).

## Operating Rules

- Public Git must not include real transcripts, customer documents, runtime meeting cards, indexes, caches, logs, local configs or secrets.
- Long offline ASR jobs must run as background/status workflows, not short shell/API timeouts.
- GigaAM remains an optional isolated local runtime; do not commit GigaAM venv/cache/chunks/raw outputs.
- `data/meeting_embeddings_cache.jsonl`, `data/meeting_chunks.jsonl`, private review labels and real eval outputs are runtime data.
