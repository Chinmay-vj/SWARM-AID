# Phase 2 completion report

The CPU simulation runs six independent drones by default. Seven JSON scenarios exercise flood, wildfire, earthquake, sensor noise, multiple people, a drone failure and a link outage. Headless execution, seeded reset, simultaneous movement validation, symbolic sensing, delayed evidence reporting, experiment exports and two viewer modes are implemented.

## Implementation inventory

| Path | Work |
|---|---|
| simulation/core | Validated configuration, private engine state, clock, event schedule, energy, communication fixtures and actions |
| simulation/environments and simulation/entities | Disaster registry, terrain rules and typed synthetic entities |
| simulation/sensors | Six symbolic modalities, noise, occlusion, dropout and latency |
| simulation/policies.py and simulation/__main__.py | Three baseline policies and command line |
| simulation/adapters and simulation/visualization | PettingZoo parallel environment and Pygame viewer |
| configs/scenarios | Seven packaged JSON configurations |
| evaluation/results.py | Metric definitions, JSON manifests and companion CSV |
| tests/integration/test_simulation.py | Episode, reproducibility, observation, safety, network and adapter tests |
| docs/simulation | Ten design and usage guides, including six diagrams |
| README.md and pyproject.toml | Windows setup, package discovery, scenario package data and static-check scope |

The engine reuses the Phase 1 SensorFrame, Evidence, Cell and Envelope types. A separate discrete action space supports one-step testing. Related sensor and environment rules share modules. No agent workflow, real transport, model training or dataset was introduced. Mypy targets the Windows Python 3.12 verification environment because its installed NumPy stubs use 3.12 syntax.

## Verification and limits

On Windows CPython 3.12, pytest executed 56 passing cases, including PettingZoo parallel_api_test and a dummy SDL render of both viewer modes. PettingZoo emitted two upstream deprecation warnings. Ruff passed. Strict mypy passed across 30 source files. The seven fixture episodes were reset and replayed, and their exported JSON metrics checked. Interactive display/input and installation on a fresh machine were not manually verified.

The stationary six-drone flood CLI at seed 42 reached the 30-step horizon after 3000 simulated milliseconds. Measured cell coverage was 0.175, with 5371 captured symbolic readings, one unique simulated person detected and 180 battery percentage points consumed across the fleet. These figures describe the fixture only.

Phase 3 can use the headless environment and evidence contracts for integration. The link fixture has no durable receipt store, authority reconciliation or incident processing. Disconnected movement is conservatively held. Terrain events and sensor error probabilities are abstract. Research comparisons still require frozen assumptions, policy-independent matching and the broader Phase 1 evaluation protocol.
