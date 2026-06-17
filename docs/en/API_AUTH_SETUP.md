# API and Auth Setup

[English](API_AUTH_SETUP.md) | [Русский](../ru/API_AUTH_SETUP.md)

This document covers authentication, authorization, and API usage for the MeetingAgent HTTP API.

---

## Current State

**The machine Bearer token (`MEETINGAGENT_API_TOKEN`) is the primary access method for scripts and automation. Local login with cookie sessions is fully operational; first-admin bootstrap and admin user management are now implemented.**

This means:

- For scripts, CI, automation, and service-to-service calls: use the Bearer token.
- For browser sessions: use `POST /admin/bootstrap` to create the first admin, then `POST /auth/local/login`.
- Public registration does not exist and is not planned for the MVP.
- Admin UI is not implemented — manage users via the admin API.

### Web UI note

The built-in web UI (`/` and `/ui`) sends `/chat` requests without any credentials or CSRF token. After RBAC was enabled, the UI's chat feature returns an auth error (`401`). The UI is not integrated with login or Bearer auth. Use the machine Bearer token directly (curl / PowerShell / scripts) until a UI auth integration is implemented.

---

## Authentication Model

The API uses two principal types:

| Principal type | How to authenticate | CSRF required for write/action requests |
|---|---|---|
| **machine** | `Authorization: Bearer <token>` | No |
| **user** (browser) | Session cookie `ma_session` | Yes (`X-CSRF-Token` header) |

### Machine Bearer Token

Set `MEETINGAGENT_API_TOKEN` in the environment (`.env` or system environment). The value must be a sufficiently long random string — at least 32 characters. All requests must include:

```
Authorization: Bearer <token>
```

If the header is present but the token does not match, the server returns `401`. If no `Authorization` header is present at all, the server falls back to checking the session cookie; if no cookie is present either, the request is unauthenticated (most protected routes return `401`).

**Important**: any `Authorization` header that is present but malformed or carries a wrong token returns `401` immediately — there is no silent fallback to the cookie in that case.

The machine principal has a fixed, narrowly-scoped permission set: it can read meetings, upload, start/cancel/read jobs, search, and chat. It cannot manage users, roles, settings, or delete meetings.

### Local Login (Browser Session)

```
POST /auth/local/login
Content-Type: application/json

{"email": "user@example.com", "password": "secret"}
```

Requires a pre-provisioned active user with a local credential and assigned roles. On success the response sets two cookies:
- `ma_session` — HttpOnly, SameSite=Lax, Secure when HTTPS. Never readable by JavaScript.
- `ma_session_csrf` — non-HttpOnly. JavaScript must read this value and send it as `X-CSRF-Token` for all write and action requests.

The response body also includes:
- `csrf_token` — same value as the CSRF cookie, for clients that prefer it from JSON.

On failure: `401 Unauthorized` with a generic message regardless of whether the email exists.

After login, call `GET /auth/me` to confirm the session and retrieve the user identity and roles. The actual access level depends on which roles were assigned to the user.

### CSRF

Cookie-authenticated requests to the following write and action endpoints require an `X-CSRF-Token` header:

- `POST /meetings/ingest`
- `POST /meetings/{id}/jobs/{stage}`
- `POST /meetings/{id}/jobs/{job_id}/cancel`
- `POST /chat`
- `POST /auth/logout`
- `POST /admin/users`
- `PATCH /admin/users/{user_id}`
- `POST /admin/users/{user_id}/disable`
- `POST /admin/users/{user_id}/enable`

```
X-CSRF-Token: <csrf_token>
```

Read endpoints (all `GET` routes, `POST /search`, `POST /auth/local/login`) do **not** require CSRF.

Machine Bearer requests are exempt from CSRF on all routes.

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

| Method | Path | Auth required | CSRF | Notes |
|---|---|---|---|---|
| POST | `/auth/local/login` | None | No | Returns session cookie + csrf_token |
| GET | `/auth/me` | Cookie session | No | Returns identity, roles |
| POST | `/auth/logout` | Cookie + CSRF | **Yes** | Revokes session |

### Meetings (read-only)

