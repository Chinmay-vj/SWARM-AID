# Phase 12J completion report: final verification and closure

2026-11-27. Symbolic civilian search simulation, CPU. No training, no checkpoint, reward,
scenario or production safety changes, no protected seeds. Artifacts:
`D:\SWARM-AID-DATA\runs\phase12\phase12j`.

| Item | Status |
|---|---|
| 12J-1 checkpoint compatibility | Assessed; **not established** |
| 12J-2 backend operator authority | Passed on SQLite, with limits |
| 12J-3 seed isolation | Complete for tests; production default unchanged |
| 12J-4 safety and integration | **Partial** |
| 12J-5 limitations and decisions | Complete; all decisions pending |
| 12J-6 quality checks | Run; one project mypy failure |
| 12J-7 documentation | Complete |

## Checkpoint compatibility

The launcher identity hashes three sources (`marl.py`, `marl_contract.py`, `marl_ppo.py`) plus
configuration and contract versions. The import closure holds 23 further modules (excluding
package files) that it does not hash, including the engine, sensors, safety gate, drone agent,
communications and the corrected `model1.py`. Scenario and `model1.json` files are also unhashed.

The 20 exact replays from 12I-FIX show identical offline metrics for both `latest.pt` on flood,
seed 13100, ten conditions. They do not cover other scenarios or seeds, `best.pt`, command-agent
behaviour, or retraining. Training-time content of unhashed files was never recorded.

Proposed record (`compat-1`) keeps separate: file integrity (pass), historical reproducibility
(not established), offline evaluation (pass for the sample), corrected runtime (not established)
and operator-facing use (not authorized, disabled). No check was altered.

## Backend operator authority

`tests/backend_api/test_operator_authority.py` drives the real application and mission loop:

- An override pause is accepted and reaches mission state; no drone moved in any paused tick.
- Pausing and resuming execution does not resume the mission; only an operator override does, and
  movement returned after it.
- An observer can neither pause nor resume. A missing assignment record blocks movement.
- Learned policies are disabled in backend contexts.

Limits: SQLite only; a tick already in flight may finish after the execution `/pause` returns (by
code, not measured); there is **no backend per-drone pause route** (per-drone pause is verified at
simulator level only).

## Seed isolation

Tests now assign the default seed 42 a development seed (12800), refuse 43–46 and always refuse
900000–900099, including in Python child processes. Verified with a fake engine; no protected
scenario ran. `SWARM_ALLOW_LEGACY_RESERVED_SEEDS=1` still permits 42–46 deliberately. Production
defaults are unchanged, so demo scripts, connected end-to-end runs and manual CLI runs still use
seed 42. Correction to 12I-FIX: all 313 redirects there were seed 42.

## Integration status

| Component | Status |
|---|---|
| Offline symbolic evaluation | PASS (sampled) |
| Command-agent integration | PARTIAL |
| Backend operator-pause route | PASS (SQLite) |
| PostgreSQL | NOT TESTED |
| Perception models | NOT TESTED |
| Dashboard | NOT TESTED |
| Operator approval workflow | PARTIAL (not with a learned policy) |
| Learned operator-facing integration | BLOCKED |

Mission and individual pause, missing-observation holds, unconfirmed person detections and human
review of recommendations rest on 12I-FIX fixtures and probes, which are in the suite or reused.

## Checks

- Full suite: 436 passed, 0 failed, 3 skipped (PostgreSQL; two retired-seed tests).
- Ruff (repository), strict mypy (`model1.py`, `seed_guard.py`), `git diff --check`: passed.
- Project `mypy`: **6 errors** in `tests/unit/test_phase11_model1.py`, which this work did not
  modify. Not fixed.
- Not run: frontend checks, PostgreSQL, pip check (no dependency change).

## Files

Added `tests/seed_guard.py`, `tests/child_guard/sitecustomize.py`,
`tests/unit/test_seed_isolation.py`, `tests/backend_api/test_operator_authority.py`, this report,
the final report and the Phase 13 handoff. Modified `tests/conftest.py` and the progress file.
No production source changed.
