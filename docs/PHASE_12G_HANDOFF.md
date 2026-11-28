# Phase 12G handoff (training not started)

No further source inspection is needed. Report: `PHASE_12E_F_COMPLETION_REPORT.md`.

## Before starting

1. Owner approves the policy-lease abstraction (`--authorize-start` records it).
2. Decide scenarios. The default uses three basic scenarios; add `flood_field` with noise only if the uncertainty
   term should matter. Any config or source change makes earlier checkpoints incompatible.
3. Use CPU. Choose budget and learner seeds.

## Train and resume (from the repository root)

```powershell
.\.venv\Scripts\python.exe -u -m evaluation.marl_train --algo mappo --run-dir D:\SWARM-AID-DATA\checkpoints\phase12\mappo-s1 --steps 300000 --seed 1 --authorize-start
.\.venv\Scripts\python.exe -u -m evaluation.marl_train --algo ippo --run-dir D:\SWARM-AID-DATA\checkpoints\phase12\ippo-s1 --steps 300000 --seed 1 --authorize-start
# resume: same command plus --resume
.\.venv\Scripts\python.exe -u -m evaluation.marl_train --algo mappo --run-dir D:\SWARM-AID-DATA\checkpoints\phase12\mappo-s1 --steps 300000 --seed 1 --authorize-start --resume
```

Options: `--device cpu|cuda`, `--config`, `--deadline 2026-12-01T18:00:00+05:30`, `--smoke`.
Outputs in the run directory: `latest.pt`, `best.pt`, `metrics.jsonl`, `summary.json`.

## Seeds and evaluation

Training 12000-12899; smoke and profiling 12900-12999; validation 13000-13999. 900000-900099 need separate owner
approval and no evaluator for them exists. Compare with fixed_sector and shared_information on matched validation
scenarios and seeds (the recorded baselines are on development seeds 12000-12002, so rerun them on validation seeds
first). Report coverage and safety vetoes, not only reward.

## On another machine

Restore the repository from the bundle or the copied `repo` folder, recreate `.venv` (torch, numpy, pydantic,
gymnasium, pettingzoo), and keep a `D:` drive: the launcher requires run directories on D: on Windows.
Verification: `.\.venv\Scripts\python.exe -m pytest -q tests/integration/test_phase12.py tests/integration/test_phase12ef.py`
