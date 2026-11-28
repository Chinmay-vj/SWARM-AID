# Phase 12I-FIX report: mission-wide operator pause

2026-11-27. Symbolic civilian search simulation only. No training, no weight, reward or
checkpoint changes, no reserved or protected seeds executed. Artifacts:
`D:\SWARM-AID-DATA\runs\phase12\phase12i_fix`.

## Root cause

A mission-wide operator pause changed the assignment record, which only stopped **new**
assignments. Nothing enforced mission status at the movement step, and a mission override sets no
per-drone override. The learned path (`marl.py`, `_gate`) issues its own one-tick lease, so it kept
moving. Heuristic coordination also kept moving until old leases expired, which Phase 12I had not
reported. Backend simulation contexts use the same `Fleet` step (established by reading the code).

## Correction

In `simulation/adapters/model1.py`, `Fleet.advance` now applies a last check before the engine,
whenever the fleet has a command agent (operator-facing):

- Travel moves become hold unless the assignment record exists and its status is `active`
  (fails closed on pause, end, degraded or missing record).
- Caller-supplied policies cannot travel at all unless `allow_external_policy` is set. It defaults
  to `False` and only verification code sets it.

Non-travel actions and the existing safety gate are unchanged. Resume still requires an operator
override with the checked revision. `marl.py` was not edited. `marl_compare.py` now refuses to
overwrite the pre-fix probe.

## Before and after

Moves in steps where the mission was paused (pause issued at tick 3, 27 paused steps, seeds
12960–12962, three scenarios):

| Path | Before | After |
|---|---:|---:|
| IPPO | 47–65 | 0 |
| MAPPO | 53–62 | 0 |
| Fixed sector | 7–10 | 0 |
| Shared information | 7–10 | 0 |
| IPPO and MAPPO, default (disabled) | — | 0 moves at any time |

Individual drone pause remains effective (fixture). Phase 12I's counts (42–59) came from a
different probe configuration and are preserved unchanged.

## Checkpoint compatibility

- All four checkpoint files match their 12G hashes.
- 20 replayed episodes (flood, seed 13100, ten conditions, both policies, no command agent) match
  the recorded 12H metrics exactly. The new code is inactive without a command agent.
- The launcher's identity check still passes, but it hashes only `marl.py`, `marl_contract.py` and
  `marl_ppo.py`. **It cannot see this correction**, so its pass does not establish compatibility.

**Status: compatibility with the corrected runtime is not established.** Learned operator-facing
integration stays disabled pending an owner decision. Offline SearchEnv evaluation is unaffected.

## Integration checks after the fix

With the existing Model 2 attached and the policy enabled for verification (six episodes): no
confirmed incident, recommendation evidence resolved to admitted findings, dispositions only
pending human review or expired. Missing observations remain flagged and hold movement.

Not exercised: perception models, the backend operator-pause route, dashboard, and operator
approval with a learned policy.

## Checks

- Phase 12I fixtures: 9 passed. The characterization test was replaced by enforcing tests; the
  old file is saved as `test_phase12i.before.py.txt`. Two new tests first failed on wrong
  expectations (mission marked completed at the horizon; a fixture with no heuristic movement);
  the zero-movement assertions were not relaxed.
- Full suite: 427 passed, 0 failed, 3 skipped (PostgreSQL; two reserved-seed tests).
- Seed isolation: a test-only guard redirected 313 engine resets from reserved seeds (mostly the
  default 42) to development seeds 12800–12804. It covers engine execution, not code that uses
  those numbers without the engine.
- Ruff and strict mypy (affected files), `git diff --check`: passed. Frontend: not run.

The default scenario seed is still 42, so an unguarded test run executes it. Earlier full-suite
runs did so.

## Open blockers

1. Owner decision on checkpoint compatibility (for example, record `model1.py` and the engine,
   safety and sensor sources in a new identity version).
2. Standalone SearchEnv and fleets without a command agent have no mission authority; the
   movement-lease decision is still pending.
3. Backend operator-pause route not verified end to end.
4. Default seed 42 in tests and configuration.
