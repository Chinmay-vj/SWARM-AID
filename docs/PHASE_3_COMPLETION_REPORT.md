# Phase 3 completion report

Model 1 runs as an explicitly selected simulator policy. The simulator retains the clock and batches actions. Each drone owns its providers, scoped evidence resolver, memory, lifecycle, health, logs and mock outbox. Providers cannot execute movement through their inputs. The trusted fleet adapter supplies only the drone packet, local connectivity and public mission constraints.

## Changed files

- agents/drone_agent/agent.py orchestrates cycles and validates inbound simulated controls.
- components.py contains configuration, normalized inputs, bounded memory, world queries, lifecycle and health. baselines.py implements four Phase 1 provider protocols. safety.py gates actions and reporting.py builds versioned envelopes.
- simulation/adapters/model1.py binds private instances to the engine. simulation/__main__.py adds --policy model1 and --agent-config.
- configs/model1.json supplies defaults. pyproject.toml includes JSON configuration in package data.
- tests/integration/test_model1.py exercises agents, scoped inputs, memory, safety, controls, deterministic replay and injected failure.
- docs/agents contains ten component guides and six Mermaid diagrams. README.md documents the Windows CLI.

## Verification

Baseline before edits: 56 tests passed. Final Windows CPython 3.12 run: 66 tests passed, including one-, three-, six- and ten-agent fixtures. The two warnings originated in the existing PettingZoo environment registry. Strict mypy checked 37 source files without issues. Ruff lint and formatting checks passed. One- and six-agent flood CLI runs reached the configured horizon. The six-agent seed-42 run produced 30 steps, 5371 symbolic sensor readings, 17.5% grid coverage and zero engine-invalid actions.

A subset of the final d5 cycle log from the six-agent run:

```json
{"agent":"d5","time_ms":2900,"category":"hazard","health":"healthy","memory_entries":128,"action":"REPORT","safety":"approved","outcome":"applied"}
```

## Readiness and limitations

Ready for Phase 4 mock transport integration. Outboxes retain a bounded history of envelopes; publication does not demonstrate receipt. The human_review destination carries evidence for review. The principal and mission revision supplied by the test harness are trusted; the future transport must authenticate them. Default agents remain stationary without authorized movement. Offline movement is conservatively held. The simulator's measured coverage is a software fixture outcome.

Perception resolves symbolic readings. Video, actual media, trained models, calibrated uncertainty, independent sensor timing, durable checkpoints and distributed replay remain future work. Memory restoration covers retained findings. The larger agent snapshot is diagnostic and should never authorize resuming an old lease. No data collection, training, physical drone execution, central command agent or full communications service was added.
