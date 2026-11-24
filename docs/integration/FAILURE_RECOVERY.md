# Failure classification, fault injection and recovery (Phase 9)

## Failure categories

| Category | Detection | User-visible status | Affected | Recovery behaviour | Persistence implications | Retry / manual action |
|---|---|---|---|---|---|---|
| Configuration | `orchestration check`; `load_settings` (field names only); `MissionConfig` validation | start script error; API 422 | everything not yet started | none: refuse to start | none | fix configuration |
| Dependency | `orchestration check` dependency groups; start script version checks | start script error | services | none | none | install declared extras / `npm ci` |
| Database | `/health/ready` (ping + revision); per-tick transaction failure | backend not ready; mission `failed` after 20 consecutive tick failures | persistence, API | tick data is retried on the next tick (adapter cursors restored) | no partial tick is committed | restore database; restart |
| Backend process | `/health/live`; start script readiness wait | dashboard "backend offline" | all connected views | missions left running are marked `stopped` at next start | committed records survive | restart via scripts |
| Simulator | exception in `ctx.step` | mission `failed` ("simulation error: <type>") | that mission only | none (no automatic restart) | records up to the failure stay | create a new mission |
| Agent (Model 1) | heartbeat age, availability, `connection_lost` | agent condition stale/unavailable/unknown | that agent's coverage | agent holds position, needs new assignment after link recovery | agent state not persisted | none |
| Model 2 | command endpoint unavailable | `MODEL_2_UNAVAILABLE` / `MODEL_2_RECOVERED`, `model2_state=unavailable` | incident processing | reports queue in transport and are processed after recovery; decisions sent during the outage expire or are rejected | Model 2 checkpoints every N ticks | none; memory restore on request |
| Communication | router events, endpoint state | `COMMUNICATION_DEGRADED` / `RESTORED`; delivery ratio | reports, instructions | retries for control messages, retention, expiry | delivered messages only | none |
| Coordination | task conflicts, availability changes | coordination page conflict markers | task assignment | tasks re-offered or expire | task history persisted | none |
| Event processing | outbox dispatch failures counted (`publish_failures`) | system health | live updates | events stay in the outbox; clients replay by sequence | outbox is transactional | none |
| WebSocket | close codes 4401/4403/4008/4029, heartbeat timeout | "Live events" reconnecting / polling | live updates | client reconnects with backoff and `after_sequence`; REST polling fallback | none | none |
| Frontend | error boundary, schema validation failure | error state with request ID | one view | retry; reload | none | reload page |
| Authorization | 401/403/404 (cross-mission is 404) | sign-in or "not permitted" | the request | refresh token rotation; session expiry signs out | audit record for sensitive actions | sign in again |
| Invalid data | Pydantic/Zod validation; Model 2 outcomes (`stale`, `duplicate`, `conflict`, `invalid_scope`, `unauthorized`, `clock_reversal`, `capacity`) | 422/409; observation outcome | that report | refused, never fused | refused API reports are not stored | none |
| Resource exhaustion | concurrency limit, request size limit, WebSocket queue overflow, Model 2 capacity, login rate limit | 409 `simulation_limit`, 413, 4008, `capacity` outcome, 429 | the request | bounded queues and limits | none | stop missions / wait |

Consequential operations are never retried automatically: a human decision is submitted once
(idempotent by key) and missions are never restarted by the system.

## Controlled fault injection (all deterministic, disposable resources)

| # | Fault | Where tested | Result |
|---|---|---|---|
| 1 | Temporary Model 1 unavailability | `flood_agent_disconnected` (integration test + matrix) | completes; `connection_lost` > 0 |
| 2 | Multiple unavailable agents | `flood_unavailable` | completes; inactive agents reported |
| 3 | Missing sensor modalities | `command_missing_modalities` | evidence limited to the configured modalities |
| 4 | Invalid observations | backend ingestion tests (future time, wrong mission, tampered duplicate) | 409/422, not fused |
| 5 | Duplicate messages | `flood_network_duplicate`; idempotent API resubmission | duplicates recognized, not double-counted |
| 6 | Delayed messages | `flood_network_delay`, `command_stale` | delayed reports delivered; beyond 1.5 s refused as stale (72/72) |
| 7 | Out-of-order messages | `flood_network_reorder`; frontend event buffer tests | completes; buffer re-orders |
| 8 | Packet loss | `flood_network_loss` | dropped > 0; delivery ratio 0.62 (matrix mean) |
| 9 | Partition | `flood_network_partition` | delivery ratio < 1; completes |
| 10 | Model 2 unavailability | `flood_server_unavailable`, `outage_steps` (integration, backend, connected e2e, demo) | `MODEL_2_UNAVAILABLE` before `MODEL_2_RECOVERED`; shown in the dashboard |
| 11 | Conflicting evidence | API reports with different findings for one cell and instant (backend test, connected e2e, demo) | shown as `conflicting` (after the Phase 9 fix) |
| 12 | Database connection failure | `test_database_failure_during_tick_loses_nothing` | nothing lost; tick retried |
| 13 | Transaction rollback | same test; constraint tests | cursors restored, no partial writes |
| 14 | Backend restart | demo phase 2 (scripted stop/start), `test_committed_data_survives_application_restart`, `test_interrupted_missions_are_stopped_on_startup` | records identical; interrupted missions stopped |
| 15 | WebSocket disconnect | demo (`after_sequence` replay, no gaps); Phase 8 connected e2e (`routeWebSocket` close) | resumed without gaps |
| 16 | Slow dashboard client | `test_websocket.py` slow-client test | `resync_required`, close 4008, REST resync |
| 17 | Browser refresh | Phase 8 connected e2e (session recovery) | session restored from tab-scoped refresh token |
| 18 | Session expiration | frontend transport tests, backend auth tests | refresh rotation; reuse rejected; sign-out on expiry |
| 19 | Stale recommendation review | backend oversight tests, connected e2e, demo | 409 `stale_version` |
| 20 | Invalid lifecycle request | duplicate start (409 `duplicate_execution`), stop after stop (409), start of a stopped mission | refused |

Not injected: a database outage at the process level while the backend runs (only per-tick
transaction failure is simulated), disk-full conditions and PostgreSQL failover.

## Recovery levels

| Level | Status | Evidence |
|---|---|---|
| Historical record recovery | Supported | summary identical before and after restart (demo phase 2) |
| Mission metadata recovery | Supported | status, history and run records survive |
| Model 2 memory recovery | Supported for inspection | checkpoint digest verified, restored read model matches persisted read model |
| Agent (Model 1) state recovery | Not supported | private memory is in-process only |
| Exact simulation continuation | Not supported | simulator state is not durable; interrupted missions are marked `stopped`. Determinism allows re-running the same configuration from the start |
| Event stream recovery | Supported | replay by sequence; REST resynchronisation |
| Frontend recovery | Supported | reload restores the session in the same tab |
