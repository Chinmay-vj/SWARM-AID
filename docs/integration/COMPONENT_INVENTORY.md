# Component inventory and integration gap analysis (Phase 9)

Status was assigned from what Phase 9 actually executed on 2026-11-24 (commands and totals in
`docs/PHASE_9_COMPLETION_REPORT.md`), not from earlier completion reports.

Classification: **Verified** (exercised end to end in Phase 9), **Partially verified**,
**Implemented but unverified**, **Synthetic only**, **Missing**, **Defective**, **Incompatible**.

## Inventory

| Component | Responsibility | Entry point | Depends on | Inputs → outputs | Configuration | Lifecycle | Tests | Known limitations | Status |
|---|---|---|---|---|---|---|---|---|---|
| Shared contracts | Domain values, messages, provider ports | `agents/shared/domain.py`, `communication/messages.py`, `interfaces/providers.py` | pydantic | validated frozen records | none | import-time | `tests/unit/test_contracts.py` | `configs/default.toml` is a Phase 1 example not read at runtime | Verified |
| Simulator engine | World, ground truth, mission clock, movement | `simulation/core/engine.py` | scenario fixtures | `Scenario` → packets per agent, metrics | `configs/scenarios/*.json` (22) | per mission, `reset(seed)` | `tests/integration/test_simulation.py`, Phase 9 matrix (141 runs incl. repeats) | Deterministic across processes and hash seeds (verified). See disaster profiles | Verified |
| Disaster profiles | Terrain semantics per disaster | `simulation/environments/base.py` | engine | label sets | `disaster` field | static | matrix | Flood, cyclone and wildfire differ only in tile labels; earthquake and landslide share "debris" (blocking). Wildfire and flood give identical dynamics for the same seed. No missing-person scenario exists | Partially verified |
| Mock sensors | Symbolic, noisy readings with dropout, misses, false positives | `simulation/sensors/mock.py` | engine | world view → `Packet` | scenario `noise`, `miss`, `dropout`, `modalities` | per tick | simulation and integration tests | Symbolic values only; no pixels or audio | Synthetic only (by design) |
| Model 1 agent | Local perception, private memory, world model, intent, planning, safety | `agents/drone_agent/agent.py` via `simulation/adapters/model1.py` (`Fleet`) | providers, mailbox | `Packet` → reports, `Move` | `configs/model1.json` | one per drone per mission | `test_model1.py`, Phase 9 object-graph isolation test | Providers are injectable but `Fleet` always builds mocks | Verified |
| Safety controller | Independent check of proposed actions and leases | `agents/drone_agent/safety.py` | domain | `Action` + `SafetyContext` → allowed action | battery reserve, prohibited cells | per decision | Phase 3 tests; `safety_interventions` counted in every Phase 9 run | — | Verified |
| Simulated transport | Routing, session binding, loss, delay, duplicates, reorder, partitions, outages, receipts | `communication/network.py`, `simulation/adapters/communications.py` | messages | envelopes → deliveries, router events | scenario `network`, `loss`, `delay`, `partition`, `outage_steps` | per mission | `test_transport.py`, 12 fault fixtures in Phase 9 | Peer and command traffic share router counters in persisted metrics | Verified |
| Coordination | Survey tasks, availability, task history; baselines independent, fixed_sector, shared_information | `simulation/adapters/coordination.py`, `task_registry.py` | transport | reports → tasks, conflicts | `coordination` in mission config | per mission | `test_coordination.py`, matrix block "coordination" | Agent-reported coverage and evaluator coverage are separate fields (by design) | Verified |
| Model 2 command agent | Report validation, fusion, incidents, urgency, recommendations, decision validation, checkpoint | `agents/command_agent/agent.py` | providers | reports → incident updates, alerts; human decisions → transitions | `command_mode`, `configs/model2.json` (only `--command-config`) | one per mission | `test_command_agent.py`, Phase 9 provenance tests, connected demo | Conflict detection is per cell and instant; the simulator rarely produces two labels at one instant | Verified |
| PettingZoo environment | MARL-facing parallel env over the engine | `simulation/adapters/parallel.py` (`RescueEnv`) | pettingzoo, gymnasium | actions → 4-int observations, rewards (injected, default 0) | scenario | `reset(seed)` / `step` | `parallel_api_test` in `test_simulation.py` | Bypasses Model 1, transport, coordination and Model 2 | Partially verified |
| Evaluator | Ground-truth metrics, research export | `evaluation/results.py` | engine | engine → metrics | — | end of run | backend export tests, Phase 9 leakage tests | — | Verified |
| Phase 5/6 research runners | Matched experiments | `evaluation/experiment_runner.py`, `evaluation/command_agent_experiments.py` | fleet | plan → episodes, CSV | `configs/experiments/phase5_*`, `phase6_*` | batch | executed in Phase 9 via `python -m orchestration experiment` | — | Verified |
| Backend API | Auth, authorization, missions, queries, oversight, exports, catalog, health | `backend/application.py`, `backend/main.py` | FastAPI, SQLAlchemy | REST/JSON | `.env` / `SWARM_*` | process | 59 tests in `tests/backend_api/` | — | Verified |
| Runtime manager | Mission execution, lifecycle, per-tick persistence, recovery on start | `backend/integrations/runtime.py` | simulation adapter | mission config → running context | `max_concurrent_simulations`, `simulation_tick_delay_ms` | per mission task | backend tests, connected demo | Paused missions count toward the concurrency limit | Verified |
| Model 2 persistence adapter | Copy Model 1/Model 2 outputs into the database each tick | `backend/integrations/model2_adapter.py` | runtime | context → rows + outbox | — | per tick | backend tests | **Fixed in Phase 9:** conflicting reports were stored as supporting evidence | Verified (after fix) |
| Database (SQLite) | Persistence, constraints, outbox | `backend/database/`, `migrations/` (head `0001`) | SQLAlchemy, Alembic | — | `SWARM_DATABASE_URL` | migrations | backend tests, restart demo | — | Verified |
| Database (PostgreSQL/PostGIS) | Production-intended persistence | same, `docker-compose.yml` | psycopg, geoalchemy2 | — | `SWARM_DATABASE_URL` | — | `test_postgis_migration_geometry_and_spatial_query` (skipped: no server) | Docker/PostgreSQL not installed (no authorization) | Implemented but unverified |
| Event outbox + WebSocket hub | Ordered events, replay, heartbeats, slow-client handling | `backend/services/events.py`, `backend/realtime/hub.py` | database | events → frames | `websocket_*` | per connection | `test_websocket.py`, connected demo reconnection | At-least-once with client dedup; not exactly-once | Verified |
| Model 2 checkpoint/recovery | Digest-verified journal and read model | `Model2Sync.checkpoint`, `POST /missions/{id}/model2/recovery` | database | snapshot → restored read model | `snapshot_every_ticks` | periodic | `test_recovery.py`, demo phase 2 | Restores Model 2 memory for inspection; the simulation does not resume | Verified |
| Evidence object store | Content-addressed synthetic evidence upload and authorized retrieval | `backend/persistence/evidence_store.py` | filesystem | bytes → object id | `evidence_*` | — | ingestion tests | The simulator never uploads objects, so connected missions show references only | Partially verified |
| Observation trace (Phase 9) | Research diagnostic of one report's processing history | `GET /api/v1/observations/{id}/trace` | queries | observation → incidents, recommendations, decisions, events | — | request | `tests/backend_api/test_system_backend.py`, demo | Bounded to 500 events | Verified |
| Dashboard, connected mode | Authorized display and human review | `frontend/src/services/api/connected.ts` | backend | REST + WebSocket → UI | `frontend/.env`, Vite proxy | browser session | 77 unit/component, 10 connected e2e | Overview polls about 8–9 requests/s | Verified |
| Dashboard, synthetic mode | Labelled demonstration without backend | `frontend/src/services/providers/synthetic/` | none | presets → UI | preset choice | browser session | 12 mock e2e (no `/api` or `/ws` requests) | — | Synthetic only (by design) |
| Orchestration (Phase 9) | Config checks, headless profile, matrix, manifests, owned backend process, status | `python -m orchestration` | backend adapter, evaluation | — | `configs/experiments/phase9_*.json` | CLI | 15 + 20 tests, scripts exercised | — | Verified |
| Start, status and stop scripts (Phase 9) | Single-command startup, ownership-safe shutdown | `scripts/start_system.ps1`, `status_system.ps1`, `stop_system.ps1` | orchestration | — | ports 8000/5173 | — | executed repeatedly in Phase 9 | Windows PowerShell only | Verified |
| Legacy presentation MVP | Phase 8 presentation | `frontend/legacy-mvp/` | none | — | — | static | none | Kept unchanged | Implemented but unverified |
| Pygame viewer | Simulator debugging | `simulation/visualization/renderer.py` | pygame | engine → window | — | interactive | renderer smoke test | — | Verified (smoke) |

