# API and Auth Setup

[English](API_AUTH_SETUP.md) | [Русский](../ru/API_AUTH_SETUP.md)

This document covers authentication, authorization, and API usage for the MeetingAgent HTTP API.

---

## Current State

**The only fully operational access method is the machine Bearer token (`MEETINGAGENT_API_TOKEN`).**

Local login (`POST /auth/local/login`) works, but is only useful after a user account already exists in the database. First-admin bootstrap is **not yet implemented** — there is no way to create the first user through the API or any UI. Admin API and admin UI are not implemented. External providers (Yandex ID, Google, OIDC) are not implemented.

This means:

- For scripts, CI, automation, and service-to-service calls: use the Bearer token.
- For browser sessions: local login is available once a user record has been inserted directly into the SQLite auth database. This is a developer/admin workflow only.
- Public registration does not exist and is not planned for the MVP.

---

## Authentication Model

The API uses two principal types:

| Principal type | How to authenticate | CSRF required for writes |
|---|---|---|
| **machine** | `Authorization: Bearer <token>` | No |
| **user** (browser) | Session cookie `ma_session` | Yes (`X-CSRF-Token` header) |

### Machine Bearer Token

Set `MEETINGAGENT_API_TOKEN` in the environment (`.env` or system environment). The value must be a sufficiently long random string — at least 32 characters. All requests must include:

```
Authorization: Bearer <token>
```

If the header is present but the token does not match, the server returns `401`. If the header is absent, the request is treated as unauthenticated (most protected routes return `401`).

The machine principal has a fixed, narrowly-scoped permission set: it can read meetings, upload, start/cancel/read jobs, search, and chat. It cannot manage users, roles, settings, or delete meetings.

### Local Login (Browser Session)

```
POST /auth/local/login
Content-Type: application/json

{"email": "user@example.com", "password": "secret"}
```

On success the response sets two cookies:
- `ma_session` — HttpOnly, SameSite=Lax, Secure when HTTPS. Never readable by JavaScript.
- `ma_session_csrf` — non-HttpOnly. JavaScript must read this and send it as `X-CSRF-Token` for all write and action requests.

The response body also includes:
- `csrf_token` — same value as the CSRF cookie, for clients that prefer it from JSON.

On failure: `401 Unauthorized` with a generic message regardless of whether the email exists.

After login, call `GET /auth/me` to confirm the session and retrieve the user identity and roles.

### CSRF

All cookie-authenticated write and action requests (POST/PUT/DELETE and `/chat`) must include:

```
X-CSRF-Token: <csrf_token>
```

Machine Bearer requests are exempt from CSRF.

Missing or invalid CSRF token returns `403 Forbidden`.

### Logout

```
POST /auth/logout
X-CSRF-Token: <csrf_token>
```

Returns `204 No Content`. Clears both cookies and revokes the server-side session.

---

## RBAC

Three built-in roles:

| Role | Permissions |
|---|---|
| **viewer** | meetings.read, artifacts.read, transcripts.read, jobs.read, search.use, chat.use |
| **editor** | viewer + meetings.upload, meetings.edit, jobs.start, jobs.cancel, jobs.retry, artifacts.edit |
| **admin** | editor + users.manage, roles.manage, settings.manage, audit.read, meetings.delete, tokens.manage |

The machine principal has `meetings.upload`, `meetings.read`, `artifacts.read`, `transcripts.read`, `search.use`, `chat.use`, `jobs.start`, `jobs.cancel`, `jobs.retry`, `jobs.read`. It does not have `users.manage`, `roles.manage`, `settings.manage`, `tokens.manage`, or `meetings.delete`.

Unknown roles grant nothing.

---

## Full API Reference

All paths are relative to the API base URL (e.g. `http://127.0.0.1:8000`).

### Auth

| Method | Path | Auth required | Notes |
|---|---|---|---|
| POST | `/auth/local/login` | None | Returns session cookie + csrf_token |
| GET | `/auth/me` | Cookie session | Returns identity, roles |
| POST | `/auth/logout` | Cookie + CSRF | Revokes session |

### Meetings (read-only)

