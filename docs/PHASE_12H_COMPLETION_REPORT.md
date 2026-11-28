# Phase 12H completion report: validity, robustness and optimization assessment

2026-11-27. Symbolic civilian search simulation, CPU. No training, no weight or reward changes,
no retired or protected seeds. Artifacts: `D:\SWARM-AID-DATA\runs\phase12\phase12h`. Phase 12G
results are preserved unchanged.

## Status

| Item | Status |
|---|---|
| 12H-1 coverage saturation | Complete |
| 12H-2 diversity and validity | Complete |
| 12H-3 checkpoint selection | Complete |
| 12H-4 frozen-policy robustness | Complete, with the limits below |
| 12H-5 reward and uncertainty | Complete |
| 12H-6 reproducibility protocol | Complete; proposed, not approved |
| 12H-7 training decision | Complete |
| 12H-8 verification and documents | Complete; full regression not run |

## Coverage saturation (12H-1)

Coverage is the union, over agents and ticks, of cells within Manhattan radius 2 of a drone while
a spatial sensor reported, divided by **all** grid cells (120 in basic scenarios). Restricted and
blocked cells are included and there is no occlusion. It is counted at capture, independent of
delivery, resets each episode and is not rounded. No implementation defect was found.

The saturation is real completion of an easy task. Six agents start at 17.6%, reach 93.5% by
tick 10 and 99% at tick 12 on average, with a 30-tick horizon. Accessible-cell coverage is also
1.0, so counting blocked cells does not explain it. Low scenario variation contributes. No
observation leakage was found by inspection and one hidden-obstacle fixture (not exhaustive). The
`unsearched_dx/dy` observation fields may make navigation easy; this is an untested hypothesis.
Coverage measures sensed footprint, not people found, reports received or a search region.

## Scenario diversity (12H-2)

- 900 seed–scenario pairs instead of 2,700: the 900-seed cycle divides by the 3-scenario cycle.
  The pairing also shifts with the learner seed, confounding the two.
- The 900 layouts are distinct only in a narrow sense. In flood and wildfire all 300 share one
  start set and one blocked map; only people and hazard cells vary. Earthquake has 7 start sets
  and 292 blocked maps. People do not affect coverage or reward.
- No training layout is identical to a validation layout, but 6 of 9 validation episodes share
  starts and blocked map with training. Seed ranges do not overlap.
- Seeds 13100–13104 used here are now exposed.

## Checkpoint selection (12H-3)

`best.pt` requires strictly higher mean validation coverage. Coverage hit 1.0 at update 30, so
later ties never replaced it: 53 IPPO and 26 MAPPO validation points tie at 1.0, and nearly all
later ones have higher reward and fewer invalid moves. `latest.pt` is the provisional candidate
(chosen after seeing the results). Proposed for future runs: fix the rule first; reject blocked
cell occupancy; select on coverage AUC; break ties by rejected moves, reward, then later step; use
separate selection and reporting seeds.

## Robustness (12H-4)

900 episodes: 10 conditions × 3 scenarios × 5 seeds (13100–13104) × 6 policies, 6 agents,
horizon 30, greedy `latest.pt`. Mean coverage over 15 episodes (SD in parentheses for learned
policies; episode variation, **not** learner variation):

| Condition | IPPO | MAPPO | Independent (weak) | Fixed sector | Shared info | Random |
|---|---:|---:|---:|---:|---:|---:|
| Nominal | 1.000 (0.000) | 1.000 (0.000) | 0.176 | 0.753 | 0.773 | 0.617 |
| Missing observations, dropout 0.2 | 0.919 (0.071) | 0.737 (0.153) | 0.176 | 0.735 | 0.747 | 0.627 |
| Noisy detections | 1.000 (0.000) | 0.997 (0.009) | 0.176 | 0.753 | 0.902 | 0.617 |
| Message loss 0.35 | 1.000 (0.000) | 0.999 (0.004) | 0.176 | 0.746 | 0.754 | 0.619 |
| Delay 3, jitter 2 | 1.000 (0.000) | 0.990 (0.005) | 0.176 | 0.632 | 0.631 | 0.617 |
| Radio outage and partition | 0.937 (0.037) | 0.648 (0.156) | 0.176 | 0.736 | 0.746 | 0.532 |
| One agent disconnected | 0.999 (0.002) | 0.998 (0.005) | 0.176 | 0.753 | 0.773 | 0.641 |
| One agent unavailable | 0.999 (0.002) | 0.998 (0.005) | 0.168 | 0.749 | 0.770 | 0.574 |
| Field scenarios | 0.688 (0.350) | 0.703 (0.357) | 0.213 | 0.631 | 0.684 | 0.523 |
| Field, noise 0.3 | 0.696 (0.354) | 0.726 (0.373) | 0.213 | 0.631 | 0.699 | 0.523 |

