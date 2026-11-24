# Phase 6 implementation and verification

**Phase 7 readiness: READY WITH LIMITATIONS** for integration with the synthetic command read model. Independent Phase 6 audit remains outstanding. Work is uncommitted.

## Files and responsibilities

| Repository location | Changes |
|---|---|
| agents/command_agent/agent.py, validation.py | Mission-scoped command memory, checkpoint/replay, world view, incident association, assessment, urgency, recommendations, operator review and authorization |
| communication/messages.py, network.py, agents/drone_agent/reporting.py | Versioned forwarding, operator review and alert envelopes, role permissions and sender serialization |
| simulation/adapters/model1.py, simulation/__main__.py | Optional one-per-mission command agent, authenticated command inbox, operator publication, assignment overrides, outage handling, CLI and snapshot export |
| simulation/environments/base.py, configs/scenarios/ | Symbolic landslide and cyclone profiles and fixtures for routine, single, noisy, stale, partial-sensor and operator-outage cases |
| configs/model2.json, configs/experiments/phase6_baselines.json, evaluation/command_agent_experiments.py | Defaults, matched experimental conditions, isolated truth comparisons and JSON/CSV export |
| tests/integration/test_command_agent.py | Integration, provenance, provider rejection, authorization, stale control, checkpoint, scenario and replay regressions |
| docs/command_agent/, docs/research/MODEL_2_*.md, docs/specifications/MESSAGE_PROTOCOL.md, README.md | Architecture, operator and backend contracts, testing commands, metric definitions and limitations |

The simulator continues to run each Model 1 independently. Model 2 processes admitted reports. Direct mode forwards observations. Rules mode assesses each hazard or sighting separately. Fusion groups recent reports by reported cell, kind and label, deduplicates evidence IDs and distinguishes original sources. ContextPriority proposes an explained operator-review priority. Review produces a time-limited recommendation tied to the current incident revision. The independent validator checks operator authorization and rejects superseded decisions. Confirmed rescue need requires a human decision reference. Explicitly reported resolution and closure are separate human actions.

## Measured results

Windows CPython 3.12.10 in the existing project virtual environment. Pre-change suite passed 103 tests. Final regression passed **124 tests with zero failures or skips**, with two PettingZoo deprecation warnings. Ruff passed. Strict mypy passed across 50 files. Pip check reported no broken requirements.

Ran 45 matched episodes across 3, 6 and 10 agents, seed 42, five scenarios and three modes. All reached the horizon. Cross-checked incident and operator-update counts in every CSV row against its episode JSON. Replay tests compared deterministic episode outputs for eight scenario configurations. Separate CLI runs exercised basic flood, multiple sightings and command outage.

| Six-agent flood, seed 42 | Admitted findings | Incident IDs | Delivered operator updates | Scripted decisions sent |
|---|---:|---:|---:|---:|
| Direct | 174 | 0 | 168 | 0 |
| Rules | 174 | 139 | 258 | 134 |
| Fusion | 174 | 11 | 37 | 11 |

The operator first received a sighting at 200 simulated ms in the fusion arm. Nine scripted decisions were accepted and two missed the current revision because a second source changed the incident category. Before corroboration holding, fusion delivered 135 updates and only one of eleven decisions was accepted; 111 corroborating reports were held in this run. In the separate outage CLI run, application log entries recorded offline at 400 ms, recovered at 700 ms and ended at 3000 ms. The run admitted 174 observations, opened 10 incidents and generated 14 further revisions while holding 137 corroborating reports (151 revisions before corroboration holding).

[Experiment CSV](../runs/phase6-verified/experiments/d3d489272319467ab2b2514994ab14c2/comparison.csv) and [outage command log](../runs/phase6-verified/flood_server_unavailable/8a32f30a3d4a4b27a897b1bb0d0a2b8f.command.json) are local ignored artifacts. Use the README PowerShell commands to reproduce them.

## Outstanding limitations

- Corroboration holding keeps a pending revision stable, but a material change (category or urgency level) still supersedes a decision in flight. Held corroboration reaches the operator only after the decision or expiry, a delay bounded by review_ms. A client should retrieve the latest recommendation and show what changed before requesting another decision.
- Cell association can merge people or split moving sightings. Confidence comes from symbolic sensors. Urgency uses heuristic environmental context. The matched matrix uses one seed and a scripted operator; response counts do not estimate real human workload.
- Checkpoint restoration requires a trusted, complete application journal and matching providers. Router sessions, pending packets and the coordination fixture have separate ownership. There is no durable crash recovery.
- Command-level pause suspends new assignments. Individual drones enforce delivered operator controls and active lease deadlines through their own safety gates. The simulation has no physical control interface.
- The experiments measured traffic, simulated delivery and review outcomes. Host CPU and peak memory were not profiled. A long-duration load test, Python 3.11 validation, interactive operator usability evaluation and independent audit remain open.
