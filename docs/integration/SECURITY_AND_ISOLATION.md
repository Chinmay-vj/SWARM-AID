# Security, isolation and research integrity (Phase 9 audit)

This is a local research-simulation audit, not a production security certification.

## Security mechanisms checked

| Mechanism | Implementation | Phase 9 evidence |
|---|---|---|
| Authentication | Argon2id passwords, 15-minute access JWT, 12-hour rotated refresh token (reuse rejected), login rate limit 10/min | backend auth tests; connected demo; login p50 61 ms (benchmark) |
| Machine identity | Per-mission, per-agent credentials exchanged for machine tokens; sender bound to agent key | conflicting-evidence test and demo used machine tokens; foreign agent refused (`not_member`) |
| Human identity and roles | Global role plus per-mission membership; deny-by-default permission matrix; administrators cannot decide without membership | observer decision refused (403) in demo and e2e; non-member trace refused (404) |
| Mission isolation | Every resource resolved through `owned()` / `mission_for()`; cross-mission access is 404 | `test_identical_scenarios_stay_isolated`, stop-isolation test, trace scope test |
| WebSocket authorization | token in the first frame (never the URL), membership checked, close 4401/4403 | `test_unauthenticated_and_unauthorized_connections_are_closed` |
| Input and message validation | Pydantic (extra fields forbidden), router session binding, Model 2 scope/freshness checks, Zod on the client | ingestion and contract tests; Phase 9 configuration tests |
| File references | scenario IDs whitelisted; evidence by content hash and object ID; no client paths | `test_scenario_identifiers_cannot_reach_the_filesystem`; path-traversal mission config rejected |
| Secrets | `SWARM_JWT_SECRET` mandatory, never logged; `.env` and `runs/` git-ignored; `orchestration check` reports lengths only and flags secret-like `VITE_*` names | `test_configuration_errors_never_echo_values`; manifest test (no secrets) |
| Error redaction | structured codes, request ID, no stacks or bodies | `test_errors_are_structured_and_leak_nothing` |
| Session cleanup | logout revokes refresh token; mode switch clears client caches | frontend integration tests |
| CSV export safety | client-side formula neutralisation | frontend unit tests (backend CSV is not neutralised: open item) |
| Audit | sensitive actions recorded with actor | `test_exports_separate_ground_truth_and_are_audited` |
| Local binding | backend and dashboard on 127.0.0.1; start script refuses to touch foreign processes | executed |
| Process control | stop signal file under `runs/system`; ownership by PID and start time | executed |

Unauthorized-access attempts in Phase 9 used isolated test accounts (pytest) and the local
development accounts against the development database only.

**Findings:** no critical or high security defect found. Open items (medium/low): backend CSV
exports are not formula-neutralised server-side; the stop-signal file can be written by any
local account with access to `runs/system`; dependency advisories for react-router (v7-only
fix) and zod (v4-only fix) remain from Phase 8; PostgreSQL deployment hardening is unverified.

## Research evaluator isolation

Evaluator-only information: people positions and visibility, hazard truth, evaluator coverage
(`coverage`), `people_observed`, `missed`, `false_positive`, first capture times, scenario truth
labels.

| Boundary | Check | Result |
|---|---|---|
| Model 1 perception, memory, reasoning, planning | Object-graph walk from each `DroneAgent` (`tests/integration/test_system_integration.py`): no `Engine`, `Person`, `Hazard`, `Drone` or `SimulationContext` reachable | pass |
| Model 1 private memory | No other agent's `DroneAgent` or `Memory` reachable from any agent | pass |
| Model 2 | No ground-truth object or Model 1 private state reachable from `CommandAgent` | pass |
| Coordination | `Baseline.target` receives `MissionContext` and agent-reported cells only | by construction; reported and evaluator coverage are separate outputs |
| Operational API | Key scan of 12 operational endpoints plus the event log for a completed mission (`tests/backend_api/test_system_backend.py`) | no evaluator keys |
| Observation trace | key scan | no evaluator keys |
| Research export | researcher membership required; observer 403; ground truth labelled "for evaluation only" | pass (demo and tests) |
| Headless results | `operational` and `evaluator_only` sections; evaluator section carries a warning | tested |
| Dashboard | synthetic metrics labelled; connected analytics use measured exports only | Phase 8 tests |

The engine does give each agent its **own** sensor packet, which is derived from ground truth
through noise, misses, dropout and false positives. That is the intended simulated sensing path,
not leakage.

Hidden ground truth is never used to improve operational decisions.

## Human-centred safety

| Requirement | Status |
|---|---|
| Operators see only authorized reported information | verified (role and mission scope) |
| Unknown stays unknown | missing confidence, location and heartbeat render as unknown/not reported (tested) |
| Stale information marked | 1.5 s freshness; stale observations and agents flagged |
| Conflicting evidence visible | **fixed in Phase 9**; verified in the dashboard against the real backend |
| Uncertainty visible | incident uncertainties and recommendation unknowns shown |
| Confidence not confused with urgency | separate fields and displays |
| Possible sightings not auto-confirmed | `human_confirmed` requires a human decision reference |
| Synthetic data labelled | banner and badges; no `/api` or `/ws` calls in synthetic mode (tested) |
| Recommendations are decision support | "submitted" until Model 2 validates; approval is not a rescue outcome |
| Human review enforced | review requests require an exact-version decision by a permitted role |
| Independent Model 1 safety validation | active for every action and lease; interventions counted |
| No physical drone controls | none exist (no hardware, flight-controller or MAVLink code) |
| No real-world autonomous rescue execution | none exists |

## Simulation versus real-world capability

Everything verified in Phase 9 is a property of a symbolic grid simulation with mock sensors and
deterministic rule-based agents. Nothing here demonstrates real-world perception accuracy,
flight safety, communications performance in a disaster, or rescue effectiveness, and no such
claim is made.
