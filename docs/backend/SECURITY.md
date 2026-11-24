# Authentication, authorization, security model and threat model

This document consolidates the authentication, authorization, permission matrix, security model and threat model documents. The controls below are implemented and tested locally. **They do not make the backend production-secure.** See the remaining limitations at the end.

## Authentication

```mermaid
sequenceDiagram
  participant H as Human client
  participant A as /api/v1/auth
  participant DB as Database
  H->>A: POST /login {username, password}
  A->>A: rate limit per client and username
  A->>DB: load user; Argon2id verify (dummy hash if unknown)
  A->>DB: insert refresh_tokens(fingerprint, family) + audit
  A-->>H: access token (15 min) + refresh token (12 h)
  H->>A: POST /refresh {refresh_token}
  A->>DB: verify fingerprint; revoke old; issue new in same family
  Note over A,DB: reuse of a revoked refresh token revokes the whole family
  H->>A: any request with Authorization: Bearer <access>
  A->>DB: load user, active flag and memberships on every request
```

- **Passwords:** Argon2id via `pwdlib` (default parameters; about 61 ms median verification on the development host). Minimum length 12. Unknown usernames verify against a dummy hash so timing does not reveal account existence.
- **Tokens:** PyJWT, HS256/384/512 only (`algorithms` pinned, so `alg=none` is rejected). Validated claims: signature, `exp`, `nbf`, `iat`, `iss`, `aud`, `sub`, `jti` and a custom purpose claim `pur` (`access` or `refresh`). Refresh tokens cannot be used as access tokens.
- **Separate audiences:** humans use `swarm-aid:human`, machines `swarm-aid:machine`. Machine tokens come from `POST /auth/machine-token` with a credential ID and secret (Argon2id-hashed; shown once at creation). Machine principals have no global role and cannot call human-only endpoints.
- **Roles are never read from tokens.** Account status, global role and memberships are loaded from the database on every request, so deactivation or a membership change takes effect immediately (WebSockets re-check at each heartbeat).
- **Refresh tokens:** only a SHA-256 fingerprint is stored. Rotation revokes the old token; reuse of a revoked token revokes the family; logout revokes the family.
- **Signing secret:** `SWARM_JWT_SECRET` is mandatory (at least 32 characters, no default). Production settings refuse SQLite, debug mode and wildcard CORS.
- **First administrator:** `python -m backend.cli create-user --username admin --role administrator`. The password comes from `SWARM_NEW_USER_PASSWORD` or an interactive prompt, never from command-line arguments.

## Authorization: deny-by-default and mission-scoped

Permissions are checked in services against the resource's own `mission_id`, not just in routers (`backend/services/access.py`). A principal who cannot read a mission receives **404** for the mission and every object in it, so the response does not reveal the object exists. A principal who can read but lacks the specific permission receives **403**. Denied requests are audited (`access.denied`).

Global roles: `administrator` (manage users, memberships, system health, audit), `coordinator` (may create missions and becomes coordinator of them), `operator`, `researcher`, `observer`. Mission authority comes only from a mission membership.

### Permission matrix

| Permission | Coordinator | Operator | Researcher | Observer | Admin (no membership) | Agent (own mission) | Service |
|---|---|---|---|---|---|---|---|
| `mission.read` | yes | yes | yes | yes | yes |  | yes¹ |
| `mission.update` (name and description only) | yes |  |  |  |  |  |  |
| `mission.control` (start, pause, resume, stop, agent credentials, Model 2 recovery) | yes |  |  |  |  |  |  |
| `mission.override` (Model 2 assignment override) | yes |  |  |  |  |  |  |
| `membership.manage` | yes |  |  |  | yes |  |  |
| `incident.acknowledge` | yes | yes |  |  |  |  |  |
| `incident.request_review` (prioritize) | yes | yes |  |  |  |  |  |
| `incident.resolution_report` | yes | yes |  |  |  |  |  |
| `incident.close` | yes |  |  |  |  |  |  |
| `recommendation.decide` (approve, reject, request revision) | yes |  |  |  |  |  |  |
| `recommendation.confirm` (human-confirmed rescue need) | yes |  |  |  |  |  |  |
| `alert.acknowledge` | yes | yes |  |  |  |  |  |
| `feedback.correct` | yes | yes |  |  |  |  |  |
| `metrics.read` | yes |  | yes |  |  |  |  |
| `export.operational` | yes |  | yes |  |  |  |  |
| `export.research` (includes evaluator ground truth) |  |  | yes |  |  |  |  |
| `audit.read` | yes |  |  |  | yes |  |  |
| `observation.ingest` |  |  |  |  |  | yes |  |
| `agent.report` |  |  |  |  |  | yes |  |