No component was found **Incompatible**. The one **Defective** component found (the Model 2
persistence adapter) was corrected and regression-tested.

## Integration gap analysis

| Gap | Severity | Resolution in Phase 9 |
|---|---|---|
| Contradicting reports flagged by Model 2 were persisted as supporting evidence, so operators always saw "0 conflicting" | High | Fixed (`role="conflicting"` copied from Model 2), regression test, connected e2e |
| No single-command startup, status or ownership-safe shutdown | High | `scripts/start_system.ps1`, `status_system.ps1`, `stop_system.ps1`, `python -m orchestration serve` |
| No validated configuration check before start | Medium | `python -m orchestration check --profile ...` (37 checks) |
| No headless profile running the same stack as the backend | Medium | `python -m orchestration run` |
| No unified experiment runner and no integrated-stack matrix | Medium | `python -m orchestration matrix` and `experiment` (dispatches to Phase 5/6 runners) |
| No observation-level traceability diagnostic | Medium | `GET /observations/{id}/trace` |
| Redirecting the start script's output blocked until the services exited (inherited console handles) | Medium | Services start without inherited handles; the server writes its own log |
| Server log grew without bound during a run | Low | Size-rotated log (10 MiB, one previous copy) |
| Phase 8 report said Model 2 unavailability could not occur in connected mode | Low (documentation) | Corrected; verified connected |
| Disaster profiles differ only in labels | Medium | Documented; simulator redesign is out of scope |
| `RescueEnv` bypasses Model 1, transport and Model 2 | Medium | Documented in MARL_READINESS.md |
| No provider factory or artifact resolver for trained models | Medium | Documented in MODEL_PROVIDER_READINESS.md |
| PostgreSQL/PostGIS unverified | Medium | Not installed without authorization; documented |
| Backend errors log the exception type only, not the traceback | Low | Documented |
