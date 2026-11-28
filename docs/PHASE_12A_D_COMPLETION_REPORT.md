# Phase 12A-12D Completion Report

2026-11-27. Civilian search-and-rescue **simulation** only. No policy was trained; no physical control.

| Subphase | Status |
|---|---|
| 12A Readiness audit and seed isolation | Complete |
| 12B Environment interface | Complete |
| 12C Observation, action, reward contracts | Complete (weights untuned) |
| 12D Development baseline pilot | Complete |

## 12A findings

`Engine` and `Fleet` are reusable: per-agent memory, delayed/lossy network, safety gate, named seed streams.
An earlier PettingZoo `RescueEnv` (`simulation/adapters/parallel.py`) bypasses agents, memory and network; it is
unchanged and not the Phase 12 environment. Details: `readiness_audit.json`.

**Reserved seeds.** Seed 42 is exposed. Existing tests also execute 43 (`test_field_scenarios`), 44 and 45
(`test_system_integration`), and 46 is listed in the Model 2 pilot test split. The Phase 11J full-suite runs
executed 43-45; the 11J report mentioned only 42. Do not call 42-46 strictly unseen without owner review. This is
from source search and reports, not an exhaustive audit. In this phase those two tests were deselected.

New namespaces (`seeds-1`): development 12000-12999, validation 13000-13999, proposed final 900000-900099 (never
executed; needs owner approval). `SearchEnv` rejects all other seeds. Historical protocols are unchanged.

## 12B-12C contracts

- `SearchEnv` (PettingZoo `ParallelEnv`) wraps `Fleet`. One added hook: `Fleet.advance(override=...)`.
- Observation `obs-1`: float32, 240 values in [-1, 1]: own state, missing-sensor flags, 5x5 patch from the agent's
  own bounded memory and delivered peer findings, own search history. No ground truth, no future views.
- Action `action-1`: HOLD, NORTH, EAST, SOUTH, WEST (`Move` 0-4) with a public-information mask. HOLD keeps the
  agent's own observe/report/request behaviour, so reporting cannot be suppressed.
- Safety: policy moves pass `safety.authorize` and then engine vetoes. **Design choice to review:** in learning
  mode the env supplies a one-tick lease for the policy's move, replacing the command lease.
- Reward `reward-1` per agent: new team cell +0.1 (shared among first observers), redundant footprint -0.02 x
  fraction, first two-modality corroboration +0.01, resolved indistinct cell +0.05, rejected own action -0.1.
  Nothing rewards detecting or confirming people.

## 12D development baselines

Scenarios flood, wildfire, earthquake (basic); 6 agents; 30 ticks; seeds 12000-12002; 9 episodes per policy.
SD pools scenarios and seeds. These are development measurements, not research results.

| Policy | Coverage | Cross-agent duplicate cells | Network MB | Engine vetoes | Safety interventions | Reward |
|---|---:|---:|---:|---:|---:|---:|
| independent | 0.175 +/- 0.000 | 29.0 | 0.63 | 0.0 | 0 | -3.60 |
| fixed_sector | 0.752 +/- 0.013 | 107.6 | 0.83 | 24.2 | 49 | 4.13 |
| shared_information | 0.776 +/- 0.034 | 112.7 | 1.35 | 31.9 | 49 | 4.45 |
| random_masked (sanity only) | 0.605 +/- 0.138 | 121.4 | 1.27 | 45.6 | 0 | -2.41 |

All episodes ended at the horizon. Adapter and original runner matched exactly (coverage by tick, steps, vetoes,
readings, battery, bytes, safety) in 9 of 9 checks. Per-episode rows: `baseline_episode_metrics.csv`.

How to read this:

- `independent` issues no movement, so it is a stationary floor, not a search strategy.
- shared_information's coverage lead over fixed_sector (0.024) is within the pooled spread; no conclusion.
- Redundant footprint fraction is 0.96-1.00 for every policy, so it barely discriminates, and its penalty
  (about -3.5 for all) mostly offsets the coverage reward. Revisit before training.
- Resolved-uncertainty reward never fired: these scenarios have no sensing noise. Untested in the pilot.
- Safety interventions count the agents' own gate; policy rejections are counted separately.

## Performance (current workstation, `environment_profile.json`)

| Agents | Reset ms | Step ms | Env steps/s |
|---:|---:|---:|---:|
| 1 | 1.2 | 1.6 | 614 |
| 3 | 2.4 | 5.4 | 186 |
| 6 | 4.4 | 12.1 | 83 |
| 10 | 7.2 | 22.1 | 45 |
| 20 | 14.0 | 57.1 | 18 |

CPU-bound, single-threaded; peak RSS 106 MiB; torch is not imported. A GPU will not speed up the environment; a
trainer would need parallel environment processes. RTX 2060 performance is not measured.

## Verification

25 Phase 12 tests passed. Full suite: 397 passed, 0 failed, 1 skipped (PostgreSQL), 2 deselected (reserved seeds).
Ruff, strict mypy (affected modules), `pip check`, `git diff --check` passed. Not run: frontend checks.

Records: `D:\SWARM-AID-DATA\runs\phase12`. Source changes are uncommitted.
