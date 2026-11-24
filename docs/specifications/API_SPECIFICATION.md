# Future command API

Prefix all routes with /v1. The backend derives principal and role from an authenticated session. Mission membership and action permission are checked for every read, write and socket subscription. Requests carry a correlation ID. Mutating retries carry an idempotency key scoped to principal and mission.

| Method and route | Input | Success |
|---|---|---|
| POST /missions | Validated scenario configuration and operator identity from session | 201 mission ID, revision and initial status |
| GET /missions | Membership-scoped status filter and cursor | 200 current and historical missions with next cursor |
| GET /missions/{id} | Mission membership | 200 status, restrictions and revision |
| GET /missions/{id}/drones | Cursor and limit | 200 positions, observation age, battery and health |
| GET /missions/{id}/coverage | Grid frame and as-of tick | 200 reported coverage and unknown cells |
| GET /missions/{id}/incidents | Category, cursor, limit | 200 incident summaries including hazards |
| GET /missions/{id}/incidents/{iid} | Optional revision | 200 reports, uncertainty, recommendations and evidence keys |
| GET /missions/{id}/evidence/{eid} | Evidence permission | 200 permitted artifact or metadata |
| POST /missions/{id}/decisions | HumanApproval envelope and expected incident revision | 201 committed decision ID and revision |
| POST /missions/{id}/overrides | HumanOverride envelope and required If-Match mission revision | 201 audit ID and mission revision |
| GET /missions/{id}/events | Cursor, type, since tick | 200 message metadata, decision history and next cursor |
| GET /runs/{id}/metrics | Research read permission | 200 metrics, denominators and config digest |
| WS /missions/{id}/stream | Cursor and allowed topics | Snapshot then sequenced telemetry, incident and review events |

Return 401 for missing authentication, 403 for denied scope, 404 for unavailable records, 409 for stale revisions or key reuse with different content and 422 for invalid payloads. Errors include stable code, correlation ID and retryability. Returning a stored successful outcome on an identical retry prevents double approval. A socket gap requires cursor replay or snapshot. No Phase 1 endpoint listens on a port.
