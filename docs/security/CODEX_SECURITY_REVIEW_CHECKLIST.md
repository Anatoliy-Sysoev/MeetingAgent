# Codex Security Review Checklist

Use this checklist when Codex or another AI coding agent reviews security-sensitive MeetingAgent changes.

Security-sensitive changes include local file handling, transcript processing, API/auth, model providers, exports, Telegram/Web/API boundaries, Docker/runtime configuration, guardrails, and any code that can expose private project data.

## 1. Scope

- [ ] Identify changed files and classify the change: code, docs, config, test, runtime script, CI.
- [ ] Confirm the PR does not include private runtime folders: `data/`, `logs/`, `meetings/`, `vector_db/`, `watched_folder/`, model caches.
- [ ] Confirm no real customer documents, transcripts, meeting recordings, indexes, eval outputs, or local config files are committed.
- [ ] Confirm new public examples are synthetic or anonymized and manually reviewed.

## 2. File Handling And Path Traversal

- [ ] All user-controlled paths are resolved relative to an expected root.
- [ ] Absolute paths and `..` traversal are rejected for artifact access.
- [ ] File serving does not follow symlinks outside the allowed root.
- [ ] Error responses do not expose local absolute paths.
- [ ] Recursive delete/move logic is not added without explicit root validation.

## 3. Transcript Privacy

- [ ] Real transcripts and meeting cards remain ignored runtime data.
- [ ] Public fixtures use synthetic data or output from `scripts/43_anonymize_transcript.py` followed by manual review.
- [ ] Speaker names, organizations, paths, URLs, emails, phones and internal identifiers are removed from public artifacts.
- [ ] Private mapping files such as `*.private.json` are not committed.
- [ ] Transcript-derived artifacts preserve source refs without leaking private paths.

## 4. API Keys And Secrets

- [ ] No `.env`, `config.yaml`, tokens, API keys, session secrets, Telegram tokens or provider credentials are staged.
- [ ] `.env.example` contains placeholders only.
- [ ] Validation errors and logs do not echo passwords, tokens, CSRF values or Authorization headers.
- [ ] New config values have safe defaults and documented environment variables.

## 5. Model Providers

- [ ] The PR states whether text is sent to local-only or hosted providers.
- [ ] Hosted provider usage is opt-in and documented.
- [ ] Local default models remain consistent with docs/config.
- [ ] Provider errors fail closed or degrade to documented fallback without exposing prompts or source text.
- [ ] Prompt construction treats retrieved/transcript content as untrusted data.

## 6. Exports And Artifacts

- [ ] Markdown/JSON/JSONL/SRT/VTT/DOCX exports do not include hidden private paths or raw prompts.
- [ ] Artifact manifest URLs are served by existing safe routes.
- [ ] Structured artifacts include source refs/timestamps for auditability.
- [ ] Generated reports under `eval/reports/` or local output folders are treated as runtime data unless explicitly curated.

## 7. Telegram, Web UI, And API Boundaries

- [ ] Browser write requests use CSRF when authenticated by cookie.
- [ ] Machine/API token flows remain separate from browser sessions.
- [ ] UI code uses DOM APIs/textContent/dataset/addEventListener, not inline handlers or unsafe HTML insertion.
- [ ] Telegram adapter does not bypass project guardrails or auth assumptions.
- [ ] Public API responses do not expose local filesystem paths, raw backend exceptions, prompts or internal credentials.

## 8. Guardrails And Retrieval

- [ ] Out-of-project and harmful requests remain blocked before retrieval/LLM.
- [ ] In-project project-security questions are not accidentally refused.
- [ ] Retrieval diagnostics distinguish guard blocking from retrieval/model failures.
- [ ] Citations are limited to sources actually returned/used by the answer.
- [ ] Meeting-scoped retrieval cannot leak chunks from another meeting.

## 9. Verification

