# SWARM-AID

Phase 2 adds a CPU-only symbolic disaster simulator, seven JSON scenarios, a PettingZoo parallel adapter and a Pygame debug viewer. The human dashboard and learned policies are future work.

## Simulated communication on Windows

From the project root after installing the simulator, run:

```powershell
.\.venv\Scripts\python -m simulation --communication --scenario flood_basic --agents 6 --seed 12900 --headless
.\.venv\Scripts\python -m simulation --communication --scenario flood_network_delay --agents 6 --seed 12900 --headless
.\.venv\Scripts\python -m simulation --communication --scenario flood_server_unavailable --agents 6 --seed 12900 --headless --output runs
```

The switch selects Model 1 and injects a deterministic in-process transport. Each exported experiment has a simulation JSON/CSV pair, communication metrics JSON and a communication event JSONL sharing its run ID. Mock command and human endpoints retain received envelopes. See the [implementation guide](docs/communication/COMMUNICATION_IMPLEMENTATION.md) and [Phase 4 completion report](docs/PHASE_4_COMPLETION_REPORT.md).

## Model 1 on Windows

Select the independent CPU mock agents explicitly. From the repository root, after installing the simulation extra:

```powershell
.\.venv\Scripts\python -m simulation --scenario flood_basic --agents 1 --seed 12900 --policy model1 --headless
.\.venv\Scripts\python -m simulation --scenario flood_basic --agents 6 --seed 12900 --policy model1 --headless --agent-config configs/model1.json
```

Each run prints the latest decision per agent and the episode metrics. The default configuration authorizes stationary observations and reports. The simulator retains the Phase 2 policies and their existing defaults.

- [Model 1 implementation](docs/agents/MODEL_1_IMPLEMENTATION.md)
- [Phase 3 report](docs/PHASE_3_COMPLETION_REPORT.md)

## Windows simulation quick start

From the repository root with Python 3.12 installed, run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev,simulation]"
.\.venv\Scripts\python -m simulation --scenario flood_basic --agents 6 --seed 12900 --headless --output runs
.\.venv\Scripts\python -m simulation --scenario wildfire_basic --render
.\.venv\Scripts\python -m simulation --scenario earthquake_basic --policy random
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m mypy
```

The viewer starts paused. Press Space to run, N to step or Tab to cycle views. The workspace-local interpreter under .tools/python can also run these commands.

- [Simulation architecture](docs/simulation/SIMULATION_ARCHITECTURE.md)
- [Phase 2 completion report](docs/PHASE_2_COMPLETION_REPORT.md)



## Core-only setup

From the repository root in PowerShell with Python 3.12 installed (3.11 also supported), run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m configs.settings
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy
```

The config command prints the validated defaults from configs/default.toml. Applications can pass a different Path to configs.settings.load_settings. The core-only install is pip install -e . inside the virtual environment. The simulation extra installs the CPU simulator dependencies. The backend extra is optional. No credentials, database, Docker service, GPU or training data are required.

## Reading the design

Start with the system architecture for component ownership, then follow a report through the communication and incident specifications. The simulation specification defines the first executable scenario and its acceptance checks. The completion report includes the repository inventory and verification results.

- [System architecture](docs/architecture/SYSTEM_ARCHITECTURE.md)
- [Message protocol](docs/specifications/MESSAGE_PROTOCOL.md)
- [Simulation specification](docs/specifications/SIMULATION_SPECIFICATION.md)
- [Experimental design](docs/research/EXPERIMENTAL_DESIGN.md)
- [Roadmap](docs/DEVELOPMENT_ROADMAP.md)
- [Phase 1 report and file inventory](docs/PHASE_1_COMPLETION_REPORT.md)

## Phase 5 cooperative simulation on Windows

From the repository root, use the Python environment installed with the dev and simulation extras. The examples below use the project virtual environment.

```powershell
.\.venv\Scripts\python.exe -m simulation --scenario flood_basic --agents 6 --seed 12900 --headless --coordination independent
.\.venv\Scripts\python.exe -m simulation --scenario flood_basic --agents 6 --seed 12900 --headless --coordination fixed_sector
.\.venv\Scripts\python.exe -m simulation --scenario flood_basic --agents 6 --seed 12900 --headless --coordination shared_information
.\.venv\Scripts\python.exe -m evaluation.experiment_runner --config configs/experiments/phase5_baselines.json
.\.venv\Scripts\python.exe -m evaluation.experiment_runner --config configs/experiments/phase5_faults.json
```

The comparison runner writes one JSON per episode and CSV and JSON summaries under runs/phase5. Replace --headless with --render for the debug viewer. Orange outlines identify outstanding survey targets in the truth view. See the [coordination architecture](docs/coordination/COORDINATION_ARCHITECTURE.md) and [Phase 5 report](docs/PHASE_5_COMPLETION_REPORT.md).

## Phase 6 command agent

From the repository root in PowerShell with the dev and simulation extras installed:

```powershell
.\.venv\Scripts\python.exe -m simulation --command-agent --scenario flood_basic --agents 6 --seed 12900 --headless --output runs/command
.\.venv\Scripts\python.exe -m simulation --command-agent --coordination shared_information --scenario flood_multiple --agents 6 --seed 12900 --headless --output runs/multiple
.\.venv\Scripts\python.exe -m simulation --command-agent --coordination shared_information --scenario flood_server_unavailable --agents 6 --seed 12900 --headless --output runs/outage
.\.venv\Scripts\python.exe -m evaluation.command_agent_experiments --config configs/experiments/phase6_baselines.json
```

