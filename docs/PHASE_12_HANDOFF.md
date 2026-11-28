# Phase 12 handoff (not started; needs an explicit owner request)

## Start here

`PHASE_11_COMPLETION_REPORT.md`, `PHASE_11J_COMPLETION_REPORT.md`, `AGENTS.md`.

## Interfaces to build on

- Environment: `simulation/core/engine.py` (`Engine`, `Move`, `reset(seed)`).
- Agents: `simulation/adapters/model1.Fleet` (`policy`, `coordination`, `command`, `record_evidence`,
  `perception_factory`). A new `Fleet` per episode clears agent state.
- Safety: `agents/drone_agent/safety.authorize` stays authoritative over any learned proposal.
- Policy port: `interfaces.providers.CoordinationPolicy` or `PlanningProvider`.
- Models: `evaluation.model1.registry.ModelRegistry.from_file(registry, data_root)`, shared and frozen.

## Constraints

- Train MARL on symbolic observations. Do not render synthetic media and call model outputs observations.
- Keep ground truth inside the simulator/evaluator boundary.
- Seeds 42-46 are reserved. **Always pass a development seed:** the default scenario seed is 42.
- Thermal detector stays excluded; WiSARD RGB output is experimental.
- Movement is disabled by default (`configs/model1.json`); enabling it in simulation is explicit.
- No physical control or real dispatch.

## Open before or during Phase 12

Reward and observation design, baselines (existing coordination policies), episode-reset and determinism tests for
the training loop, named seed streams and split registry, dependency extra for the RL library (not installed),
RTX 2060 measurement.

## Commands

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m evaluation.model1.phase11j registry
.\.venv\Scripts\python.exe -m evaluation.model1.phase11j profile
.\.venv\Scripts\python.exe -m evaluation.model1.phase11j migration
powershell -ExecutionPolicy Bypass -File scripts\migrate_phase11.ps1 -Destination <PATH>
```

The registry command rewrites `runtime_model_registry.json` from preserved checkpoints and reads the authorized UCI
training partition for normalization. Data root `D:\SWARM-AID-DATA` is hard-coded in several evaluation modules; on
another machine keep that path or update those constants.
