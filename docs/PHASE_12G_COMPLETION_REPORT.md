# Phase 12G completion report: initial IPPO and MAPPO training

Verified 2026-11-27. Symbolic simulation only. No retraining, no weight changes, no protected or
final seeds. Verification replayed greedy validation on seeds 13000–13008.

## Status

Both runs completed 300,000 environment steps (10,000 episodes, 625 updates, stop reason
`budget_reached`, no resume). The checkpoints and metrics logs are complete and consistent.
The results are **initial and saturated**: they do not separate the two algorithms.

## Configuration

`configs/marl/ppo-v1.json` (SHA256 `9ac49a2e…24ace1`): reward-2; flood_basic, wildfire_basic,
earthquake_basic; 6 agents; horizon 30; hidden 128; learning rate 3e-4; gamma 0.99; lambda 0.95;
clip 0.2; entropy 0.01; value 0.5; gradient norm 0.5; 16 episodes per update; 4 epochs;
minibatch 512; validation every 10 updates over 9 episodes; 1 torch thread. CPU, FP32.

- Learner seed 1 for both. One run per algorithm.
- Training scenario seeds 12000–12899; validation seeds 13000–13008 (three per scenario).
- The configuration, contract versions and source hashes stored in all four checkpoints match the
  current repository files. The hashes cover `marl.py`, `marl_contract.py` and `marl_ppo.py` only.

## Checkpoint verification

All four checkpoints loaded with `weights_only=True` and strict state loading (model, optimizer
and sampling generator), had finite weights, matched the SHA256 in `metrics.jsonl`, and reproduced
their recorded validation values exactly. File hashes were unchanged by verification.

| Run | Checkpoint | Steps | Val. coverage | Val. reward-2 | Engine-invalid moves | SHA256 |
|---|---|---:|---:|---:|---:|---|
| IPPO | latest (final) | 300,000 | 1.0000 | 10.89 | 0.00 | `7ac14fb8…3eff` |
| IPPO | best | 14,400 | 1.0000 | 10.69 | 1.89 | `cc67e2d5…2aa3` |
| MAPPO | latest (final) | 300,000 | 0.9991 | 10.83 | 0.44 | `81444395…2a1b` |
| MAPPO | best | 14,400 | 1.0000 | 10.56 | 3.00 | `9f9ec58c…3062` |

`best.pt` is selected by strict improvement in validation coverage. Coverage reached 1.0 at update
30, so `best.pt` was never replaced. For both algorithms the final checkpoint has higher validation
reward and fewer invalid moves than `best.pt`.

## IPPO versus MAPPO

| Metric | IPPO | MAPPO |
|---|---:|---:|
| Final validation coverage | 1.0000 | 0.9991 |
| Final validation reward-2 | 10.89 | 10.83 |
| Final validation engine-invalid moves per episode | 0.00 | 0.44 |
| Mean of last 10 validations: coverage | 1.0000 | 0.9998 |
| Mean of last 10 validations: reward-2 | 10.87 | 10.87 |
| Mean of last 10 validations: engine-invalid | 0.20 | 0.13 |
| First step with validation coverage ≥ 0.99 | 14,400 | 14,400 |
| Last 50 updates, training coverage | 0.9989 | 0.9978 |
| Last 50 updates, training reward-2 | 10.81 | 10.77 |
| Last 50 updates, engine-invalid | 0.51 | 0.76 |
| Last 50 updates, entropy | 0.038 | 0.092 |
| Last 50 updates, value loss | 0.0128 | 0.0107 |
| Last 50 updates, approximate KL | 0.0022 | 0.0032 |
| Duration | 1 h 20 min 33 s | 1 h 25 min 07 s |
| Environment steps per second | 62.1 | 58.7 |
| Rollout / update seconds | 4,499 / 57 | 4,739 / 72 |
| Peak process memory | 637 MiB | 656 MiB |
| GPU memory | not used | not used |
| Parameters | 95,494 | 156,934 |
| Checkpoint size | 1,166,352 B | 1,903,696 B |

The runs were sequential: MAPPO about 14:13–15:38, then IPPO about 15:38–16:59 (UTC−8).

## Learning curves

Generated from the existing `metrics.jsonl` files, in `D:\SWARM-AID-DATA\runs\phase12\phase12g`:

- `learning_curves.svg` (training and validation coverage and reward, entropy, invalid moves)
- `curves.csv` (the same series as a table)
- `verification.json` (all values above and full file hashes)
- `verify_phase12g.py` (reproduces the three files)

The chart was not rendered for visual inspection, and the palette validator was not run because
Node.js is not available in this shell.

## Interpretation and limitations

- The final differences are very small. With one learner seed and 9 validation episodes, no claim
  of superiority or equivalence is supported.
- Validation coverage saturates after about 5% of the step budget. This task setting (6 agents,
  30 ticks, basic scenarios) is too easy for coverage to discriminate between methods.
- `index % 3` selects the scenario and the seed cycle has length 900, so each training seed is
  always paired with the same scenario: 900 distinct seed–scenario pairs, not 2,700.
- Validation seeds were also used for checkpoint selection. They are not an unseen test.
- Existing heuristic baselines used development seeds. They are not comparable to these validation
  numbers until rerun on seeds 13000–13008.
- The default scenarios never trigger the uncertainty reward term.
- Movement relies on the simulation-only policy lease. Results say nothing about physical flight.
- No final-seed evaluation exists. Seeds 900000–900099 were not executed.

## Missing or incomplete artifacts

- No saved console log for either run.
- No record of the launch command, `--authorize-start`, or owner approval of the lease design.
  Checkpoints record `smoke: false`; the command-line launcher requires the flag for such a run.
- No standalone configuration copy or Git commit in the run folders (the configuration is
  embedded in each checkpoint). The source changes are uncommitted.
- Simulator, safety and fleet sources are not hashed into checkpoint identity.
- Validation logs hold means only: no per-episode, per-scenario, duplicate-coverage or network data.
- The migration manifest predates these runs. `checkpoints/phase12` is optional in the migration
  script, so use `-IncludeOptional`. No off-machine copy is verified.

Tests, Ruff and mypy were not rerun: no repository source changed in this phase.