¹ Service identities are defined but Phase 7 provides no endpoint to issue them. A global role holds no mission permission without a membership. Administrators hold no decision or control authority, so they cannot bypass mandatory domain rules. Every human decision is also validated independently by Model 2, and Model 1 safety gates still apply.

## API security controls

| Control | Implementation |
|---|---|
| Input validation | Pydantic schemas with `extra="forbid"` (blocks mass assignment of `status`, `created_by`, `config`, client-supplied classifications); bounded strings, ranges and list lengths. |
| Lifecycle protection | `PATCH /missions/{id}` edits name and description only, with an expected `version`; status changes only through lifecycle endpoints and the validated state machine. |
| Concurrency | Version checks (409 `stale_version`); idempotency keys for decisions; observation ID plus content for ingestion. |
| Injection | SQLAlchemy parameterized queries only; filter values are bound parameters (tested with injection strings). |
| File access | Scenarios chosen by allow-listed name; evidence stored content-addressed under `<root>/<mission>/<sha256>` with containment checks; media-type allow-list and size limit; `nosniff` and attachment headers. |
| Remote fetching | None. Evidence `artifact_key` is an opaque label and is never dereferenced. |
| Untrusted instructions | Report contents are data; nothing is executed or forwarded to a language model. |
| Request limits | `SWARM_MAX_REQUEST_BYTES` (Content-Length and streamed size, 413). Login rate limit per client and username (429). |
| CORS | Disabled unless `SWARM_CORS_ORIGINS` is set; no credentials; explicit methods and headers. |
| Errors | `{error: {code, message, request_id, details}}`; no stack traces or SQL in responses. |
| Correlation | `X-Request-ID` accepted when it matches a safe pattern, otherwise generated; echoed back; stored on audit rows and events. |
| Logging | JSON logs; keys matching password, secret, token, authorization, api key or private key are redacted; bearer and JWT-like strings are masked. |
| Audit | Append-only `audit_logs` (database triggers). Records: logins (success and failure), refresh-token reuse, logout, user creation and deactivation, membership grants, credential creation, mission create, update and lifecycle, approvals, reviews, overrides, alert acknowledgements, evidence storage, exports, Model 2 recovery, denied access. Details are redacted. Not cryptographically tamper-evident. |
| WebSocket | Authentication in the first frame (never the URL); mission permission required; re-authorized at each heartbeat; bounded queues. |

## Threat model (STRIDE summary)

| Threat | Example | Mitigation | Residual risk |
|---|---|---|---|
| Spoofing | Forged JWT; agent posing as another drone | Pinned algorithm, issuer, audience and purpose; reporter taken from the credential | Shared HS256 secret: whoever holds it can mint tokens. No MFA. |
| Tampering | Altering a stored decision; stale approval | Append-only audit; version checks; Model 2 revision validation | Database superusers can disable triggers; no hash chain. |
| Repudiation | "I never approved that" | Decision rows with actor, role, request ID; audit records | Audit integrity depends on database access control. |
| Information disclosure | Cross-mission reads; ground truth leakage | Mission-scoped 404s; ground truth only in research export | Error codes can distinguish 403 from 404 for members. |
| Denial of service | Login flooding; slow WebSocket consumers; large bodies | Rate limit, bounded queues, body limit, concurrent simulation limit | Rate limiter is in-process and per worker; no global throttling. |
| Elevation of privilege | Administrator approving recommendations; role in token | Matrix denies admins decision authority; roles loaded from the database | Administrators can grant themselves membership (audited). |

## Remaining limitations

- No TLS termination, reverse proxy, secret manager, key rotation, MFA, password reset or account lockout beyond rate limiting.
- In-process rate limiting and runtime state: single worker only.
- SQLite in development has no per-user database permissions; PostgreSQL role separation (application role without trigger or DDL rights) is recommended but not configured.
- Audit logs are append-only by trigger, not cryptographically chained. Retention pruning (`SWARM_AUDIT_RETENTION_DAYS`) is not implemented: deleting audit rows needs a deliberate maintenance migration.
- No dependency vulnerability scanning was run in Phase 7.
- Not for public internet deployment.
