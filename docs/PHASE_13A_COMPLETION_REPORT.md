# Phase 13A completion report: performance baseline

2026-11-27. Symbolic civilian search simulation. Synthetic inputs, development seed 12990, no
training, no optimization applied, no production source changed. Artifacts:
`D:\SWARM-AID-DATA\runs\phase13\phase13a`.

Status: 13A-1 to 13A-4 and 13A-6 to 13A-8 complete. **13A-5 partial** (PostgreSQL, health endpoint,
dashboard, network latency and per-model CPU utilisation not measured). The owner's request covers
Phase 13A only; Phase 12 stays conditionally closed and every other decision stays pending.

## Environment

Intel Xeon 636, 12 cores / 24 logical; 63.3 GiB RAM (51.9 free); NVIDIA RTX PRO 4500 Blackwell,
32,623 MiB (31,437 free), driver 596.51; Windows 11 Pro for Workstations build 10.0.26300;
Python 3.12.10; PyTorch 2.11.0+cu128; D: 1,446 GiB free. Minimal CPU and CUDA checks passed.
These match the versions reported for Phase 11J. No RTX 2060 is present.

## Code quality

The six mypy errors were in `tests/unit/test_phase11_model1.py`. Fixed with
`torch.autograd.backward` and `typing.cast` on test stand-ins; no suppressions or assertion
changes. Project mypy passes.

## Perception baseline (batch 1, median of 40, end to end)

| Model | CPU FP32 ms | CUDA FP32 ms | CUDA FP16 ms | RSS CPU / CUDA MiB | VRAM reserved FP32 / FP16 MiB |
|---|---:|---:|---:|---:|---:|
| RescueNet | 50.8 | 12.0 | 13.4 | 926 / 1,325 | 130 / 112 |
| FloodNet | 50.2 | 11.7 | 13.3 | 928 / 1,325 | 130 / 100 |
| FLAME | 10.2 | 9.8 | 11.1 | 636 / 1,156 | 30 / 28 |
| ESC-50 | 3.8 | 4.3 | 5.2 | 631 / 1,148 | 28 / 26 |
| UCI CO | 0.5 | 0.8 | 1.2 | 504 / 1,028 | 22 / 22 |
| WiSARD RGB (experimental) | 33.2 | 14.3 | 17.6 | 1,122 / 1,859 | 158 / 156 |
| Neural fusion (comparison) | 0.5 | 2.3 | 2.6 | 507 / 1,234 | 22 / 22 |

Stage times, p95, load and first-inference times: `model1_baseline.json`. WiSARD thermal stays
excluded. Synthetic inputs say nothing about accuracy. FP16 was slower than FP32 here.

## System baseline

- **Model 2** (synthetic reports): ingestion 9–15 µs; hazard processing median 0.08, 0.23 and
  0.94 ms at 100, 500 and 2,000 reports (about 0.19 ms early to 1.63 ms late at 2,000);
  recommendation step 6–16 µs; deterministic fusion 0.7–3.5 ms; checkpoint serialization
  0.4–9.3 ms; peak RSS 33–53 MiB.
- **Messages:** 721-byte envelope, serialize 4 µs, validate 8 µs.
- **Backend, in process on SQLite** (6 agents, 60 ticks): step 12.8 ms; persistence 27.2 ms median,
  49.0 mean, 154 p95. API medians: mission 3.3, summary 4.7, events 6.8 ms. Health: NOT TESTED
  (the profiler's path returned 404). Peak RSS 164 MiB. Not network or production figures.
- **Simulator** (median tick, without / with command agent): 3 agents 4.9 / 5.4 ms; 6 agents
  10.5 / 11.7; 20 agents 51.2 / 61.3 (p95 108 / 133). Safety check about 7 µs, 0.2–0.4% of a tick.
  One CPU core; RSS 51–98 MiB.

## Bottlenecks

Measured, in priority order:

1. Backend persistence per tick, about twice the simulation step.
2. Snapshots: 12.6 MB of about 13.3 MB of stored data after 60 ticks (snapshot every 5 ticks in
   this fixture; the default is 10). Checkpoint ticks took 87 ms against 48 ms under the profiler.
3. Cold start: importing torch 1.2 s and torchvision 0.76 s; image models load in 0.9–1.7 s;
   first CUDA inference 0.2–0.4 s (FP32), up to 3.0 s (FP16).
4. Simulator ticks at 20 agents.
5. Image preprocessing, 4–6 ms, near half of CUDA latency for segmentation and FLAME.
6. Model 2 cost grows with the number of findings.

Suspected, not established: persistence is mostly ORM work (Python 3.12 profiling includes other
threads, so those shares are indicative only); lazy torchvision import explains most image-model
load time; decode dominates preprocessing. Simulator own-time is spread out, led by random-stream
seeding (12%) and pydantic validation.

End-to-end GPU FP32 medians are close to Phase 11J, which used fewer samples in a shared process;
load times are not comparable. No improvement is claimed.

## Plan and restrictions

`optimization_plan.json` lists each proposal with its risk and required checks. Order: 13D
persistence and snapshots; 13B warm-up and shared decoding; 13C indexing; 13G simulator; 13E
memory; 13F dashboard after measurement. Optimizing engine, sensor, messaging or fleet code can
change MARL behaviour **without** failing the checkpoint identity check, so require trace equality
(`checkpoint_provenance_plan.json`). Learned policies stay disabled on operator-facing missions.

RTX 2060: provisional 6 GiB planning assumption, not verified; measured allocator figures exclude
the CUDA context.

## Checks

Focused tests 26 passed. Project mypy, Ruff and `git diff --check` passed. Full regression not
rerun (no production source changed); the last full run was Phase 12J: 436 passed, 3 skipped.
Figures (`fig_*.svg` and `.png`): stages, memory and system costs were visually inspected; latency
and loading were not. One profiling run: no run-to-run variance is available.

## Reproduce

```powershell
.\.venv\Scripts\python.exe -u -m evaluation.phase13a_profile all
```

Takes a few minutes and overwrites this folder's baselines; copy them first to keep them.
