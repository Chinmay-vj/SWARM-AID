# CPU baseline benchmarks (Phase 9)

Measured on 2026-11-24. These describe this machine and this untrained, rule-based system. They
are not scalability claims and not research results.

**Host:** Intel64 Family 6 Model 165 (i7-10750H class), 12 logical CPUs, Windows 11
(10.0.26200), CPython 3.12.10, numpy 2.5.5, pydantic 2.14.4, FastAPI 0.165.0, SQLAlchemy
2.1.9, uvicorn 0.54.0; SQLite in WAL mode on the local disk; single uvicorn worker; other
desktop applications running. Software revision `ce0ef30` plus uncommitted Phase 9 changes
(manifests record `-dirty`).

## 1. Integrated stack, headless (Phase 9 extended matrix)

Run: `python -m orchestration matrix --config configs/experiments/phase9_extended.json`
→ `runs/phase9/659f0b5f5d3b4ef98003724352cf3aa5/`. Workload: full integrated stack per tick
(engine, N Model 1 agents, transport, shared-information coordination, Model 2 fusion), 30
ticks per run, no tick delay, no database.

Outcome: **134 of 134 runs completed** (0 failed, 0 unsupported); **30 of 30 determinism
repeats identical**.

Simulation step duration, scaling block (flood, wildfire, earthquake × 5 seeds = 15 runs and
450 steps per agent count; median is the median of per-run medians; p95/p99/max are the
maximum across runs):

| Agents | Steps | Median ms | p95 ms (max) | p99 ms (max) | Min ms | Max ms | Mean run wall-clock ms | Max router queue |
|---|---|---|---|---|---|---|---|---|
| 1 | 450 | 2.6 | 5.6 | 147.2 | 1.7 | 147.2 | 95 | 11 |
| 3 | 450 | 8.9 | 18.3 | 187.1 | 5.2 | 187.1 | 303 | 36 |
| 6 | 450 | 19.7 | 35.5 | 55.1 | 11.3 | 55.1 | 619 | 88 |
| 10 | 450 | 35.7 | 84.2 | 101.1 | 19.5 | 101.1 | 1132 | 334 |
| 20 | 450 | 96.8 | 203.7 | 218.6 | 46.5 | 218.6 | 3056 | 779 |

Step time grows faster than linearly with agent count (peer sharing makes message volume grow
with pairs of agents). The isolated 147–187 ms maxima at 1 and 3 agents are single outliers
(host scheduling or garbage collection), not sustained behaviour.

Python peak traced memory for one headless mission (`--memory`, tracemalloc): 16.3 MB at 6
agents, 57.6 MB at 20 agents.

Communication (simulated time): delivery latency p95 was 100 ms (one tick) in every scaling run;
mean delivery ratio 0.96 (1–6 agents) and 0.91 (10–20 agents). Under fault fixtures: loss 0.62,
delay 0.84, reorder 0.86 (summary.csv).

## 2. Backend under load (`python -m evaluation.backend_benchmark`)

Isolated server on port 8766 with its own database
(`runs/backend/benchmark-20261124T154812Z/benchmark_results.json`). Per fleet size: one running
mission, one machine credential per drone, 40 reports per agent submitted concurrently through
Model 2, duplicate resubmission, REST reads and WebSocket delivery.

| Agents | Reports | Errors | Ingestion p50 / p95 / p99 ms | Ingestion throughput /s | WebSocket events | WS delivery p50 / p95 / p99 ms |
|---|---|---|---|---|---|---|
| 3 | 120 | 0 | 168 / 592 / 640 | 15.3 | 774 | 50 / 158 / 537 |
| 6 | 240 | 0 | 508 / 1380 / 1816 | 9.2 | 1546 | 67 / 245 / 583 |
| 10 | 400 | 0 | 571 / 1819 / 2378 | 15.9 | 1812 | 57 / 330 / 1747 |
| 20 | 800 | 0 | 639 / 1436 / 1761 | 21.3 | 3051 | 72 / 482 / 1346 |

Other measurements: duplicate resubmission p50 about 3 ms (all recognized); REST reads at 6
agents p50 summary 5 ms, incidents 29 ms, observations 6 ms, review queue 30 ms, map 20 ms;
login (Argon2id) p50 61 ms, p95 73 ms; 50 concurrent authenticated WebSocket connections, p50
connect 16 ms, 0 errors; database single-row commit p50 0.43 ms (p99 49.7 ms), primary-key
read p50 0.27 ms; cold start 2.11 s; restart to ready 2.08 s; server peak working set 315 MB.
Error rate 0 in every series.

Ingestion latency includes waiting for the mission lock while the simulation ticks; it is
dominated by contention, not by Model 2's assessment.

## 3. Dashboard (Phase 8 measurement, unchanged)

`runs/frontend/phase8-performance.json`: 0 long tasks at 3–20 agents, JS heap under 80 MB,
overview about 8–9 API requests per second. See `docs/frontend/QUALITY_AND_OPERATIONS.md`.

## 4. Not measured separately

Per-stage latencies inside one tick (Model 1 update, Model 2 assessment, event publication) are
not instrumented separately; the step duration covers all of them. CPU utilisation was not
sampled. Dashboard update latency is covered only by WebSocket delivery latency.

## Reproduce

```powershell
.\.venv\Scripts\python.exe -m orchestration matrix --config configs\experiments\phase9_extended.json
.\.venv\Scripts\python.exe -m evaluation.backend_benchmark
```

Optimisation is Phase 13 work; nothing was tuned in Phase 9.
