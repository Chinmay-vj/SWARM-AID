# Multi-agent reinforcement learning readiness (Phase 12 preparation)

No learning policy, reward function or training was introduced in Phase 9.

## What exists

`simulation/adapters/parallel.py` defines `RescueEnv`, a PettingZoo `ParallelEnv`
(`metadata.name = "swarm_aid_v1"`) over the Phase 2 engine.

| Interface | Implementation | Verified |
|---|---|---|
| Reset | `reset(seed=None, options=None)` → per-agent observations and infos; `seed=None` uses the scenario seed | `parallel_api_test` (35 cycles) passes; identical observations for the same seed |
| Step | `step(actions: dict[str, int])` → observations, rewards, terminations, truncations, infos | API test |
| Agent identifiers | `possible_agents` = drone keys `d0..dN`; `agents` = active drones | API test |
| Observations | `Box(4,)` int32 per agent: own cell x, y (−1 when missing), battery %, count of `possible_human` readings in the agent's own sensor packet | observation-space containment test |
| Actions | `Discrete(10)` = `simulation.core.engine.Move` (hold, 4 moves, observe, request, report, return, inactive) | API test |
| Termination | drone inactive | — |
| Truncation | horizon reached | — |
| Agent availability | inactive drones leave `agents` | — |
| Seed handling | named seed streams in the engine | Phase 9 determinism checks (engine level) |
| Rewards | injected `RewardProvider(agent, observation, action) -> float`; **0.0 when none is given** | — |
| Evaluation hooks | `evaluation.results.metrics(env.engine)` after an episode | — |
| Independent observations | each agent sees only its own packet-derived vector | by construction |

Observations come from the agent's simulated sensor packet (with noise, misses and dropout),
not from ground truth. A reward provider written in Phase 12 must not use ground truth for
anything an operational agent could not know, unless it is explicitly an evaluator-side
training signal and documented as such.

## Gaps for Phase 12

1. **The environment bypasses the integrated stack.** `RescueEnv` drives the engine directly:
   no Model 1 safety controller, no simulated transport (so no communication conditions), no
   coordination and no Model 2. A policy trained there would not see packet loss, partitions or
   leases, and its actions would not be checked by the independent safety controller. Options:
   (a) a second environment that steps `SimulationContext` and lets a policy act through
   `CoordinationPolicy.target` (task assignment), keeping Model 1 safety; or (b) a policy as a
   Model 1 `PlanningProvider` whose proposals still pass `safety.py`.
2. **Observation is minimal** (4 integers). Richer observations (local map, peer messages,
   task lease) need a versioned observation contract.
3. **Communication conditions** are scenario-level, not configurable per episode through
   `reset(options=...)`.
4. **The action space includes `INACTIVE`**, which lets a policy switch a drone off; decide in
   Phase 12 whether that remains a legal learned action.
5. **No vectorised or parallel-episode runner** for CPU training throughput.
6. Coordination interfaces (`CoordinationPolicy.target(mission, member, round, reported)`)
   are stable and are the natural attachment point for a learned coordination policy; the
   Phase 5 baselines remain the comparison points.

## Commands

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration\test_simulation.py -k parallel -q
```