- Dropout and outage show gaps between the two trained runs (paired IPPO − MAPPO coverage +0.18
  and +0.29). These are differences between two single runs, not between algorithms. Under outage
  IPPO also had far more engine-invalid moves (paired +24 per episode).
- Under outage MAPPO's coverage is below the heuristic baselines.
- `earthquake_field` stays at 0.216 for IPPO, MAPPO and shared information. It sets
  `latency: 2`; a single diagnostic with latency 0 raised shared information from 0.212 to 0.808,
  indicating that delayed frames are refused by the safety gate. It is a degenerate comparison
  cell. Flood and wildfire field coverage is 0.90–0.98 for the same three policies.
- No episode had blocked-cell occupancy or two drones in one cell. All ended at the horizon.
- Reward, rejected moves, network bytes, uncertainty counts and tick curves per episode are in
  `robustness_episode_metrics.csv` and `robustness_episodes.jsonl`.
- Learned and random policies act through the policy-lease gate; heuristics use the Fleet path.
  Their reward and rejection counts are not like-for-like.
- Unsupported: a separately controlled contradictory-evidence condition, distress or rescue
  outcome metrics, hardware failure or physical flight.

## Reward and uncertainty (12H-5)

- Components sum correctly, new-cell reward is not duplicated, missing observations earn nothing
  and the number of people does not change reward (fixtures).
- `corroborated` fires when one agent's own packet has two modalities, so it is effectively extra
  coverage reward (about 0.99 per nominal episode). Disagreeing labels also count (inspection).
- `resolved_uncertainty` never fired in basic scenarios, including noisy ones, so 12G never
  trained uncertainty handling. In field conditions it contributes about 2.7–2.9 per episode and
  can be earned without moving (independent stationary totals about 0.9).
- No weights were changed. reward-1 and reward-2 stay separate.

## Protocol and training decision (12H-6, 12H-7)

See `reproducibility_protocol.json`. Three learner seeds per algorithm is an initial budget only:
a 3-versus-3 exact two-sided rank test cannot go below p = 0.1. The trained run is the unit of
replication.

**No additional training is justified on the current task.** Keep the checkpoints. First approve
a harder task, the pairing fix, the selection rule and provenance logging. A nearest-unsearched
heuristic is recommended (new code; needs approval). Sequential CPU estimates: 1.4 h for a pilot
of 3 seeds × 2 algorithms × 50k steps; 8.3 h for 3 seeds × 300k; 13.8 h for 5 seeds × 300k. This
900-episode evaluation took about 6 minutes.

## Checks and limitations

- New fixtures: 8 passed. Ruff (new files) and strict mypy (`marl_robustness.py`): passed.
- Full pytest, existing Phase 12 tests and frontend checks: not run. No existing source changed.
- The 12G learning-curve SVG was rendered with Edge and visually inspected: legible, no label
  collisions. Its y-axes do not start at zero.
- Reconstructed configurations are extracted from checkpoint identity and labelled as such.
  Historical console logs, commands, approvals and commits remain missing.
- `owner_decision_pending.json` is unapproved.

## Reproduce

```powershell
.\.venv\Scripts\python.exe -u -m evaluation.marl_robustness diagnostics
.\.venv\Scripts\python.exe -u -m evaluation.marl_robustness run      # resumable; skips done episodes
.\.venv\Scripts\python.exe -u -m evaluation.marl_robustness analyze
```

The run command prints condition, policy, progress, elapsed and remaining time.
