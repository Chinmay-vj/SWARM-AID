# Phase 12E handoff (not started)

Read this and `PHASE_12A_D_COMPLETION_REPORT.md`; no further repository audit should be needed.

## Environment

```python
from simulation.adapters.marl import SearchEnv
from simulation.core.configuration import Scenario, load
config = Scenario.model_validate(load("flood_basic").model_dump() | {"agents": 6})
env = SearchEnv(config)                      # coordination=None is learning mode
obs, infos = env.reset(seed=12000)           # dict agent -> float32[240]
obs, rew, term, trunc, infos = env.step({a: 0 for a in env.agents})
env.episode_metrics()                        # evaluator only
```

| File | Role |
|---|---|
| `simulation/adapters/marl.py` | environment |
| `simulation/adapters/marl_contract.py` | observation, mask, reward, seed namespaces |
| `evaluation/marl_baselines.py` | smoke, resumable pilot, parity, profile, spec export |
| `tests/integration/test_phase12.py` | contract tests |

## Rules

- Seeds: train 12000-12999, select on 13000-13999. 42-46 closed. 900000-900099 need owner approval.
- Sample only actions allowed by `infos[a]["action_mask"]`; apply the mask to policy logits.
- Keep safety gates; never give the policy `env.engine`.
- Changing observation, action or reward means bumping its version and rerunning baselines.

## Decide before training

1. Accept the policy-lease design, or require command-issued leases.
2. Reward: the redundancy penalty dominates and barely discriminates. Consider penalizing only avoidable revisits.
3. Resolved-uncertainty needs noisy scenarios (`command_routine`/`flood_noise` or `noise` > 0) to be exercised.
4. Centralized critic input for MAPPO: concatenated observations, or a separately specified training-only state.
5. Metric and budget: coverage at horizon 30 against fixed_sector 0.752 and shared_information 0.776 (3 seeds each
   per scenario; widen before claiming differences).
6. Hold out scenarios as well as seeds; peers currently share findings, not positions.

## Practicalities

PyTorch is installed; no RL framework is needed for a small IPPO. About 83 env steps/s at 6 agents on one core, so
plan multiprocessing (spawn). Use FP32 or FP16, not BF16, for RTX 2060 portability; that card is untested.

## Commands

```powershell
.\.venv\Scripts\python.exe -u -m evaluation.marl_baselines smoke
.\.venv\Scripts\python.exe -u -m evaluation.marl_baselines baseline   # resumes; skips finished episodes
.\.venv\Scripts\python.exe -u -m evaluation.marl_baselines profile
.\.venv\Scripts\python.exe -u -m evaluation.marl_baselines contracts
.\.venv\Scripts\python.exe -m pytest -q tests/integration/test_phase12.py
.\.venv\Scripts\python.exe -m pytest -q --deselect tests/integration/test_field_scenarios.py::test_expansion_protection_and_storage --deselect tests/integration/test_system_integration.py::test_identical_configuration_reproduces_identically
```
