# Phase 9 completion report: complete system integration

Date: 2026-11-24. Branch `main` at `ce0ef30` (tag `v0.8.0`) plus uncommitted Phase 9 changes.
Nothing was committed, tagged or pushed; Git finalization waits for the independent Phase 9
audit. Phase 10 was not started.

## 1. Overall status

**READY WITH LIMITATIONS.** The integrated stack (simulator, independent Model 1 agents,
simulated communication, coordination, Model 2, backend, database, event stream, dashboard and
evaluator) starts with one command, runs a complete connected six-agent flood demonstration
(33/33 steps, plus 3/3 after a scripted shutdown and restart), stays deterministic across
processes, keeps evaluator data isolated, and passes every executed automated test. One
high-severity integration defect (conflicting evidence hidden from operators) was found and
fixed. Limitations that remain are listed in §30; none is critical or high.

## 2. Previous-phase audit findings

| Finding | Severity | Action |
|---|---|---|
| Model 2 flagged contradicting reports, but the backend stored every evidence link as "supporting"; operators always saw 0 conflicting observations | High | Fixed in `model2_adapter.py`; regression test; connected e2e |
| Phase 8 report: "Model 2 unavailability can't be produced by the real backend" | Low (documentation) | Wrong: `Fleet.advance` sets Model 2 `offline` during command-endpoint outages and the backend emits the events; correction notes added; verified connected |
| No single-command startup, status or safe shutdown; Phase 8 `start_dashboard.ps1` started unowned processes | High (mandatory workflow) | `start_system.ps1`, `status_system.ps1`, `stop_system.ps1`, `orchestration serve` |
| Disaster profiles differ only in labels; wildfire and flood simulate identically for the same seed; cyclone equals flood; landslide equals earthquake | Medium | Documented (simulator design, Phase 2 scope) |
| No missing-person scenario exists | Medium | Documented; none claimed |
| `RescueEnv` (PettingZoo) bypasses Model 1, transport, coordination and Model 2 | Medium | Documented (MARL_READINESS.md) |
| `configs/default.toml` and `configs/model2.json` are not read by the runtime paths | Low | Documented; the configuration check reports their role |
| Backend logs record exception types without tracebacks | Low | Documented |

Phases 1–8 otherwise behaved as their reports state; the Phase 8 baseline was reproduced before
any change (backend 176 passed / 1 skipped; frontend 77 unit, 12 mock e2e).

## 3. Integrated architecture

See `docs/integration/SYSTEM_ARCHITECTURE.md` (14 Mermaid diagrams: integrated system,
dependencies, startup, mission lifecycle, Model 1 flow, Model 1–Model 2 interaction,
communication, provenance, human review, persistence, WebSocket synchronization, failure
recovery, evaluator isolation, planned trained-provider integration). Responsibilities are
unchanged. Phase 9 added `orchestration/`, which composes the existing components and does not
replace `RuntimeManager`, Model 1 or Model 2.

## 4. Component inventory

`docs/integration/COMPONENT_INVENTORY.md`: 27 components. Verified 19, partially verified 4
(disaster profiles, PettingZoo env, evidence object store; Pygame viewer at smoke level is
counted as verified), synthetic only 2 (mock sensors, synthetic dashboard), implemented but
unverified 2 (PostgreSQL/PostGIS, legacy MVP), defective 0 after the fix, incompatible 0,
missing 1 (missing-person scenario).

## 5. Files created and modified

Created:

- `orchestration/` (`__init__.py`, `__main__.py`, `checks.py`, `headless.py`, `manifest.py`,
  `matrix.py`, `serve.py`, `status.py`)
- `scripts/start_system.ps1`, `scripts/status_system.ps1`, `scripts/stop_system.ps1`,
  `scripts/system_demo.py`
- `configs/experiments/phase9_smoke.json`, `configs/experiments/phase9_extended.json`
- `tests/integration/test_system_integration.py`, `tests/integration/test_orchestration.py`,
  `tests/backend_api/test_system_backend.py`, `frontend/tests/e2e/connected/integration.spec.ts`
- `docs/integration/` (SYSTEM_ARCHITECTURE, COMPONENT_INVENTORY, SYSTEM_OPERATIONS,
  INTEGRATION_CONTRACTS, FAILURE_RECOVERY, END_TO_END_TESTING, SECURITY_AND_ISOLATION)
- `docs/research/` (REPRODUCIBILITY_GUIDE, CPU_BASELINE_BENCHMARKS, METRIC_DEFINITIONS,
  MODEL_PROVIDER_READINESS, MARL_READINESS, DATASET_COLLECTION_READINESS)
- `docs/PHASE_9_COMPLETION_REPORT.md`, `docs/PHASE_10_READINESS_CHECKLIST.md`

