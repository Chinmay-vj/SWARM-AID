# Integration contracts (Phase 9 audit)

Authoritative definitions are the code below. Documentation must follow the code; the wire types,
protocol documentation and validation tests change together (AGENTS.md).

| Contract | Authoritative definition | Version | Validation tests |
|---|---|---|---|
| Domain values (cells, evidence, observations, findings, incidents, actions) | `agents/shared/domain.py` | implicit (Phase 1) | `tests/unit/test_contracts.py` |
| Transport envelope and payloads | `communication/messages.py` (`Envelope.schema_version` 1.0/1.1/1.2) | per message | `test_contracts.py`, `test_transport.py` |
| Provider ports | `interfaces/providers.py`, `agents/command_agent/agent.py` (`UrgencyAssessmentProvider`) | — | Model 1 / Model 2 tests |
| Scenario | `simulation/core/configuration.py` (`Scenario.version` "1") | "1" | simulation tests, `orchestration check` |
| Mission configuration | `backend/integrations/simulation_adapter.py` (`MissionConfig`, extra fields forbidden) | — | `test_orchestration.py` |
| REST resources | `backend/schemas.py`, served as OpenAPI at `/openapi.json` | API `/api/v1` | `tests/backend_api/` |
| Domain events | `backend/services/events.py` (`EVENT_SCHEMA_VERSION` "1") | "1" | `test_websocket.py`, connected demo |
| WebSocket protocol | `docs/backend/WEBSOCKET_PROTOCOL.md`, `backend/realtime/hub.py` | — | `test_websocket.py` |
| Dashboard contracts | `frontend/src/contracts/api.ts`, `events.ts` (Zod, runtime-validated) | — | `frontend/tests/unit/contracts.test.ts` |
| Database schema | `backend/database/models.py`, `migrations/` | Alembic head `0001` | `test_database.py` |
| Research results | `orchestration/headless.py` (`RESULT_VERSION` "1"), manifest `manifest_version` "1" | "1" | `test_orchestration.py` |

Phase 9 changed one wire contract additively: `GET /api/v1/observations/{id}/trace`
(`ObservationTraceOut`). No existing field changed meaning. The persisted
`incident_evidence.role` now carries `conflicting` when Model 2 flags a report; the column and
its allowed values already existed, and the dashboard already displayed the count.

## Identity

| Identity | Format | Scope and rule |
|---|---|---|
| Backend mission | UUID4 (`missions.id`) | Global |
| Simulator mission | `uuid5(NAMESPACE_OID, scenario_id)` | Deterministic per scenario; repeats across missions, never a database key |
| Agent | key `d0..dN` (simulator), UUID (`agents.id`) | Agent key unique within a mission; machine credentials are bound to one mission and agent key |
| Observation | UUID chosen by the reporting agent | Unique per mission (`UNIQUE(mission_id, observation_id)`); stable across forwarding |
| Message | UUID (`Envelope.message_id`); API reports get `uuid5(sim mission, "api/agent/observation")` | Idempotency key for reports |
| Evidence | UUID per sample, with `origin` (capturing agent), `captured_ms`, `modality`, opaque `artifact_key` | Origin preserved through fusion (tested) |
| Incident / recommendation | Model 2 UUID scoped by `uuid5(mission_id, "model2/<id>")` | Model 2 IDs repeat across identical missions, so the backend scopes them |
| Recommendation version | `incident_revision` (exposed as `version`) | Decisions must name the exact version (409 `stale_version` otherwise) |
| Human decision | UUID4, `UNIQUE(mission, actor, idempotency_key)` | Same key, same action returns the same decision; same key, different action is 409 |
| Event | `sequence` strictly increasing per mission (`UNIQUE(mission_id, sequence)`) | Clients de-duplicate by sequence |
| Correlation | events: `correlation_id` = run ID for simulation events, request ID for API events; envelopes: `correlation_id` | — |
| Resource version | `version` columns on incidents and recommendations (optimistic locking) | — |

## Time

- **Simulation time** (`*_ms`, `sim_time_ms`): integer milliseconds since mission start,
  `tick × tick_ms`. Deterministic. Does not advance while paused.
- **Wall-clock time** (`*_at`): timezone-aware UTC (`datetime.now(UTC)`), set when rows are
  written or requests handled. Not deterministic.
- **Received time**: `observations.received_ms` (simulation time when Model 2 received the
  report) and `received_at` (wall clock).
- Ordering rules checked in Phase 9 tests: evidence `captured_ms` ≤ observation `observed_ms`
  ≤ envelope `sent_ms` ≤ current simulation time; the command inbox is ordered by `sent_ms`;
  task histories are ordered; API reports later than mission time are refused (409
  `future_observation`).
- Freshness: Model 2 refuses reports older than `freshness_ms` (1500 ms); the API marks
  observations `stale` with the same window (`FRESHNESS_MS` in `queries.py` and the dashboard).

## Coordinates

- All operational coordinates are local grid cells, `crs = "swarm-aid:grid"`, unit `cell`,
  origin at the top-left, `0 ≤ x < width`, `0 ≤ y < height`. They are **not** GPS coordinates.
- Reported cells carry `uncertainty = 0.5` cell (cell granularity).
- A missing location stays `null` in every layer; the dashboard shows "not reported" and never
  draws it at (0, 0). Tested in the backend (`test_location_reference_systems`), the
  integration tests (all reported cells are inside the grid) and frontend unit tests.
- `EPSG:4326` is accepted by the API schema only for valid longitude/latitude; the simulator
  never produces it.

## Confidence, urgency and uncertainty

- `confidence` (0–1) is the reporting agent's confidence in one observation. Unknown confidence
  is shown as "unknown", never 0.
- Urgency is Model 2's separate `priority_level` (`review_required`, `elevated`,
  `potentially_urgent`) with a textual `priority_reason` and evidence references. It is not
  derived from confidence.
- Incident `category` (`routine`, `hazard`, `possible_human`, `uncertain_need`,
  `suspected_emergency`, `human_confirmed`) is separate again. `human_confirmed` requires a human
  decision reference; routine environmental observations never become incidents.
- Uncertainty is carried as `uncertainties` (incident revisions) and `unknowns`
  (recommendations); conflicting evidence as `incident_evidence.role = "conflicting"`.

## Availability, health and communication

| Field | Values | Source |
|---|---|---|
| `agents.availability` | from coordination availability | `AssignmentFixture.availability` |
| `agents.communication` | `connected`, `disconnected` | router link state |
| `mission_runtime.model2_state` | `inactive`, `available`, `unavailable`, `ended` | derived from the Model 2 agent state (`active`, `offline`, `ended`) |
| `mission_runtime.communication_state` | `unknown`, `nominal`, `degraded` | any disconnected endpoint |
| Dashboard agent condition | `nominal`, `degraded`, `stale`, `unavailable`, `unknown` | a missing heartbeat is stale or unknown, never "failed" |

## Lifecycle

Mission states and transitions: SYSTEM_ARCHITECTURE.md §4. Recommendation and decision states:
§9. Task states: `simulation/adapters/task_registry.py` (`TERMINAL` = completed, expired,
failed, cancelled; no activity after a terminal state is tested).
