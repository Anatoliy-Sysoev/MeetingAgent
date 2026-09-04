# ADR-0039: Auth Providers, Local RBAC, And Machine Fallback

Status: accepted.

Date: 2026-07-07.

Issue: #39.

## Context

MeetingAgent is local-first, but it now has two different access patterns:

- browser users working through Web UI and Workspace;
- scripts, CLI, Telegram adapter and automation calling HTTP APIs directly.

The current implementation already provides local users, local sessions,
RBAC, CSRF, bootstrap-admin flow and a machine Bearer token.  The next
architecture decision is how external browser identity providers should fit
without weakening local authorization or machine automation.

ADR-0001-style simple token access remains valid for machine/API usage only.
It is not the browser-user authentication model.

## Decision

MeetingAgent will keep local RBAC as the authoritative authorization layer.
External providers authenticate identity only; they do not directly grant
`editor` or `admin` permissions.

The target browser provider architecture is provider-agnostic OAuth/OIDC
adapters.  The first planned external provider is Yandex ID.  Future providers
may include Telegram, Google, Microsoft Entra and Keycloak.

Current local login remains supported for local/self-hosted MVP operation and
for environments where an external provider is not configured.

Machine/API fallback remains separate:

- transport: `Authorization: Bearer <MEETINGAGENT_API_TOKEN>`;
- purpose: CLI, automation, local scripts, Telegram adapter and tests;
- permissions: narrowly scoped operational API access;
- not a browser admin credential by default.

## Authentication vs Authorization

Authentication answers: who is this principal?

Authorization answers: what can this principal do in MeetingAgent?

Provider identity must be mapped into a local MeetingAgent user record before
it can receive roles.  Provider email or subject is not enough to infer admin
rights.

Local roles remain:

| Role | Intent |
|---|---|
| `viewer` | Read meetings, transcripts, artifacts, search and chat. |
| `editor` | `viewer` plus ingest/upload, start/cancel/retry jobs, edit meeting labels/mapping/artifacts. |
| `admin` | `editor` plus users, roles, settings, tokens, audit, diagnostics and destructive admin actions. |
| `machine` | Non-browser API principal for scripts and automation. |

Default browser role for an allowed external identity is `viewer`.

## Provider Adapter Contract

Planned route shape:

```text
GET /auth/{provider}/login
GET /auth/{provider}/callback
POST /auth/logout
GET /auth/me
```

MVP provider id:

```text
yandex
```

Planned future provider ids:

```text
telegram
google
microsoft_entra
keycloak
```

Provider adapters must normalize external identity into:

```json
{
  "provider": "yandex",
  "subject": "provider-subject-id",
  "email": "user@example.com",
  "email_verified": true,
  "display_name": "User Name"
}
```

After callback, MeetingAgent creates its own local HttpOnly session cookie.
External OAuth access tokens must not be stored in browser localStorage or
sessionStorage.

## Local Mapping

MVP mapping may use local DB records plus optional config/env allowlists.
Do not commit real values.

Suggested future configuration:

```text
MEETINGAGENT_ALLOWED_EMAILS=...
MEETINGAGENT_EDITOR_EMAILS=...
MEETINGAGENT_ADMIN_EMAILS=...

YANDEX_CLIENT_ID=...
YANDEX_CLIENT_SECRET=...
YANDEX_REDIRECT_URI=...
```

If an external identity is missing an allowed email and no provider-subject
allowlist is configured, browser access is denied.

## Machine/API Fallback

Machine Bearer token remains independent from browser sessions.

Rules:

- invalid Bearer token returns `401` and does not silently fall back to cookies;
- machine principal is not an admin UI identity;
- machine principal does not get `users.manage`, `roles.manage`,
  `settings.manage`, `tokens.manage` or `meetings.delete` by default;
- machine token must be strong and never committed.

## Permission Matrix

| Capability | viewer | editor | admin | machine |
|---|---:|---:|---:|---:|
| Browser login | yes | yes | yes | no |
| View meetings/transcripts/artifacts | yes | yes | yes | yes |
| Search/chat | yes | yes | yes | yes |
| Upload/ingest meeting | no | yes | yes | yes |
| Start/cancel/retry jobs | no | yes | yes | yes |
| Edit meeting metadata/speaker mapping/artifacts | no | yes | yes | no by default |
| Delete/archive meeting | no | no by default | yes | no by default |
| Manage users/roles | no | no | yes | no |
| Manage auth/settings/tokens | no | no | yes | no |
| View audit/log diagnostics | no | limited | yes | no by default |

## Security Requirements

- OAuth flow must use `state` protection.
- Prefer PKCE where provider supports it.
- Request minimal scopes.
- MeetingAgent-owned session cookie must be HttpOnly.
- Secure cookies must be enabled for HTTPS deployments.
- SameSite=Lax remains the default.
- CSRF remains required for cookie-authenticated write/action routes.
- Raw OAuth tokens and machine tokens must never be exposed through UI/API.
- Audit events must record role changes and admin actions.

## Impact

For ingest/jobs:

- browser users require local `editor` or `admin`;
- machine callers may use the Bearer token.

For admin console:

- browser user must have local `admin`;
- machine token must not grant admin UI access by default.

For future OIDC/Yandex implementation:

- add provider adapter behind the generic route shape;
- map provider identity to local user;
- keep RBAC checks unchanged.

## Consequences

Positive:

- Browser auth can evolve without rewriting product authorization.
- CLI/automation remains stable.
- Admin rights stay explicit and local.

Tradeoffs:

- Yandex ID requires configuration and callback handling in a future task.
- External provider identity lifecycle must be reconciled with local users.
- Per-user API tokens remain a separate future decision.

## Current Implementation Status

Implemented now:

- local users;
- local login/session cookie;
- CSRF;
- RBAC;
- bootstrap admin;
- admin user API;
- machine Bearer token;
- provider registry placeholders for future adapters.

Not implemented in this ADR task:

- Yandex OAuth/OIDC callback flow;
- per-user API tokens;
- OIDC discovery/client implementation;
- admin UI for auth provider settings.