The CLI uses deterministic fusion by default. Direct forwarding and per-report assessment are available through command configuration and the experiment runner. See the [Model 2 implementation](docs/command_agent/MODEL_2_IMPLEMENTATION.md) and [Phase 6 report](docs/PHASE_6_COMPLETION_REPORT.md).

## Phase 7 backend

The FastAPI backend in `backend/` persists and serves simulator, Model 1 and Model 2 outputs, relays authenticated human decisions to Model 2 for validation, and streams mission events over WebSockets. It performs no reasoning of its own and has no physical drone control. From the repository root in PowerShell with the dev, simulation and backend extras installed:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,simulation,backend]"
Copy-Item .env.example .env   # then set SWARM_JWT_SECRET (required, >= 32 characters)
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m backend.cli create-user --username admin --role administrator
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe scripts\backend_demo.py              # end-to-end synthetic demonstration
.\.venv\Scripts\python.exe -m evaluation.backend_benchmark      # local benchmark
```

Add `--reload` only for development, never for benchmarks. API documentation is served at http://127.0.0.1:8000/docs. SQLite is the default; PostgreSQL with PostGIS is supported through `SWARM_DATABASE_URL` and the optional `docker-compose.yml`, but was not verified in Phase 7. See [backend architecture](docs/backend/BACKEND_ARCHITECTURE.md), [database](docs/backend/DATABASE.md), [API reference](docs/backend/API_REFERENCE.md), [security](docs/backend/SECURITY.md) and the [Phase 7 report](docs/PHASE_7_COMPLETION_REPORT.md).

## Phase 8 rescue command dashboard

The React + TypeScript dashboard in `frontend/` monitors missions (map, Model 1 fleet, observations, evidence, Model 2 incidents and recommendations, coordination, hazards, communication, events, analytics) and relays human-oversight decisions to the Phase 7 backend. It has two isolated data sources: **Connected simulation** (the backend) and a clearly labelled **Synthetic demo** that runs entirely in the browser. Simulation research only: no physical drone control. With the backend running (see Phase 7 above), from PowerShell:

```powershell
cd frontend
npm ci
npm run dev        # http://127.0.0.1:5173 (proxies /api, /health and /ws to 127.0.0.1:8000)
```

`scripts\start_dashboard.ps1` starts both services after checking prerequisites. Verification: `npm run typecheck`, `npm run lint`, `npm run test`, `npm run test:e2e`, and `npm run test:e2e:connected` with `E2E_PASSWORD` set. See the [frontend README](frontend/README.md), [docs/frontend](docs/frontend/FRONTEND_ARCHITECTURE.md) and the [Phase 8 report](docs/PHASE_8_COMPLETION_REPORT.md). The original presentation MVP is preserved in `frontend/legacy-mvp/`.

## Phase 9 integrated system

Phase 9 integrates and verifies the whole stack (simulator, independent Model 1 agents, simulated communication, coordination, Model 2, backend, database, event stream, dashboard and evaluator) as one local, CPU-only research platform. It adds no models and no datasets. From the repository root in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_system.ps1      # validate, migrate, start backend + dashboard
powershell -ExecutionPolicy Bypass -File scripts\status_system.ps1     # health, database, active missions
powershell -ExecutionPolicy Bypass -File scripts\stop_system.ps1       # graceful; stops only what start_system started
powershell -ExecutionPolicy Bypass -File scripts\start_system.ps1 -Headless -Scenario flood_basic -Agents 6 -Seed 12900

.\.venv\Scripts\python.exe -m orchestration check                       # configuration validation
.\.venv\Scripts\python.exe -m orchestration matrix --config configs\experiments\phase9_smoke.json
.\.venv\Scripts\python.exe scripts\system_demo.py                       # connected demonstration (dev accounts)
```

The dashboard is at http://127.0.0.1:5173 and the API at http://127.0.0.1:8000/docs. See [system architecture](docs/integration/SYSTEM_ARCHITECTURE.md), [operations](docs/integration/SYSTEM_OPERATIONS.md), [component inventory](docs/integration/COMPONENT_INVENTORY.md), [reproducibility](docs/research/REPRODUCIBILITY_GUIDE.md), [CPU baselines](docs/research/CPU_BASELINE_BENCHMARKS.md), the [Phase 9 report](docs/PHASE_9_COMPLETION_REPORT.md) and the [Phase 10 readiness checklist](docs/PHASE_10_READINESS_CHECKLIST.md).

## Phase 10A dataset infrastructure

From the repository root, run `python -m evaluation.data` to validate the candidate registry.
For a deterministic symbolic example, run
`python -m evaluation.data --registry tests/fixtures/data/registry.json tests/fixtures/data/symbolic.json`.
See the [dataset contracts and validation guide](docs/datasets/DATASET_REQUIREMENTS.md) and
[Phase 10A completion report](docs/PHASE_10A_COMPLETION_REPORT.md).

For the subsequent symbolic dataset and field simulations, see the [Model 2 pilot report](docs/PHASE_10E_COMPLETION_REPORT.md) and [field scenario release, baseline results and verification](docs/PHASE_10F_FIELD_REPORT.md).

The [Phase 10G completion report](docs/PHASE_10G_COMPLETION_REPORT.md) records public dataset preprocessing, measured split overlaps and outstanding human review.

The [Phase 10H completion report](docs/PHASE_10H_COMPLETION_REPORT.md) records the final integrity audit and NO-GO training decision. See the [Phase 10 completion report](docs/PHASE_10_COMPLETION_REPORT.md), [training readiness matrix](docs/datasets/TRAINING_READINESS_MATRIX.md), and [Phase 11 handoff](docs/PHASE_11_HANDOFF.md).
