# Phase 12E-12F Completion Report

2026-11-27. Symbolic search-and-rescue **simulation** only. Only bounded smoke and timing runs; no full training.

| Subphase | Status |
|---|---|
| 12E contracts, IPPO, MAPPO | Complete; movement-lease design awaits owner approval |
| 12F infrastructure, checkpoints, launcher, profile | Complete; off-machine migration pending |

## Contract resolution

- **Movement lease:** the environment issues a one-tick lease for the policy move, which still passes
  `safety.authorize` and engine vetoes. Simulation only; it verifies neither command-lease enforcement nor physical
  control. Passing `--authorize-start` records the owner's acceptance.
- **Redundancy:** radius-2 sensing overlaps the previous footprint on every step, so reward-1 penalizes straight new
  paths and holding alike. `reward-2` penalizes only moving back to a cell the agent occupied (-0.02). On the same 36
  baseline episodes no non-reward metric changed. Holding is unpenalized and necessary transit still is penalized.
  reward-1 and reward-2 totals are not comparable. reward-1 results are preserved.
- **Uncertainty:** it needs a field-profile scenario with noise > 0; basic scenarios have neither. Controlled tests:
  fires with partial noise; zero with no noise, all noise or no observations. Contradictory clear labels are not
  rewarded. The default training scenarios are basic, so this term stays at zero there.
- **Independent baseline:** kept as a stationary floor. Recommended addition for later: a no-communication
  nearest-unsearched-cell heuristic from local memory.
- **Seeds:** 42-45 have been executed; 42-46 are retired as unseen. `tests/conftest.py` skips the two tests that
  execute 43-45 unless `SWARM_ALLOW_LEGACY_RESERVED_SEEDS=1`. 900000-900099 remain unexecuted and protected.

| Mean reward, 9 episodes | reward-1 | reward-2 |
|---|---:|---:|
| independent (stationary) | -3.60 | 0.00 |
| fixed_sector | 4.13 | 7.50 |
| shared_information | 4.45 | 7.81 |
| random_masked | -2.40 | -0.28 |

## Algorithms

Both use one shared actor over each agent's local 240-value observation, a masked categorical policy, GAE
(bootstrap on truncation, none on termination) and clipped PPO in FP32.

- IPPO: shared local critic (95,494 parameters).
- MAPPO: critic sees own + mean + max of all local observations, training only (156,934 parameters). No simulator
  truth. Tests confirm actions do not depend on other agents' observations.

Not included: value clipping or normalization, recurrence, parallel environments, mixed precision.

## Training infrastructure

`evaluation/marl_train.py` with `configs/marl/ppo-v1.json`: atomic checkpoints each update, `best.pt` by validation
coverage (seeds 13000+), JSONL metrics, deadline and Ctrl+C stops, refusal of incompatible resume. Resume is at
update boundaries, with no mid-episode restore. Interrupted and uninterrupted CPU runs produced identical weights
and sampling state for both algorithms. GPU exactness is unverified.

## Smoke and profile

Both algorithms passed two-update smoke runs on CPU and GPU. Smoke rewards are not evidence of learning.

| Run | End-to-end env steps/s | Rollout s | Update s | Peak GPU alloc/reserved MiB |
|---|---:|---:|---:|---:|
| IPPO CPU | 61.3 | 22.6 | 0.3 | - |
| IPPO CUDA | 57.4 | 24.2 | 0.3 | 29 / 50 |
| MAPPO CPU | 60.2 | 22.9 | 0.3 | - |
| MAPPO CUDA | 56.6 | 24.5 | 0.3 | 44 / 58 |

Timing: 1,440 steps per run. Rollout is about 99% of time, so **CPU is the better device**. Process RAM about
0.6 GiB CPU-only (about 1.7 GiB once CUDA is loaded). Checkpoints 1.2 MB (IPPO), 1.9 MB (MAPPO).

Estimate: about 1.4 h per 300k-step run, 4.6 h per 1M, plus roughly 6% for validation. Two algorithms x three
learner seeds at 300k is about 9 h sequentially. Running processes in parallel is untested. Whether 300k steps is
enough for learning is unknown.

## Verification

38 Phase 12 tests passed. Full suite: 410 passed, 0 failed, 3 skipped (PostgreSQL; two reserved-seed tests); it ran
before three type-only edits, after which Phase 12 tests, Ruff and strict mypy passed again. `pip check` and
`git diff --check` passed. Frontend checks not run. RTX 2060 untested. Source is uncommitted.
