# Phase 12I completion report: comparative evaluation and integration verification

2026-11-27. Exploratory, symbolic civilian search simulation, CPU. No training, no weight,
reward, environment or safety-gate changes, no retired or protected seeds. Artifacts:
`D:\SWARM-AID-DATA\runs\phase12\phase12i`.

> **Update (Phase 12I-FIX):** the mission-pause defect below is corrected; see
> `PHASE_12I_FIX_REPORT.md`. The text below records the pre-fix findings unchanged. 12I-7 remains
> partial because checkpoint compatibility is not established and learned operator-facing
> integration is disabled.

## Status

| Item | Status |
|---|---|
| 12I-1 owner decisions | Complete as a record; all pending |
| 12I-2 methodology (`cep-1`) | Complete; confirmatory part proposed only |
| 12I-3 scenario and metric review | Complete |
| 12I-4 matched baselines | Complete from the 900 recorded episodes; none rerun |
| 12I-5 reproducibility | Complete |
| 12I-6 statistics | Complete, exploratory |
| 12I-7 symbolic integration | **Partial: a mission-wide pause does not stop learned movement** |
| 12I-8 verification | Complete; full regression deferred |

## Main integration finding

In all six probe episodes, drones driven by the frozen policies kept moving (42–59 moves) after
the operator's mission-wide pause was accepted. The policy path issues its own one-tick movement
lease and consults neither mission status nor assignments, and a mission pause sets no per-drone
override. A per-drone pause does stop movement. SearchEnv itself builds no command agent, so
training and the 12H evaluation never exercised this path. Nothing was changed: editing the gate
adapter (`marl.py`) would also invalidate checkpoint identity, and it needs an owner decision.
Until fixed, the learned policies should not be connected to any operator-facing mission path.

Other integration results (see `integration_verification.json`):

- Missing sensors are flagged and hold movement; the safety gate refuses delayed frames.
- With the existing Model 2 attached by the probe, no incident or disposition became confirmed.
  Possible-human findings stayed unconfirmed. Recommendation evidence resolved to admitted
  findings, and dispositions were pending human review or expired.
- Not exercised: perception models (the path is symbolic), operator approval, backend, dashboard.

## Matched comparison

Coverage AUC (mean coverage over ticks 1–30, percent), 15 matched episodes per condition. This is
sensed coverage, not rescue outcomes. Independent is a weak comparator.

| Condition | IPPO | MAPPO | Shared info | IPPO − MAPPO, points |
|---|---:|---:|---:|---:|
| Nominal | 86.1 | 86.1 | 63.4 | −0.1 |
| Missing observations | 74.9 | 63.2 | 58.7 | +11.7 [6.4, 17.3] |
| Radio outage and partition | 67.1 | 51.5 | 56.4 | +15.6 [12.2, 19.8] |
| Message delay | 86.1 | 85.4 | 41.4 | +0.7 [0.6, 0.8] |

All ten conditions and all six policies: `comparison_tables.md`. Final coverage, reward-2, bytes,
rejections, vetoes, safety counts and termination: `matched_baseline_results.json`. Paired
differences in percentage points with median, range and win/tie/loss counts:
`statistical_analysis.json`. Per matched cell: `comparative_episode_metrics.csv`.

- Brackets resample evaluation episodes for two fixed policies. They say nothing about retraining,
  are unadjusted for many comparisons and support no superiority or equivalence claim.
- Nominal is saturated: both learned policies reach full coverage in 15 of 15 episodes, and those
  episodes contain only 5 (IPPO) and 4 (MAPPO) distinct coverage traces.
- Differences between the two policies appear mainly under missing observations and outage.
- Both exceed shared information in AUC in most conditions. MAPPO is below it under outage
  (−4.9 points), and its missing-observation interval against it crosses zero.
- Post hoc, excluding the immobile earthquake field cell, field coverage is 92–98% for IPPO,
  MAPPO and shared information.
- All episodes ended at the horizon; no blocked-cell or shared-cell occupancy was recorded.
- AUC is unavailable for 12G training and validation, which kept no tick traces.

Figure: `coverage_by_tick.svg` (rendered to PNG and visually inspected). It adds the time course,
which the 12G and 12H material did not show.

## Scenario and metric review

The pairing flaw (900 of 2,700 combinations) applied equally to both runs because both used
learner seed 1. It limits generality rather than favouring either. `authorize()` refuses movement
when the frame time differs from the current tick. That behaves as written and explains the
`earthquake_field` result (`latency: 2`). The learned path is also penalized for these refusals,
and `obs-1` carries no observation age.

## Further experiments (proposed, not started)

A nearest-unsearched heuristic is needed before concluding that learning is useful: the existing
heuristics follow assigned targets and plateau near 75%. It would serve only as a symbolic
research comparator, with the same observation limits and safety gate; it was not implemented.
Then a harder task and `cep-1`. Sequential CPU estimates at measured throughput: 1.4 h pilot
(3 seeds × 2 algorithms × 50k), 8.3 h (3 × 300k), 13.8 h (5 × 300k).

## Checks

Phase 12H and 12I fixtures: 12 passed, 0 failed, 0 skipped. Ruff (new files) and strict mypy
(`marl_compare.py`): passed. Full pytest, frontend checks and existing command/transport tests:
not run. Existing source files were not modified.

## Reproduce

```powershell
.\.venv\Scripts\python.exe -m evaluation.marl_compare analyze
.\.venv\Scripts\python.exe -m evaluation.marl_compare integration
```
