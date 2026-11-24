# Development roadmap

| Phase | Deliverable | Exit gate |
|---|---|---|
| 1 · Contracts | Architecture, provider ports, versioned wire data, config and Windows validation | Contract suite, Ruff and strict mypy pass |
| 2 · Headless simulation | Seeded grid, scoped sensors, mock perception, per-drone state machine, independent safety gate and fault-injectable transport | Two-drone fixture reproduces a trace, respects visibility, holds on lease expiry and accounts for lost messages |
| 3 · Command integration | Evidence association, assessment, validation and replayable human-decision ledger | Duplicate input, stale revision and unsupported recommendation tests pass |
| 4 · Human interface | FastAPI/WebSocket adapters, PostgreSQL/PostGIS persistence and operator dashboard | Inspect evidence, approve/reject and override with a traceable audit record |
| 5 · Research evaluation | Baselines, modality and assessment ablations, failure sweeps and reproducible analytics | Frozen protocol and independent reproduction of a held-out run |
| Future · Learned providers | Optional pretrained, MAPPO, QMIX or other trained providers | Separate authorization, data governance and matched comparison plan |

Phase 2 starts with the simulation specification and a versioned scenario fixture. Pin the run environment, define exact scenario parameters and exercise the private-view boundary before implementing coordination policies.
