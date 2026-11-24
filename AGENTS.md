# Working in SWARM-AID

Read README.md, docs/DEVELOPMENT_ROADMAP.md and the relevant architecture and specification documents before changing a contract. Phase 1 ends at scaffolding, typed interfaces, validation and documentation. Start later phases only on explicit request.

Keep core Python 3.11/3.12 compatible and usable offline on a Windows CPU. Inject providers through interfaces/providers.py. Keep model and transport SDK imports in adapters. Declare dependencies in the appropriate optional extra. Preserve local memory ownership, synthetic evidence provenance, independent action validation and human authority over consequential decisions.

Use deterministic mission ticks and named seed streams in future simulations. Keep ground truth in the simulator/evaluator boundary. Preserve stable observation IDs across forwarding, validate sender identity outside the payload, and apply human decisions to a checked revision. Keep imagery and private artifacts out of logs and version control.

Update wire types, protocol documentation and validation tests together. Version incompatible changes explicitly. Run pytest, Ruff and strict mypy from the repository root and report actual results. Keep research hypotheses separate from results. Record assumptions, limitations and unverified work in the relevant phase report.

## Project context after four delivery phases

The completion reports use the delivery sequence below. The original roadmap assigns command integration and the operator interface to Phases 3 and 4. Those roadmap gates remain open. Use capability names when defining a new phase.

| Delivered scope | Runtime entry points | Focused verification |
|---|---|---|
| 1. Contracts and configuration | `agents/shared/domain.py`, `interfaces/providers.py`, `communication/messages.py`, `configs/settings.py` | `tests/unit/test_contracts.py` |
| 2. Seeded symbolic simulator | `simulation/core/engine.py` owns the world and mission clock. `simulation/sensors/mock.py` builds local observations. Scenario fixtures live in `configs/scenarios/`. | `tests/integration/test_simulation.py` |
| 3. Model 1 drone agents | `simulation/adapters/model1.py` constructs one `DroneAgent` per drone. The cycle in `agents/drone_agent/agent.py` calls injected providers and checks the proposed action through `safety.py` before the engine resolves movement. | `tests/integration/test_model1.py` |
| 4. Simulated communications | `communication/network.py` owns routing, session binding, queues and receipts. `simulation/adapters/communications.py` advances the router and hosts mock command and operator endpoints. | `tests/integration/test_transport.py` |

Trace an end-to-end run from `simulation/__main__.py`. The default policy is stationary. Use `--policy model1` for the local agent loop or `--communication` for that loop with transport. The default Model 1 configuration disables movement. A representative offline invocation from the repository root is:

```powershell
.tools\python\python.exe -m simulation --scenario flood_basic --agents 6 --seed 42 --communication --headless
```

Model 2, a persistent decision ledger, the backend and the operator dashboard remain design work. The Pygame viewer is a simulator debugging tool. For experiment interpretation, read `docs/PHASE_4_AUDIT_REPORT.md` and `evaluation/results.py`. A transport receipt records inbox delivery. Application acceptance and a human decision require separate evidence.