Modified:

- `backend/integrations/model2_adapter.py`: conflicting-evidence role copied from Model 2
- `backend/services/queries.py`, `backend/schemas.py`, `backend/api/v1/agents.py`: observation
  trace endpoint
- `backend/integrations/runtime.py`: `git_commit` delegates to `orchestration.manifest`
- `scripts/start_dashboard.ps1`: now forwards to `start_system.ps1` (same switches)
- `pyproject.toml`: `orchestration` package and mypy path
- `README.md`, `AGENTS.md`, `docs/PHASE_8_COMPLETION_REPORT.md` (correction notes),
  `docs/frontend/API_INTEGRATION.md`

No dependency was added or upgraded. Local, git-ignored outputs: `runs/phase9/`,
`runs/system/`, `runs/backend/benchmark-20261124T154812Z/`.

## 6. System orchestration

`python -m orchestration` provides `check`, `run`, `matrix`, `experiment`, `serve` and
`status`. Headless runs build the same `SimulationContext` as the backend. Mission lifecycle
stays in `RuntimeManager` (one owner; duplicate starts refused). The backend process started by
the scripts is `orchestration serve`, which turns a stop-request file into uvicorn's graceful
exit and writes a size-rotated log.

## 7. Startup and shutdown verification

- `start_system.ps1`: 37 configuration checks, migration, backend ready, dashboard ready; a
  second invocation started nothing ("already running (started by this script)"); with output
  redirected it returns in 8 s (fixed: earlier, inherited console handles blocked a redirected
  run until the services exited).
- `status_system.ps1`: managed PIDs, live/ready probes, database revision, active missions.
- `stop_system.ps1`: five graceful cycles; backend log shows "Application shutdown complete";
  held missions recorded `stopped` with reason "backend shutdown"; ports free; no Python or Node
  process left; a foreign process on a port is reported and left running.
- `-Headless` profile: `wildfire_basic`, 10 agents, seed 43, completed (34 checks first).

## 8. Mission lifecycle

draft → running → paused → running → stopped/completed/failed verified through the API, the
dashboard (Phase 8 e2e) and the demo; duplicate start (409 `duplicate_execution`), stop after
stop (409) and start of a non-draft mission are refused; history is persisted with actor and
reason; stopping one mission left another running to completion (test); four repeated
create/start/stop cycles left no active runtime.

## 9. Model 1 integration

One `DroneAgent` per drone with its own memory (distinct objects, tested). An object-graph walk
from each agent reaches no `Engine`, `Person`, `Hazard`, `Drone`, `SimulationContext`, other
agent or other agent's memory. Every admitted Model 2 finding traces to a transport message
from its agent, with evidence origin equal to that agent. Safety interventions are counted in
every run; provider failures put the agent in HOLD.

## 10. Communication integration

Peer-to-peer deliveries between drones occur under shared information (tested). Twelve fault
fixtures complete without failure: loss (delivery ratio 0.62), delay, duplicate, reorder,
partition, agent disconnection, server outage, extended outage, unavailable agents, missing
modalities, stale reports (72 of 72 refused) and noise. Connected: degradation and restoration
events, 3,597 deliveries of 3,301 generated messages in the demo (ratio 0.979).

## 11. Coordination integration

Independent, fixed-sector and shared-information baselines ran 5 seeds each (matrix block
"coordination"); task histories are time-ordered with no activity after a terminal state;
agent-reported and evaluator coverage are separate outputs; the demo showed 6 tasks, 6 sectors
and 14 task events.

## 12. Model 2 integration

Model 2 receives real Model 1 reports (30/30 admitted by the demo's first pause; 174 admitted
findings in a headless 6-agent run); incidents cite only admitted reports; recommendations
carry the incident revision; stale reports are refused; unavailability and recovery are emitted
and displayed; contradicting reports are flagged and (after the fix) shown as conflicting;
Model 2 memory restored from checkpoint with integrity after restart. The three Model 2 modes
(direct, rules, fusion) ran in the matrix.

## 13. Human oversight

Exact-version approval accepted and "validated by Model 2"; outdated version 409
`stale_version`; duplicate submission returned the same decision; observer 403; non-member 404;
persistent decision and audit record; dashboard synchronised through events. Approval is never
presented as a rescue outcome.

## 14. Backend integration

All endpoints exercised by 59 backend tests plus the demo; new trace endpoint; health and
readiness probes; system health reports active simulations, WebSocket counts and failures.

## 15. Database persistence

SQLite: transactions per tick, rollback with cursor restore (failure injection test), duplicate
and idempotency constraints, cross-mission 404, restart persistence (summary identical before
and after restart). Alembic head `0001`. PostgreSQL/PostGIS: not verified (skipped test; no
server installed, no authorization requested to install one).