| Method | Path | Permission | Notes |
|---|---|---|---|
| GET | `/meetings` | meetings.read | Paginated list. Query params: `offset`, `limit` |
| GET | `/meetings/{id}` | meetings.read | Meeting card |
| GET | `/meetings/{id}/transcript` | transcripts.read | Transcript or `{"available": false}` |
| GET | `/meetings/{id}/artifacts` | artifacts.read | Artifact metadata list |
| GET | `/meetings/{id}/artifacts/{name}` | artifacts.read | Text artifact content. 413 if > limit. 415 for binary artifacts. |

Text artifact size limit: **10 MiB** (configurable via `meetings.max_text_artifact_bytes`). Binary artifacts return `415 Unsupported Media Type`.

### Ingest

| Method | Path | Permission | Notes |
|---|---|---|---|
| POST | `/meetings/ingest` | meetings.upload (write access) | Multipart upload. Returns 201 or 409 on sha256 dedup. |

### Job Pipeline

| Method | Path | Permission | Notes |
|---|---|---|---|
| POST | `/meetings/{id}/jobs/{stage}` | write access | Start a pipeline stage. Returns 202. |
| GET | `/meetings/{id}/jobs/{job_id}` | jobs.read | Job status |
| POST | `/meetings/{id}/jobs/{job_id}/cancel` | write access | Cancel a job |
| GET | `/jobs/active` | jobs.read | Currently running job or `{}` |

### Search and Chat

| Method | Path | Permission | Notes |
|---|---|---|---|
| POST | `/search` | search.use | RAG retrieval |
| POST | `/chat` | chat.use | Grounded answer with citations. Cookie callers need CSRF. |

### Health

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/health` | None | Service health check |

---

## HTTP Status Codes

| Code | Meaning |
|---|---|
| 200 | OK |
| 201 | Created (ingest) |
| 202 | Accepted (job started) |
| 204 | No Content (logout) |
| 400 | Bad Request (validation error) |
| 401 | Unauthorized — no credentials or invalid Bearer token |
| 403 | Forbidden — authenticated but insufficient permissions, or missing/invalid CSRF |
| 404 | Not Found |
| 409 | Conflict — duplicate file on ingest (sha256 match) |
| 413 | Payload Too Large — transcript or artifact exceeds byte limit |
| 415 | Unsupported Media Type — binary artifact requested as text |
| 422 | Unprocessable Entity — request body schema error |
| 429 | Too Many Requests — login throttle triggered; `Retry-After` header included |
| 500 | Internal Server Error |

---

## Login Throttling

Failed login attempts are counted per (sha256(email), client IP) pair. After `max_failures` failures in `window_seconds`, the endpoint returns `429 Too Many Requests` with a `Retry-After` header. The attempt that reaches the threshold itself receives 429.

The block clears on a successful login.

Configuration in `config.yaml`:

```yaml
auth:
  login_throttle:
    enabled: true
    max_failures: 5
    window_seconds: 300
    block_seconds: 900      # 15 minutes
    max_entries: 10000
    trusted_proxy_cidrs: [] # see Reverse Proxy section
```

To disable throttling (development only):

```yaml
auth:
  login_throttle:
    enabled: false
```

---

## Request Examples

### PowerShell — Machine Bearer

```powershell
$token = $env:MEETINGAGENT_API_TOKEN
$headers = @{ Authorization = "Bearer $token" }

# List meetings
Invoke-RestMethod http://127.0.0.1:8000/meetings -Headers $headers

# Get a meeting card
Invoke-RestMethod http://127.0.0.1:8000/meetings/2026-01-15__kickoff -Headers $headers

# Get transcript
Invoke-RestMethod http://127.0.0.1:8000/meetings/2026-01-15__kickoff/transcript -Headers $headers

# Ingest a meeting file
$form = @{
  file  = Get-Item "C:\recordings\meeting.mp4"
  title = "Kickoff Meeting"
  date  = "2026-01-15"
}
Invoke-RestMethod http://127.0.0.1:8000/meetings/ingest `
  -Method Post -Headers $headers -Form $form

# Start a transcription job
Invoke-RestMethod http://127.0.0.1:8000/meetings/2026-01-15__kickoff/jobs/transcribe `
  -Method Post -Headers $headers

# Search
$body = @{ query = "project risks" } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/search `
  -Method Post -Headers $headers `
  -ContentType "application/json" -Body $body