| Method | Path | Permission | CSRF | Notes |
|---|---|---|---|---|
| GET | `/meetings` | meetings.read | No | Paginated list. Query params: `offset`, `limit` |
| GET | `/meetings/{id}` | meetings.read | No | Meeting card |
| GET | `/meetings/{id}/transcript` | transcripts.read | No | Transcript or `{"available": false}` |
| GET | `/meetings/{id}/artifacts` | artifacts.read | No | Artifact metadata list |
| GET | `/meetings/{id}/artifacts/{name}` | artifacts.read | No | Text artifact content. 413 if > limit. 415 for binary. |

Text artifact size limit: **10 MiB** (configurable via `meetings.max_text_artifact_bytes`). Binary artifacts return `415 Unsupported Media Type`.

### Ingest

| Method | Path | Permission | CSRF | Notes |
|---|---|---|---|---|
| POST | `/meetings/ingest` | meetings.upload | **Yes** (cookie) | Multipart upload. 201 or 409 on sha256 dedup. |

### Job Pipeline

| Method | Path | Permission | CSRF | Notes |
|---|---|---|---|---|
| POST | `/meetings/{id}/jobs/{stage}` | write access | **Yes** (cookie) | Start pipeline stage. Returns 202. |
| GET | `/meetings/{id}/jobs/{job_id}` | jobs.read | No | Job status |
| POST | `/meetings/{id}/jobs/{job_id}/cancel` | write access | **Yes** (cookie) | Cancel a job |
| GET | `/jobs/active` | jobs.read | No | Currently running job or `{}` |

### Search and Chat

| Method | Path | Permission | CSRF | Notes |
|---|---|---|---|---|
| POST | `/search` | search.use | No | RAG retrieval. No CSRF even for cookie callers. |
| POST | `/chat` | chat.use | **Yes** (cookie) | Grounded answer with citations. Machine Bearer exempt. |

### Admin

#### Bootstrap

`POST /admin/bootstrap` creates the first admin user. It returns `409` if any user already exists.

**Bootstrap safety** — the endpoint enforces a locality policy to protect empty deployments:

| Request origin | Default behavior | How to override |
|---|---|---|
| **Localhost** (127.0.0.1, ::1) | Allowed without any secret | No configuration needed |
| **Non-local** (LAN, container, remote) | **Blocked** (returns 403) | Set `allow_remote=true` + `secret` (see below) |

For non-local bootstrap, the operator must explicitly enable it and provide a strong one-time secret:

1. Set environment variables (recommended) or `auth.bootstrap` in `config.yaml`:
   ```
   MEETINGAGENT_BOOTSTRAP_ALLOW_REMOTE=true
   MEETINGAGENT_BOOTSTRAP_SECRET=<strong-random-value>
   ```
   The secret must be at least 32 characters. Generate one:
   `python -c "import secrets; print(secrets.token_urlsafe(48))"`

2. Send the secret in the `X-Bootstrap-Token` header:
   ```
   POST /admin/bootstrap
   X-Bootstrap-Token: <secret>
   Content-Type: application/json

   {"email": "admin@example.com", "password": "..."}
   ```

3. After the first admin is created, **remove or unset** `MEETINGAGENT_BOOTSTRAP_ALLOW_REMOTE` and `MEETINGAGENT_BOOTSTRAP_SECRET`. The secret is not needed again.

The secret is never logged, audited, returned, or stored. IP detection uses the direct peer address only — `X-Forwarded-For` is not trusted for client IP identification. If any forwarded proxy headers are present the local bypass is suppressed: the request must provide a valid `X-Bootstrap-Token`.

Bootstrap endpoints:

| Method | Path | Auth | CSRF | Notes |
|---|---|---|---|---|
| POST | `/admin/bootstrap` | None (+ locality check) | No | Create first admin. 409 if users exist. 403 if blocked by policy. |

User management (requires `users.manage` — admin browser cookie session only):

| Method | Path | Auth | CSRF | Notes |
|---|---|---|---|---|
| GET | `/admin/users` | users.manage | No | List users. Query: `offset`, `limit`. |
| GET | `/admin/users/{user_id}` | users.manage | No | Get user. |
| POST | `/admin/users` | users.manage | **Yes** (cookie) | Create user. 409 on duplicate email. 422 on unknown role. |
| PATCH | `/admin/users/{user_id}` | users.manage | **Yes** (cookie) | Update display name and/or roles. 409 if last admin demoted. |
| POST | `/admin/users/{user_id}/disable` | users.manage | **Yes** (cookie) | Disable user. 409 if last active admin. |
| POST | `/admin/users/{user_id}/enable` | users.manage | **Yes** (cookie) | Re-enable disabled user. |