## 16. WebSocket integration

Authentication in the first frame, mission subscription and isolation, ordered delivery,
heartbeats, slow-client cut-off with resync instruction, replay after reconnection (demo: replay
from 221 after 220, no gaps), cleanup on shutdown. Delivery under load: p50 50–72 ms, p95
158–482 ms (3–20 agents). At-least-once with client de-duplication; exactly-once is not claimed.

## 17. Dashboard integration

10 connected browser tests pass against the running backend (8 Phase 8 workflows plus Phase 9
Model 2 outage display and conflicting-evidence display); 77 unit/component tests; 12
synthetic e2e tests with accessibility scans.

## 18. Synthetic-mode isolation

Synthetic mode makes no `/api` or `/ws` requests (mock e2e assertion); mode switching signs out
and clears caches; connected failures are shown, never replaced by synthetic data; synthetic
decisions cannot reach the backend; synthetic metrics are labelled and not mixed with exports.

## 19. Failure recovery

`docs/integration/FAILURE_RECOVERY.md`: 15 failure categories with detection, visibility,
recovery, persistence and manual steps; all 20 required fault scenarios exercised (table with
test references). Recovery: history, metadata, Model 2 memory and event stream yes; Model 1
state and exact simulation continuation no.

## 20. Security findings

No critical or high security defect. Medium/low: backend CSV not neutralised server-side; the
stop file is writable by local accounts with access to `runs/system`; react-router and zod
advisories carried from Phase 8; PostgreSQL hardening unverified. No security mechanism was
disabled or relaxed (the login rate limit was respected during testing).

## 21. Evaluator isolation

Object-graph tests for Model 1 and Model 2; key scan of 12 operational endpoints and the event
log; trace endpoint scan; research export restricted to researchers and labelled; headless
results separate `operational` from `evaluator_only`. No leakage found.

## 22. Reproducibility

Identical operational fingerprints for 30/30 matrix repeats and across separate processes with
different `PYTHONHASHSEED`; different seeds differ. Manifests record Git revision (with
`-dirty`), configuration digest, environment and package versions. Wall-clock values and UUID4
identifiers are not reproducible and are documented as such.

## 23. Benchmark results (measured)

Headless integrated step time, median (p95 max): 1 agent 2.6 ms (5.6), 3: 8.9 (18.3), 6: 19.7
(35.5), 10: 35.7 (84.2), 20: 96.8 (203.7). Backend ingestion through Model 2, p50/p95: 168/592
ms (3 agents), 508/1380 (6), 571/1819 (10), 639/1436 (20), 0 errors. Login p50 61 ms; cold start
2.11 s; restart to ready 2.08 s; server peak working set 315 MB. Full tables:
`docs/research/CPU_BASELINE_BENCHMARKS.md`. Not scalability claims.

## 24. Backend test totals

| Command | Exit | Result |
|---|---|---|
| `python --version` | 0 | Python 3.12.10 |
| `python -m pip check` | 0 | No broken requirements found |
| `python -m pytest -q` | 0 | **217 passed, 1 skipped** (PostgreSQL/PostGIS test, no server), 3 warnings (deprecations in third-party packages); baseline was 176 passed, 1 skipped |
| `python -m ruff check .` | 0 | All checks passed |
| `python -m ruff format --check .` | 0 | 251 files already formatted |
| `python -m mypy` (strict) | 0 | no issues in 124 source files |
| `python -m alembic current` | 0 | `0001 (head)` |
| `python -m orchestration check` | 0 | 37 checks, 0 errors, 0 warnings |

New tests: 20 headless integration (`test_system_integration.py`), 15 orchestration
(`test_orchestration.py`), 6 backend (`test_system_backend.py`). Collected: 59 backend API,
116 integration, 43 unit.

## 25. Frontend test totals

Node.js 23.11.0, npm 10.9.2.

| Command | Exit | Result |
|---|---|---|
| `npm run lint` | 0 | 0 warnings |
| `npm run typecheck` | 0 | clean |
| `npm run format:check` | 0 | clean |
| `npm run test` (Vitest) | 0 | **77 passed** (5 files) |
| `npm run build` | 0 | built |
| `npm run test:e2e` (mock) | 0 | **12 passed** (synthetic, accessibility, responsive) |

## 26. Connected end-to-end totals

- Playwright connected: 10 passed, 1 skipped (performance spec, gated by `E2E_PERF`; it passed
  in Phase 8 and was not re-run). Phase 9 spec 2/2; Phase 8 spec 8/8.