Run the narrowest relevant tests and, for substantial changes, full tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
git diff --check
```

For docs-only changes, at minimum run:

```powershell
git diff --check
```

Before merge:

- [ ] `git status --short` contains no private/runtime files.
- [ ] PR description lists security impact and verification commands.
- [ ] `docs/context.md` and `docs/todo.md` are current when behavior or backlog status changes.

---

# Чеклист Security Review Для Codex

Используйте этот чеклист, когда Codex или другой AI coding agent проверяет security-sensitive изменения MeetingAgent.

Security-sensitive изменения: локальные файлы, транскрипты, API/auth, model providers, exports, Telegram/Web/API границы, Docker/runtime config, guardrails и любой код, который может раскрыть приватные проектные данные.

## 1. Scope

- [ ] Определить изменённые файлы и тип изменения: code, docs, config, test, runtime script, CI.
- [ ] Проверить, что PR не включает runtime folders: `data/`, `logs/`, `meetings/`, `vector_db/`, `watched_folder/`, model caches.
- [ ] Проверить, что не закоммичены реальные customer documents, transcripts, recordings, indexes, eval outputs или local configs.
- [ ] Проверить, что public examples синтетические или анонимизированные и прошли ручной review.

## 2. File Handling И Path Traversal

- [ ] Все user-controlled paths резолвятся внутри ожидаемого root.
- [ ] Absolute paths и `..` traversal отклоняются для artifact access.
- [ ] File serving не следует за symlink за пределы allowed root.
- [ ] Error responses не раскрывают local absolute paths.
- [ ] Recursive delete/move не добавлен без явной root validation.

## 3. Transcript Privacy

- [ ] Real transcripts и meeting cards остаются ignored runtime data.
- [ ] Public fixtures используют synthetic data или output `scripts/43_anonymize_transcript.py` после manual review.
- [ ] Speaker names, organizations, paths, URLs, emails, phones и internal identifiers удалены из public artifacts.
- [ ] Private mapping files типа `*.private.json` не закоммичены.
- [ ] Transcript-derived artifacts сохраняют source refs без private paths.

## 4. API Keys И Secrets

- [ ] Нет staged `.env`, `config.yaml`, tokens, API keys, session secrets, Telegram tokens или provider credentials.
- [ ] `.env.example` содержит только placeholders.
- [ ] Validation errors и logs не возвращают passwords, tokens, CSRF values или Authorization headers.
- [ ] Новые config values имеют safe defaults и documented environment variables.

## 5. Model Providers

- [ ] PR явно говорит, отправляется ли текст в local-only или hosted providers.
- [ ] Hosted provider usage opt-in и documented.
- [ ] Local default models синхронизированы с docs/config.
- [ ] Provider errors fail closed или degrade в documented fallback без раскрытия prompts/source text.
- [ ] Prompt construction трактует retrieved/transcript content как untrusted data.

## 6. Exports И Artifacts

- [ ] Markdown/JSON/JSONL/SRT/VTT/DOCX exports не включают hidden private paths или raw prompts.
- [ ] Artifact manifest URLs обслуживаются существующими safe routes.
- [ ] Structured artifacts содержат source refs/timestamps для auditability.
- [ ] Generated reports под `eval/reports/` или local output folders считаются runtime data, если не curated вручную.

## 7. Telegram, Web UI И API Boundaries

- [ ] Browser write requests используют CSRF при cookie-auth.
- [ ] Machine/API token flows отделены от browser sessions.
- [ ] UI использует DOM APIs/textContent/dataset/addEventListener, не inline handlers и не unsafe HTML insertion.
- [ ] Telegram adapter не обходит project guardrails или auth assumptions.
- [ ] Public API responses не раскрывают local filesystem paths, raw backend exceptions, prompts или internal credentials.

## 8. Guardrails И Retrieval

- [ ] Out-of-project и harmful requests блокируются до retrieval/LLM.
- [ ] In-project project-security questions не уходят в false refuse.
- [ ] Retrieval diagnostics различают guard blocking и retrieval/model failures.
- [ ] Citations ограничены источниками, которые ответ реально вернул/использовал.
- [ ] Meeting-scoped retrieval не возвращает chunks другой встречи.

## 9. Verification

Для существенных изменений:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
git diff --check
```

Для docs-only изменений минимум:

```powershell
git diff --check
```

Перед merge:

- [ ] `git status --short` не содержит private/runtime files.
- [ ] PR description перечисляет security impact и verification commands.
- [ ] `docs/context.md` и `docs/todo.md` обновлены, если меняется behavior или backlog status.