Machine Bearer tokens do **not** have `users.manage` and receive `403` on all user-management routes.

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
| 401 | Unauthorized — no credentials, invalid Bearer token, or expired session |
| 403 | Forbidden — authenticated but insufficient permissions, or missing/invalid CSRF |
| 404 | Not Found |
| 409 | Conflict — duplicate file on ingest (sha256 match); bootstrap rejected (users exist); last-admin protection |
| 403 | Also: bootstrap blocked for non-local request without `allow_remote`; bootstrap token missing or invalid |
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

# Get artifact content
Invoke-RestMethod `
  http://127.0.0.1:8000/meetings/2026-01-15__kickoff/artifacts/memo `
  -Headers $headers

# Ingest a meeting file
$form = @{
  file  = Get-Item "C:\recordings\meeting.mp4"
  title = "Kickoff Meeting"
  date  = "2026-01-15"
}
Invoke-RestMethod http://127.0.0.1:8000/meetings/ingest `
  -Method Post -Headers $headers -Form $form

# Start a transcription job
Invoke-RestMethod `
  http://127.0.0.1:8000/meetings/2026-01-15__kickoff/jobs/transcribe `
  -Method Post -Headers $headers

# Get job status
Invoke-RestMethod `
  http://127.0.0.1:8000/meetings/2026-01-15__kickoff/jobs/<job_id> `
  -Headers $headers

# Cancel a job
Invoke-RestMethod `
  http://127.0.0.1:8000/meetings/2026-01-15__kickoff/jobs/<job_id>/cancel `
  -Method Post -Headers $headers

# Active job
Invoke-RestMethod http://127.0.0.1:8000/jobs/active -Headers $headers

# Search
$body = @{ query = "project risks" } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/search `
  -Method Post -Headers $headers `
  -ContentType "application/json" -Body $body

# Chat
$body = @{ query = "summarise the meeting decisions" } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/chat `
  -Method Post -Headers $headers `
  -ContentType "application/json" -Body $body
```

### PowerShell — Browser Session (Cookie + CSRF)

```powershell
$base = "http://127.0.0.1:8000"
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession

# Login
$loginBody = @{ email = "user@example.com"; password = "secret" } | ConvertTo-Json
$loginResp = Invoke-RestMethod "$base/auth/local/login" `
  -Method Post -WebSession $session `
  -ContentType "application/json" -Body $loginBody
$csrf = $loginResp.csrf_token

# Read (no CSRF needed for GET)
Invoke-RestMethod "$base/meetings" -WebSession $session

# Write (CSRF required)
$form = @{
  file  = Get-Item "C:\recordings\meeting.mp4"
  title = "Kickoff Meeting"
  date  = "2026-01-15"
}
Invoke-RestMethod "$base/meetings/ingest" `
  -Method Post -WebSession $session `
  -Headers @{ "X-CSRF-Token" = $csrf } -Form $form

# Chat (CSRF required for cookie callers)
$body = @{ query = "what were the decisions?" } | ConvertTo-Json
Invoke-RestMethod "$base/chat" `
  -Method Post -WebSession $session `
  -Headers @{ "X-CSRF-Token" = $csrf } `
  -ContentType "application/json" -Body $body

# Logout
Invoke-RestMethod "$base/auth/logout" `
  -Method Post -WebSession $session `
  -Headers @{ "X-CSRF-Token" = $csrf }
```

### curl — Machine Bearer

```bash
TOKEN="your-api-token"

# List meetings
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/meetings

# Get transcript
curl -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/meetings/2026-01-15__kickoff/transcript

# Get artifact
curl -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/meetings/2026-01-15__kickoff/artifacts/memo

# Ingest
curl -X POST http://127.0.0.1:8000/meetings/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/meeting.mp4" \
  -F "title=Kickoff Meeting" \
  -F "date=2026-01-15"

# Start job
curl -X POST http://127.0.0.1:8000/meetings/2026-01-15__kickoff/jobs/transcribe \
  -H "Authorization: Bearer $TOKEN"

# Job status
curl -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/meetings/2026-01-15__kickoff/jobs/<job_id>

# Cancel job
curl -X POST http://127.0.0.1:8000/meetings/2026-01-15__kickoff/jobs/<job_id>/cancel \
  -H "Authorization: Bearer $TOKEN"

# Search
curl -X POST http://127.0.0.1:8000/search \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "project risks"}'

# Chat
curl -X POST http://127.0.0.1:8000/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "summarise the meeting decisions"}'
```