- Complete system demonstration: 33/33 steps; post-restart verification 3/3.
- Matrices: smoke 7/7 completed, determinism 7/7; extended 134/134, determinism 30/30.
- Phase 5 and Phase 6 runners via `orchestration experiment`: 18 and 45 episodes completed.
- Backend benchmark: 0 errors across all series.

## 27. Lint and type checks

Ruff check and format clean; strict mypy clean (see §24 for file count); ESLint (0 warnings),
TypeScript strict typecheck and Prettier clean.

## 28. Production build

`npm run build` succeeded (Vite). The backend has no build step.

## 29. Bugs corrected

1. Conflicting evidence persisted as supporting (High): fixed, regression test (fails without
   the fix), connected e2e.
2. Start script blocked when its output was redirected (Medium): services now start without
   inherited handles; the server writes its own log.
3. Unbounded server log during a run (Low): size-rotated (10 MiB, one previous copy), tested.
4. Phase 8 documentation error about Model 2 unavailability (Low): corrected.

Demonstration-script mistakes found and fixed during development (an invalid WebSocket topic,
a horizon too short to stop, and a check that read the first metrics event) were defects in the
new script, not in the system; they are not counted above.

## 30. Remaining limitations

- PostgreSQL/PostGIS unverified.
- Disaster profiles differ only in labels; no missing-person scenario.
- Simulations cannot resume after a backend restart; Model 1 state is not persisted.
- `RescueEnv` bypasses the integrated stack.
- No provider factory, artifact resolver or provider versioning for trained models.
- Evidence media never uploaded by the simulator.
- The simulator rarely produces contradicting reports on its own; conflicts were exercised
  through the agent-report API.
- Paused missions occupy simulation slots (limit 2 by default).
- Per-stage tick latencies and CPU utilisation not instrumented.
- Backend logs lack tracebacks; Vite log not rotated; stop signal file not access-controlled.
- Overview page polls about 8–9 requests per second (Phase 8).
- Manual screen-reader testing still not done (Phase 8).
- Node.js 23.11 (not LTS) was used for verification.

## 31. Future Model 1 readiness

Ports and validation ready; gaps: provider factory and configuration, artifact resolver,
uncertainty field, provider version in records (`docs/research/MODEL_PROVIDER_READINESS.md`).

## 32. Future Model 2 readiness

Assessment, urgency and recommendation ports injectable; independent guards stay outside
learned providers; gaps: factory, versioning, provenance of which provider produced a revision.

## 33. MARL readiness

PettingZoo API test passes; deterministic reset; injected reward (0 by default); gaps: env over
the integrated stack, richer versioned observations, per-episode communication conditions,
`INACTIVE` action policy, vectorised runner (`docs/research/MARL_READINESS.md`).

## 34. Dataset collection readiness

Specification written (`docs/research/DATASET_COLLECTION_READINESS.md`): datasets needed per
consumer, metadata, labels, licensing, privacy, splits and leakage prevention, storage. No data
was collected.

## 35. Verified startup commands

```powershell
cd D:\SWARM-AID
powershell -ExecutionPolicy Bypass -File scripts\start_system.ps1
powershell -ExecutionPolicy Bypass -File scripts\status_system.ps1
powershell -ExecutionPolicy Bypass -File scripts\stop_system.ps1
powershell -ExecutionPolicy Bypass -File scripts\start_system.ps1 -Headless -Scenario flood_basic -Agents 6 -Seed 42
.\.venv\Scripts\python.exe -m orchestration check
.\.venv\Scripts\python.exe -m orchestration matrix --config configs\experiments\phase9_smoke.json
.\.venv\Scripts\python.exe scripts\system_demo.py
```

## 36. Dashboard URL

http://127.0.0.1:5173 (backend http://127.0.0.1:8000, API docs http://127.0.0.1:8000/docs).
Development accounts: `admin`, `coordinator`, `operator`, `researcher`, `observer`; the password
is in the git-ignored `runs/backend/dev-credentials.env`.

## 37. Phase 10 readiness

`docs/PHASE_10_READINESS_CHECKLIST.md`. **READY WITH LIMITATIONS**: the platform can support
dataset work; dataset inventory, licence review and label schema are Phase 10 decisions, and
PostgreSQL remains unverified.

## Safety statement

No dataset was collected, no model was trained, no weights were downloaded, no GPU, paid API or
cloud service was used, and no physical drone-control or real-world rescue functionality exists.

## Git status

Uncommitted on `main`. Do not stage `.venv/`, `node_modules/`, `.env`, `runs/` (local
databases, logs, benchmark and demo outputs), `frontend/test-results/` or `frontend/dist/`; all
are git-ignored. Commit after the independent Phase 9 audit; `v0.9.0` not created.
