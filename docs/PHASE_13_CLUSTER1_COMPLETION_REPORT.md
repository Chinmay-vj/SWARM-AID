# Phase 13 cluster 1 completion report (13B, 13C, 13E)

2026-11-27, about 20 minutes. Symbolic civilian research simulation. No training, no checkpoint
file changes, no protected or retired seeds. Phase 12 remains conditionally closed.

| Part | Status | Headline |
|---|---|---|
| 13B | Complete | Four-model frame −27% CUDA, −12% CPU; outputs bit-identical |
| 13C | Complete | Hazard report at 2,000 findings 934 → 49 µs; state identical |
| 13E | Complete | Peak process RSS −31% CPU, −17% CUDA; VRAM unchanged |

Detail: the three part reports.

## Method

`evaluation/phase13_cluster1.py`: synthetic inputs, same weights, FP32, batch 1, three rounds,
5 warm-up and 40 measured iterations, one process per measurement area, CUDA synchronized. All
"before" runs preceded all "after" runs (not interleaved), so slow drift in machine load is not
controlled. NVIDIA RTX PRO 4500 Blackwell only.

## Checks

- Full suite: 449 passed, 0 failed, 3 skipped (PostgreSQL; two retired-seed tests), none
  deselected. Seed guard active.
- Focused: 64 passed. Project mypy (224 files), Ruff and `git diff --check`: passed.
- Not run: pip check (no dependency change), frontend, PostgreSQL, RTX 2060.

## Compatibility

MARL checkpoints and `marl.py` hashes are unchanged. `command_agent/agent.py`, `perception.py` and
`registry.py` changed; the checkpoint identity check cannot detect such changes. Corrected-runtime
compatibility remains unestablished and learned policies remain disabled on operator-facing
missions.

## Pending owner decisions

Residency limit and precision in `rtx2060_runtime.json`; device placement (no change
recommended); derived inference-only checkpoint copies to shorten checksum and load time; and the
earlier ones: Phase 12 closure, checkpoint compatibility, movement permission, default seed 42.

## Limits

Synthetic inputs establish speed and consistency, not accuracy or operational readiness. No
component currently runs the real perception models inside the backend, so the perception gains do
not change backend mission time.

## Reproduce

```powershell
.\.venv\Scripts\python.exe -u -m evaluation.phase13_cluster1 all --label after
.\.venv\Scripts\python.exe -u -m evaluation.phase13_cluster1 verify
```

This overwrites the "after" data. The pre-change sources are saved under `cluster1\before`;
re-measuring "before" would require running them from a separate copy.