### curl — Browser Session (Cookie + CSRF)

```bash
BASE=http://127.0.0.1:8000

# Login — save cookies to jar; extract csrf_token from response
RESP=$(curl -s -c cookies.txt -X POST "$BASE/auth/local/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"secret"}')
CSRF=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['csrf_token'])")

# Read (no CSRF needed for GET)
curl -b cookies.txt "$BASE/meetings"

# Write (CSRF required)
curl -b cookies.txt -X POST "$BASE/meetings/ingest" \
  -H "X-CSRF-Token: $CSRF" \
  -F "file=@meeting.mp4" -F "title=Test" -F "date=2026-01-15"

# Chat (CSRF required for cookie callers)
curl -b cookies.txt -X POST "$BASE/chat" \
  -H "X-CSRF-Token: $CSRF" \
  -H "Content-Type: application/json" \
  -d '{"query": "what were the decisions?"}'

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
paths:
  auth_db: "data/meetingagent/auth.db"   # default; can be overridden

auth:
  session_ttl_seconds: 86400             # 24 h default
  cookie_name: "ma_session"              # default
  cookie_secure: "auto"                  # auto|true|false; auto=Secure when HTTPS

  # Bootstrap safety (optional — only needed for non-local first-run).
  # bootstrap:
  #   allow_remote: false                # default; set true only for non-local bootstrap
  #   secret: ""                         # required when allow_remote: true

  login_throttle:
    enabled: true
    max_failures: 5
    window_seconds: 300
    block_seconds: 900
    max_entries: 10000
    trusted_proxy_cidrs: []

meetings:
  max_text_artifact_bytes: 10485760      # 10 MiB
```

Bootstrap environment variables (override config.yaml):

| Variable | Values | Notes |
|---|---|---|
| `MEETINGAGENT_BOOTSTRAP_ALLOW_REMOTE` | `true` / `false` | Default: `false`. Set `true` to allow non-local bootstrap. |
| `MEETINGAGENT_BOOTSTRAP_SECRET` | string, min 32 chars | Required when `allow_remote` is `true`. Never commit. |

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

Session cookies are set with `Secure` only when the request arrives over HTTPS (`cookie_secure: auto`). Set `cookie_secure: true` to force `Secure` regardless, or `false` to disable it (development only). Run behind HTTPS in production.

---

## Secure Storage

| Item | Where to keep it | Never do |
|---|---|---|
| `MEETINGAGENT_API_TOKEN` | `.env` (not committed) or system env | Commit to Git |
| `config.yaml` | Local only, gitignored | Commit to Git |
| `data/meetingagent/auth.db` (auth SQLite) | Local only, gitignored | Commit to Git |
| `meetings/` | Local only, gitignored | Commit to Git |
| `logs/` | Local only, gitignored | Commit to Git |
| `data/` (indexes, chunks) | Local only, gitignored | Commit to Git |

Generate a strong token:

