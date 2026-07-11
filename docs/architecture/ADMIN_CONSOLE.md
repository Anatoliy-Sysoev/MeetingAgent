# Admin Console Contract

Updated: 2026-07-07.

Issue: #40.

## Purpose

The MeetingAgent admin console is the operator surface for users, roles,
access, runtime health, jobs, audit, and controlled destructive operations.

This document is the product/API contract. It does not by itself implement a
new production UI page.

## Access Model

Admin console access is browser-user only.

Required:

- authenticated MeetingAgent user session;
- local `admin` role;
- CSRF token on every mutation.

Not allowed by default:

- machine Bearer token as admin UI credential;
- unauthenticated access;
- external provider identity granting admin without local role mapping.

This follows ADR-0039:

- external providers authenticate identity;
- MeetingAgent local RBAC authorizes actions;
- `MEETINGAGENT_API_TOKEN` remains a separate automation fallback.

## Information Architecture

### 1. Users And Roles

Purpose: manage local MeetingAgent users and their roles.

Required UI fields:

- `user_id`;
- email;
- display name;
- status;
- roles;
- provider summary when available;
- created/updated/last login timestamps.

Actions:

- create local user;
- edit display name;
- assign roles: `viewer`, `editor`, `admin`;
- disable/enable user;
- prevent last active admin removal or demotion.

Current API coverage:

```text
GET   /admin/users
GET   /admin/users/{user_id}
POST  /admin/users
PATCH /admin/users/{user_id}
POST  /admin/users/{user_id}/disable
POST  /admin/users/{user_id}/enable
```

### 2. Access Settings

Purpose: show auth mode and provider readiness without leaking secrets.

Required UI fields:

- deployment mode;
- local login status;
- Yandex/OIDC planned provider status;
- callback/redirect URI when provider is configured;
- machine token configured/weak/missing status, without token value;
- trusted proxy policy summary.

Current API coverage:

```text
GET /admin/security/status
```

Planned API:

```text
GET /admin/auth/settings
POST /admin/tokens/rotate
```

Token rotation must never return the old token and must require explicit
confirmation.

### 3. Jobs And Processing

Purpose: see active and recent processing work and perform controlled actions.

Required UI fields:

- job id;
- meeting id;
- stage/profile;
- status;
- timestamps;
- last public-safe error;
- current child stage for pipeline jobs.

Current API coverage:

```text
GET  /jobs/active
GET  /meetings/{meeting_id}/jobs/{job_id}
POST /meetings/{meeting_id}/jobs/{job_id}/cancel
POST /meetings/{meeting_id}/jobs/{stage}/retry
POST /meetings/{meeting_id}/jobs/pipeline
```

Planned admin aggregate API:

```text
GET /admin/jobs
POST /admin/jobs/{job_id}/cancel
POST /admin/jobs/{job_id}/retry
```

The aggregate admin API must not expose command lines, local paths, raw
tracebacks, or secret-containing environment values.

### 4. Meetings Administration

Purpose: operational control over meeting cards.

Required UI fields:

- meeting id;
- title;
- processing status;
- source/media availability;
- artifact manifest summary;
- last error summary;
- retention/archive state.

Current API coverage:

```text
GET /meetings
GET /meetings/{meeting_id}
GET /meetings/{meeting_id}/artifacts/manifest
GET /meetings/{meeting_id}/pipeline/readiness
```

Planned admin actions:

```text
POST   /admin/meetings/{meeting_id}/archive
DELETE /admin/meetings/{meeting_id}
```

Delete/archive must require explicit confirmation and must write audit events.

### 5. Audit And Diagnostics

Purpose: answer who changed what and whether the runtime is safe.

Required audit events:

- login/logout;
- denied access;
- bootstrap admin;
- user creation;
- role change;
- enable/disable user;
- job cancel/retry/resume;
- token rotation;
- meeting archive/delete.

Current persistence:

- `auth_audit_events` table exists in the local auth SQLite database.

Current diagnostics API and planned audit API:

```text
GET /admin/audit
GET /admin/diagnostics/health
GET /admin/diagnostics/meetings/{meeting_id}
```

`GET /admin/diagnostics/health` is implemented and requires an admin browser
session with `users.manage`. Meeting diagnostics uses the same browser-admin
guard and is the only API surface allowed to return the raw meeting card and
its absolute storage path. Machine Bearer tokens are rejected. `GET
/admin/audit` remains planned.

Audit responses must redact sensitive values and avoid filesystem paths unless
the route is explicitly local-admin diagnostic and documented as such.

### 6. Runtime Settings

MVP console mode is read-only.

Show:

- active corpus key/name;
- configured model names;
- Ollama URL readiness summary;
- deployment mode;
- trusted proxy policy;
- key feature flags.

Editable settings require a separate ADR/task. Raw secrets are never returned.

## RBAC Matrix

| Capability | viewer | editor | admin | machine |
|---|---:|---:|---:|---:|
| Open admin console | no | no | yes | no |
| List users | no | no | yes | no |
| Create/update/disable users | no | no | yes | no |
| Change roles | no | no | yes | no |
| View auth/security status | no | no | yes | no |
| View active jobs | no | limited own/read APIs | yes | limited operational API |
| Cancel/retry jobs | no | yes for meeting flow | yes | yes for operational API |
| Archive/delete meetings | no | no | yes | no by default |
| View audit log | no | no | yes | no |
| Rotate machine token | no | no | yes | no |

## Security Rules

- No secret values in UI or API responses.
- No OAuth access tokens in browser storage.
- No localStorage/sessionStorage for credentials or CSRF.
- Admin mutations require CSRF for cookie-authenticated users.
- Machine token does not grant admin UI access.
- Destructive actions require explicit confirmation.
- Role changes require explicit confirmation.
- Last active admin cannot be disabled or demoted.
- All admin mutations must emit audit events.

## Current Implementation Status

Implemented:

- local users and roles;
- first-admin bootstrap;
- admin user API;
- deployment safety status API;
- RBAC/CSRF enforcement;
- machine token blocked from user-management routes;
- audit table and audit writes for user-management actions;
- last-active-admin protection.

Not implemented:

- dedicated admin UI page;
- aggregate `/admin/jobs`;
- `/admin/audit`;
- `/admin/auth/settings`;
- machine token rotation endpoint;
- meeting archive/delete admin routes;
- external provider settings UI.

## Implementation Plan

1. Add an admin-only Web UI section/page with Users and Security status first.
2. Add read-only `/admin/audit` over existing audit table.
3. Add `/admin/jobs` as a path-safe aggregate over `JobRunner`.
4. Add meeting archive/delete only after a dedicated destructive-action ADR.
5. Add external provider settings after Yandex/OIDC implementation.
