# SWARM-AID

A CPU-only research foundation for drone-assisted civilian disaster search and rescue. Phase 1 provides executable configuration and message validation, ten provider protocols, and architecture and research specifications. Runtime agents, simulation, persistence and operator dashboard are future phases.

## Windows quick start

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