```powershell
# PowerShell (cross-platform via Python — no special-char issues)
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

```bash
# bash / Linux / macOS
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
# or
openssl rand -hex 32
```

---

## Limitations and Roadmap

| Feature | Status |
|---|---|
| Machine Bearer token | **Working** |
| Local login (cookie session) | **Working** |
| First-admin bootstrap (`POST /admin/bootstrap`) | **Working** |
| Admin user API (`/admin/users`) | **Working** |
| Deployment safety validation | **Working** — `MEETINGAGENT_DEPLOYMENT_MODE`, startup validator, `GET /admin/security/status` |
| Admin UI | **Not implemented** — use the admin API directly |
| Web UI chat (browser) | **Broken** — UI sends no credentials; returns 401 after RBAC enabled |
| Yandex ID / Google / OIDC | **Not implemented** |
| Public registration | **Not planned for MVP** |
| Per-user API tokens | **Not implemented** |
| Password reset | **Not implemented** |

---

## Deployment Safety

### Deployment mode

Set `MEETINGAGENT_DEPLOYMENT_MODE` to control startup safety validation:

| Mode | Description |
|---|---|
| `local` (default) | Local development. Weak config produces **warnings** but does not block startup. |
| `self_hosted` | LAN or internet exposure. Missing/weak required settings produce **errors** and **abort startup**. |

```bash
# .env — self-hosted deployment
MEETINGAGENT_DEPLOYMENT_MODE=self_hosted
MEETINGAGENT_API_TOKEN=<generate with: python -c "import secrets; print(secrets.token_urlsafe(48))">
```

### What is validated at startup

The validator (`src/asu_june_bot/auth/deployment_safety.py`) checks:

| Finding code | Checked | self_hosted severity |
|---|---|---|
| `deployment_mode_unknown` | Unknown value for `MEETINGAGENT_DEPLOYMENT_MODE` | error |
| `machine_token_missing` | `MEETINGAGENT_API_TOKEN` not set | error |
| `machine_token_weak` | Token is a placeholder or shorter than 32 characters | error |
| `session_cookie_insecure` | `auth.cookie_secure = false` in config | error |
| `cors_wildcard_self_hosted` | No `security.allowed_hosts` or `security.allowed_origins` configured | warning |
| `bootstrap_policy_unsafe` | `allow_remote=true` without a strong bootstrap secret | error |

In `local` mode, the same checks produce `warning` or `info` findings and never abort startup.

### Self-hosted deployment checklist

1. Set `MEETINGAGENT_DEPLOYMENT_MODE=self_hosted` in `.env`.
2. Set a strong machine/API token: `MEETINGAGENT_API_TOKEN=<random ≥ 32 chars>`.
3. Set `auth.cookie_secure: auto` or `true` in `config.yaml` (never `false`).
4. Configure `security.allowed_hosts` / `security.allowed_origins` in `config.yaml`, or ensure your reverse proxy enforces host/origin restrictions.
5. Use HTTPS or a trusted reverse proxy for all browser access.
6. Run first-admin bootstrap through the local-only path or use `MEETINGAGENT_BOOTSTRAP_SECRET`.
7. Confirm `.env` is not committed to version control (it is in `.gitignore`).
8. Run `pytest tests/asu_june_bot/auth -q` to confirm safety tests pass.

### Admin security status endpoint

```
GET /admin/security/status
```

Requires an admin browser session (`users.manage` permission). Machine Bearer tokens are forbidden for this endpoint.

Returns deployment mode and redacted findings. **Never** includes raw token values, token hashes, session IDs, or filesystem paths.

```json
{
  "deployment_mode": "self_hosted",
  "findings": [
    {
      "code": "cors_wildcard_self_hosted",
      "severity": "warning",
      "message": "No security.allowed_hosts or security.allowed_origins are configured...",
      "setting": "security.allowed_hosts / security.allowed_origins"
    }
  ],
  "error_count": 0,
  "warning_count": 1
}
```

### Principal types and what they can access

- **Machine Bearer token** (`MEETINGAGENT_API_TOKEN`) — intended for scripts, CI, and service-to-service calls. Not a browser admin password. Machine tokens cannot manage browser users (`/admin/users`, `/admin/security/status`).
- **Browser session** (`ma_session` cookie) — for human operators using the web UI. State-changing requests require a CSRF token (`X-CSRF-Token` header).

These are separate principals. A valid session cookie does **not** compensate for a wrong Bearer token — invalid supplied credentials always return 401.

### Cookie and session security

| Property | Value |
|---|---|
| Cookie name | `ma_session` (configurable) |
| HttpOnly | Yes — JavaScript cannot read the session cookie |
| SameSite | `Lax` |
| Secure flag | Controlled by `auth.cookie_secure` (`auto` / `true` / `false`; default `auto`) |
| Session TTL | 24 hours (configurable via `auth.session_ttl_seconds`) |
| Storage | Server-side (SQLite); token hash only — plaintext token never stored |
| CSRF | Non-HttpOnly `ma_session_csrf` cookie; value sent as `X-CSRF-Token` header |

### Host and origin controls

MeetingAgent does not include built-in CORS or TrustedHost middleware. For self-hosted deployments, host/origin enforcement must be provided by the reverse proxy (nginx, Caddy, etc.) or load balancer in front of the app.

To suppress the `cors_wildcard_self_hosted` warning, configure explicit lists in `config.yaml`:

```yaml
security:
  allowed_hosts:
    - meetingagent.internal
  allowed_origins:
    - https://meetingagent.internal
```

These values are currently used only for the safety validator finding. Middleware enforcement is a future roadmap item.
