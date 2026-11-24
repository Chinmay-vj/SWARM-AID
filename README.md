# SWARM-AID

Phase 2 adds a CPU-only symbolic disaster simulator, seven JSON scenarios, a PettingZoo parallel adapter and a Pygame debug viewer. The human dashboard and learned policies are future work.

## Model 1 on Windows

Select the independent CPU mock agents explicitly. From the repository root, after installing the simulation extra:

```powershell
.\.venv\Scripts\python -m simulation --scenario flood_basic --agents 1 --seed 42 --policy model1 --headless
.\.venv\Scripts\python -m simulation --scenario flood_basic --agents 6 --seed 42 --policy model1 --headless --agent-config configs/model1.json
```

Each run prints the latest decision per agent and the episode metrics. The default configuration authorizes stationary observations and reports. The simulator retains the Phase 2 policies and their existing defaults.

- [Model 1 implementation](docs/agents/MODEL_1_IMPLEMENTATION.md)
- [Phase 3 report](docs/PHASE_3_COMPLETION_REPORT.md)

## Windows simulation quick start

From the repository root with Python 3.12 installed, run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev,simulation]"
.\.venv\Scripts\python -m simulation --scenario flood_basic --agents 6 --seed 42 --headless --output runs
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

The config command prints the validated defaults from configs/default.toml. Applications can pass a different Path to configs.settings.load_settings. The core-only install is pip install -e . inside the virtual environment. The simulation and backend extras are reserved for later phases. No credentials, database, Docker service, GPU or training data are required.

## Reading the design

Start with the system architecture for component ownership, then follow a report through the communication and incident specifications. The simulation specification defines the first executable scenario and its acceptance checks. The completion report includes the repository inventory and verification results.

- [System architecture](docs/architecture/SYSTEM_ARCHITECTURE.md)
- [Message protocol](docs/specifications/MESSAGE_PROTOCOL.md)
- [Simulation specification](docs/specifications/SIMULATION_SPECIFICATION.md)
- [Experimental design](docs/research/EXPERIMENTAL_DESIGN.md)
- [Roadmap](docs/DEVELOPMENT_ROADMAP.md)
- [Phase 1 report and file inventory](docs/PHASE_1_COMPLETION_REPORT.md)
