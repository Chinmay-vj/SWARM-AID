# Reproducibility guide (Phase 9)

## What identifies a run

| Item | Where it is recorded |
|---|---|
| Scenario identifier and version | `configuration.scenario_id`; `scenario_version` (`Scenario.version`) |
| Random seed | `configuration.seed` (named seed streams inside the engine: `"{seed}/people"`, `"{seed}/hazards"`, `"{seed}/{agent}/{tick}/{modality}"`) |
| Agent count | `configuration.agents` |
| Coordination policy | `configuration.coordination` |
| Model 2 mode | `configuration.command_mode` |
| Communication configuration | inside the scenario fixture (`network`, `loss`, `delay`, `partition`, `outage_steps`) plus mission `outage_steps` |
| Model 1 / Model 2 providers | mock and rule-based only (`configs/model1.json`; Model 2 defaults). Provider identifiers are not yet versioned (see MODEL_PROVIDER_READINESS.md) |
| Runtime limits | `horizon`, `tick_ms` |
| Software version and Git revision | manifest `software_version`, `git_commit` (suffix `-dirty` when tracked files differ) |
| Dependencies and host | manifest `environment` (Python, OS, CPU count, package versions) |
| Timestamp | manifest `created_at` (UTC) |
| Configuration digest | manifest `configuration_sha256` |

Backend missions record the same in `simulation_runs` (`config`, `software_version`,
`git_commit`) and in the research export's `reproducibility` section.

## Determinism

Deterministic: simulation time, world, sensor readings, agent decisions, transport outcomes,
coordination, Model 2 outputs and evaluator metrics, for a given configuration and code
revision.

Verified in Phase 9 by an operational fingerprint (SHA-256 of Model 2's read model, router
metrics, final agent positions and coordination snapshot; no wall-clock values):

- 30 of 30 repeated runs in the extended matrix produced identical fingerprints (same process);
- `flood_basic`/6/42 and `flood_network_reorder`/10/43 produced identical fingerprints in
  separate processes with `PYTHONHASHSEED` 1, 2 and 3;
- different seeds produce different fingerprints (tested).

Not deterministic: wall-clock fields (`*_at`, timings, latencies), UUID4 identifiers created by
the backend (missions, rows, decisions), and connected missions in general, because human
actions, tick pacing and HTTP timing decide which simulation tick a decision or API report
reaches. Bit-for-bit reproducibility of output files is not claimed (they contain timestamps and
UUID4 experiment folders).

## Reproduce

```powershell
# one integrated run
.\.venv\Scripts\python.exe -m orchestration run --scenario flood_basic --agents 6 --seed 42
# expected fingerprint at revision ce0ef30 + Phase 9 changes:
#   b8e313d18d69852f77bad65d908d206627fb1f7719b90d58d952a0696ba6b4c4

# matrices
.\.venv\Scripts\python.exe -m orchestration matrix --config configs\experiments\phase9_smoke.json
.\.venv\Scripts\python.exe -m orchestration matrix --config configs\experiments\phase9_extended.json

# Phase 5 / Phase 6 research runners through the unified entry point
.\.venv\Scripts\python.exe -m orchestration experiment --family coordination --config configs\experiments\phase5_baselines.json
.\.venv\Scripts\python.exe -m orchestration experiment --family command --config configs\experiments\phase6_baselines.json
```

Each matrix folder contains `manifest.json`, `runs.jsonl` (full results), `runs.csv`,
`summary.csv`, `summary.json` and `determinism.csv`. Fingerprints change when code that affects
simulation behaviour changes; compare runs only at the same `git_commit`.

## Known sources of variation

- Running a mission through the backend paces ticks by `SWARM_SIMULATION_TICK_DELAY_MS`; this
  changes wall-clock behaviour, not simulation outcomes, unless a human or API client
  intervenes.
- Python 3.11 and 3.12 are both supported; cross-version identity of fingerprints was not
  tested.
