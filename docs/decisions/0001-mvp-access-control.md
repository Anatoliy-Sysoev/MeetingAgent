# ADR 0001 — MVP Access Control

Refs #33

## Status

Accepted — 2026-06-09. Applies to MVP only; superseded once a hardened multi-user
deployment is required.

## Context

MeetingAgent MVP is deployed for a single small team of roughly 10–15 users on an
internal LAN. The Meeting API (read-only) already exists, and upcoming tasks
(MA-INGEST-DEDUP, MA-JOB-API) will add endpoints that accept uploads, create
meeting cards, and trigger processing actions. Those are the first write/action
surfaces and must not ship without an access-control decision.

Constraints and assumptions:

- The corpus contains sensitive project material (НТК documents, transcripts).
  Even on a LAN the content warrants access control.
- A LAN is **not** treated as fully trusted: other devices, guests, and
  misconfigured network segments can reach the host. "Internal network" is not a
  security boundary on its own.
- The product is local-first and CPU-first. The auth mechanism must not add a
  cloud dependency, an external identity provider, or heavyweight infrastructure.
- The team is small and known; onboarding/offboarding is infrequent and manual.
- Attribution (who uploaded / who triggered a job) becomes useful once the review
  queue (MA-REVIEW-QUEUE) exists, but is not strictly required for read-only access.

## Decision

For the MVP:

1. **Web UI and API are protected by a token.** The deployment supports either a
   single **shared token** (simplest) or **per-user tokens** (when attribution is
   wanted). Both are static bearer-style secrets configured locally, never
   committed to Git.
2. **OIDC/SSO is explicitly out of scope** for the MVP.
3. **Public/anonymous share links are out of scope** for the MVP.
4. **The LAN is not treated as fully trusted** — no endpoint is left unauthenticated
   on the assumption that "only our network can reach it".

The shared token is the default for the smallest deployments; per-user tokens are
the recommended upgrade as soon as attribution (review queue, audit) is needed,
since they require no new infrastructure — only a local token-to-user mapping.

## Alternatives

- **No auth (rely on LAN).** Rejected. Contradicts the "LAN is not fully trusted"
  premise; sensitive corpus would be exposed to anyone who can reach the host.
- **Shared token.** Accepted as the minimal viable option. Simple to deploy and
  rotate. Weakness: no attribution, and a leak forces a single global rotation.
- **Per-user token.** Accepted as the recommended option when attribution matters.
  Still no external dependency: a local mapping of token → user. Slightly more
  bookkeeping; revocation is per-user rather than global.
- **OIDC/SSO (Keycloak, Azure AD, Google, Auth0).** Rejected for MVP. Provides
  real identity, MFA, and central revocation, but adds an identity-provider
  dependency and operational weight that is disproportionate for 10–15 LAN users
  and conflicts with local-first. Revisit if the deployment grows or leaves the LAN.

## Consequences

- Upcoming write/action endpoints (MA-INGEST-DEDUP, MA-JOB-API) can ship behind a
  single token check without waiting on an identity system.
- Token transport must be protected: bind the service to the intended interface and
  prefer TLS (or an SSH/VPN tunnel) so the bearer token is not sent in clear text.
- Tokens are secrets: stored only in local config / `.env`, never committed,
  rotatable. A shared-token leak requires global rotation; per-user tokens limit
  blast radius to one user.
- No attribution under the shared-token mode — MA-REVIEW-QUEUE labelling cannot
  reliably attribute actions to a person until per-user tokens are enabled.
- This decision is intentionally lightweight and is expected to be superseded by a
  future ADR if/when SSO, public links, or off-LAN access become requirements.

## Follow-up tasks

- MA-INGEST-DEDUP / MA-JOB-API: enforce the token check on every write/action route.
- Define where tokens live (local config / `.env`) and document rotation — extends
  the existing "do not commit secrets" rule.
- Decide default interface binding and TLS/tunnel guidance for the deployment.
- Revisit OIDC/SSO and public links in a follow-up ADR if scope grows beyond the
  small trusted LAN team.
