# End-to-end testing and the connected demonstration (Phase 9)

## Test architecture

| Category | Location | Resources | What it covers |
|---|---|---|---|
| Unit / contract | `tests/unit/`, `frontend/tests/unit/` | none | domain and message validation, frontend contracts against captured backend shapes, formatting, freshness, permissions, statistics, CSV safety, event buffer, transport client |
| Component | `frontend/tests/integration/` (jsdom) | stub provider | pages, decision flow, mode isolation |
| Integration, headless | `tests/integration/` incl. `test_system_integration.py`, `test_orchestration.py` | in-process | Model 1 → transport → Model 2 provenance, time and coordinates, peer delivery, task lifecycle, agent and Model 2 isolation (object graph), reproducibility, 12 fault fixtures, configuration validation, matrix runner, shutdown signal, log rotation |
| Integration, backend (SQLite) | `tests/backend_api/` incl. `test_system_backend.py` | disposable SQLite copy per test in the system temp folder | API, auth, oversight, WebSocket, recovery, exports; Phase 9: conflicting evidence, trace, evaluator keys on 12 endpoints, stop isolation, repeated lifecycles, graceful shutdown |
| PostgreSQL/PostGIS | `test_postgis_migration_geometry_and_spatial_query` | needs `SWARM_TEST_POSTGRES_URL` | reported as skipped (no server) |
| E2E synthetic | `frontend/tests/e2e/mock/` | Vite only | synthetic demo; asserts no `/api` or `/ws` request; axe scans |
| E2E connected | `frontend/tests/e2e/connected/` | running backend + dev accounts | Phase 8 workflows; Phase 9 Model 2 unavailability and conflicting evidence in the dashboard |
| Performance smoke | `frontend/tests/e2e/connected/performance.spec.ts` | `E2E_PERF=1` | skipped unless requested |
| Complete system | `scripts/system_demo.py` | running system from `start_system.ps1` | 33 steps + 3 verification steps after restart |
| Reproducibility / benchmark | `python -m orchestration matrix`, `evaluation.backend_benchmark` | in-process / isolated server | determinism, CPU baselines |

Tests never depend on unrelated running services: pytest builds its own applications and
databases, the mock e2e project uses only Vite, and the connected projects skip (reported as
skipped) without `E2E_PASSWORD`.

## Commands

```powershell
# backend (repository root)
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m alembic current

# frontend (frontend/)
npm run lint; npm run typecheck; npm run format:check; npm run test; npm run build
npm run test:e2e
$env:E2E_PASSWORD = "<dev password>"
npx playwright test --project=connected tests/e2e/connected/integration.spec.ts --workers=1
npx playwright test --project=connected tests/e2e/connected/backend.spec.ts tests/e2e/connected/performance.spec.ts --workers=1

# complete system
powershell -ExecutionPolicy Bypass -File scripts\start_system.ps1
.\.venv\Scripts\python.exe scripts\system_demo.py
powershell -ExecutionPolicy Bypass -File scripts\stop_system.ps1
powershell -ExecutionPolicy Bypass -File scripts\start_system.ps1
.\.venv\Scripts\python.exe scripts\system_demo.py --verify runs\phase9\demo\<report>.json
```

Run the two connected spec files a minute apart, or with one worker as shown: the backend's
login rate limit (10 per minute) is a security control and was not relaxed for testing. The
demonstration needs a free simulation slot (paused missions count toward
`SWARM_MAX_CONCURRENT_SIMULATIONS`); it refuses to start otherwise.

## Complete connected demonstration (flood, 6 agents, seed 42)

Report: `runs/phase9/demo/demo-20261124T154241Z.json` (phase 1: 33/33 steps; phase 2 after
`stop_system.ps1` and `start_system.ps1`: 3/3).

| # | Required step | Result |
|---|---|---|
| 1 | Single-command startup | `start_system.ps1`: 37 checks, backend and dashboard ready |
| 2–4 | Database, backend, dashboard | ready (SQLite, revision 0001); live/ready 200; dashboard 200 |
| 5 | Authorized login | coordinator |
| 6–7 | Mission creation, scenario and seed | `flood_basic`, 6 agents, seed 42 |
| 8 | Simulation start | 200; a second start refused (409 `duplicate_execution`) |
| 9 | Independent Model 1 initialization | agents d0–d5 registered |
| 10 | Actual agent observations | 30 by the first pause, all 6 agents reporting, all on `swarm-aid:grid` |
| 11 | Peer communication | 3,597 deliveries of 3,301 generated messages over the run (ratio 0.979); peer delivery asserted directly in the headless test |
| 12 | Cooperative coordination | 6 tasks, 6 sectors, 14 task events |
| 13 | Reports at Model 2 | 30 of 30 admitted |
| 14 | Evidence fusion | the reviewed incident fused 2 observations from 2 independent agents |
| 15 | Incident assessment | `uncertain_need`, `human_review_pending`, priority `elevated` |
| 16 | Supporting and contradicting evidence | 2 supporting; two authenticated agent reports with different hazards for one cell and instant → second shown as `conflicting` |
| 17 | Structured recommendation | `review_rescue_need`, version 2, unknowns listed, expiry 1200 ms |
| 18 | Authorized human review | observer refused (403); outdated version refused (409); idempotent resubmission returned the same decision |
| 19 | Persistent human decision | `accepted`, "validated by Model 2" |
| 20 | Dashboard synchronization | WebSocket events received live; trace shows 12 events for the reviewed report |
| 21–22 | Communication degradation and recovery | `COMMUNICATION_DEGRADED` ×2, `COMMUNICATION_RESTORED` ×2 (`flood_server_unavailable` + outage steps) |
| 23 | Model 2 unavailability | `MODEL_2_UNAVAILABLE` ×2 before `MODEL_2_RECOVERED` ×2 |
| 24 | WebSocket reconnection | 219 events, reconnect after sequence 220, replay from 221, no gaps |
| 25 | Measured metrics | persisted operational metrics per run |
| 26 | Authorized research export | researcher 200, observer 403, Git revision recorded |
| 27 | Pause and resume | two pauses and two resumes recorded in the mission history |
| 28 | Stop | `stopped` |
| 29 | Persistent record retrieval | 341 observations; incidents by disposition |
| 30 | Graceful system shutdown | held mission recorded `stopped`, reason "backend shutdown"; summary identical after restart; Model 2 memory restored with integrity |

Workflows not produced by `flood_basic` itself used existing deterministic fixtures
(`flood_server_unavailable` with outage steps) or the authenticated agent-report API
(contradicting reports). No connected-mode event was fabricated.

## Additional scenarios

Every registered scenario ran headless in the Phase 9 matrices (smoke and extended):
`flood_basic`, `flood_multiple`, `wildfire_basic`, `earthquake_basic`, `cyclone_basic`,
`landslide_basic` and the ten flood fault fixtures; scenario loading, agent initialisation,
observation flow, communication, coordination, Model 2 processing, termination and metrics were
recorded for each.
The connected demonstration used flood scenarios only; the headless start-script check also ran `wildfire_basic` with 10 agents. There is **no missing-person scenario**; none is claimed.
