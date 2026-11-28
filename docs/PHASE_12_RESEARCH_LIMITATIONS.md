# Phase 12 research limitations and reporting readiness

For anyone writing up Phase 12. All results come from a symbolic civilian search simulation.

## May be reported, labelled exploratory

- Both algorithms trained for 300,000 steps with one learner seed each.
- Development validation coverage saturates after about 14,400 steps: the task is too easy.
- Robustness (900 episodes) and matched coverage AUC for these two trained runs.
- The operator-pause defect and its correction.

## Not supported

- Superiority or equivalence of IPPO and MAPPO.
- Rescue effectiveness: coverage counts sensed cells, not people found or helped.
- Generalization, deployment readiness or operator readiness.
- Any independent final evaluation. Seeds 13000–13008 were used for selection and reporting;
  13100–13104 were chosen after results were seen. Final seeds were never run.

## Known weaknesses

| Weakness | Effect |
|---|---|
| One learner seed | No between-run variance |
| 900 of 2,700 seed–scenario pairs; shared starts and walls | Narrow variety |
| Saturated coverage; `best.pt` fixed by ties | Cannot discriminate |
| Metric and conditions chosen after results | Exploratory only |
| Heuristics do not target unsearched cells | Low bar |
| Different action paths for learned and heuristic policies | Reward and rejections not comparable |
| Corroboration reward duplicates coverage; uncertainty reward unused in training | Narrow objective |
| `earthquake_field` immobile under delayed frames | Degenerate comparison cell |

## Records

Documented: step counts, seeds, hashes, metrics logs. Reconstructed: configurations, from
checkpoint identity. Missing: console logs, launch commands, authorization, commit, per-episode
validation, training-time hashes of most sources. Earlier test runs executed seeds 42–45.

## Before Phase 14

Phase 14 is not defined. If it uses learned policies, decisions D2, D3 and D5 in the decision
packet are needed. Every new experiment needs separate authorization.