```

### curl — Machine Bearer

```bash
TOKEN="your-api-token"

# List meetings
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/meetings

# Get transcript
curl -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/meetings/2026-01-15__kickoff/transcript

# Ingest
curl -X POST http://127.0.0.1:8000/meetings/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/meeting.mp4" \
  -F "title=Kickoff Meeting" \
  -F "date=2026-01-15"

# Start job
curl -X POST http://127.0.0.1:8000/meetings/2026-01-15__kickoff/jobs/transcribe \
  -H "Authorization: Bearer $TOKEN"

# Search
curl -X POST http://127.0.0.1:8000/search \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "project risks"}'
```

### curl — Browser Session (Cookie + CSRF)

```bash
BASE=http://127.0.0.1:8000

# Login — save cookies to jar
curl -c cookies.txt -X POST "$BASE/auth/local/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"secret"}'
# Response includes csrf_token; save it.

CSRF="<csrf_token from login response>"

# Read (no CSRF needed for GET)
curl -b cookies.txt "$BASE/meetings"

# Write (CSRF required)
curl -b cookies.txt -X POST "$BASE/meetings/ingest" \
  -H "X-CSRF-Token: $CSRF" \
  -F "file=@meeting.mp4" -F "title=Test" -F "date=2026-01-15"

# Logout
curl -b cookies.txt -X POST "$BASE/auth/logout" \
  -H "X-CSRF-Token: $CSRF"
```

---

## Configuration Reference

`.env.example` / `.env`:

```ini
# Required for Bearer auth
MEETINGAGENT_API_TOKEN=change-this-to-a-long-random-secret

# API server port (Docker / docker compose)
MEETINGAGENT_API_PORT=8000
```

`config.yaml` (copy from `config.example.yaml`):

```yaml
auth:
  login_throttle:
    enabled: true
    max_failures: 5
    window_seconds: 300
    block_seconds: 900
    max_entries: 10000
    trusted_proxy_cidrs: []

meetings:
  max_text_artifact_bytes: 10485760   # 10 MiB
```

---

## HTTPS and Reverse Proxy

The API does not terminate TLS. Run behind a reverse proxy (nginx, Caddy, Traefik) for production.

When behind a proxy that sets `X-Forwarded-For`, configure `trusted_proxy_cidrs` so the API resolves the real client IP for login throttling:

```yaml
auth:
  login_throttle:
    trusted_proxy_cidrs:
      - "127.0.0.1/32"
      - "10.0.0.0/8"
```

The API resolves the real client IP by walking `X-Forwarded-For` right-to-left, skipping IPs that belong to trusted proxies. Only the first untrusted hop is used. Without `trusted_proxy_cidrs` (default empty), the direct peer IP is always used and `X-Forwarded-For` is ignored — this is the safe default for a directly-exposed host.

Session cookies are set with `Secure` only when the request arrives over HTTPS. Run behind HTTPS in production to enforce this.

---

## Secure Storage

| Item | Where to keep it | Never do |
|---|---|---|
| `MEETINGAGENT_API_TOKEN` | `.env` (not committed) or system env | Commit to Git |
| `config.yaml` | Local only, gitignored | Commit to Git |
| `data/auth.db` (auth SQLite) | Local only, gitignored | Commit to Git |
| `meetings/` | Local only, gitignored | Commit to Git |
| `logs/` | Local only, gitignored | Commit to Git |
| `data/` (indexes, chunks) | Local only, gitignored | Commit to Git |

Generate a strong token:

```powershell
# PowerShell
[System.Web.Security.Membership]::GeneratePassword(48, 8)
# or
-join ((48..122) | Get-Random -Count 48 | % {[char]$_})
```

```bash
# bash / Linux
openssl rand -hex 32
```

---

## Limitations and Roadmap

| Feature | Status |
|---|---|
| Machine Bearer token | **Working** |
| Local login (cookie session) | **Working** — requires existing user record |
| First-admin bootstrap | **Not implemented** |
| Admin user API | **Not implemented** |
| Admin UI | **Not implemented** |
| Yandex ID / Google / OIDC | **Not implemented** |
| Public registration | **Not planned for MVP** |

Next planned step: **MA-AUTH-BOOTSTRAP-ADMIN** — first-admin bootstrap and admin user API.
