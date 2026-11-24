# System operations: orchestration, configuration, profiles, startup and shutdown

All commands are Windows PowerShell from `D:\SWARM-AID` unless noted. Everything binds to
`127.0.0.1`, runs on a CPU and needs no cloud service, GPU or paid API.

## 1. Orchestration ownership

There is one mission lifecycle manager: `backend.integrations.runtime.RuntimeManager`. Phase 9
adds `orchestration/` around it without duplicating it:

| Concern | Owner |
|---|---|
| Validate configuration before anything starts | `orchestration/checks.py` (`python -m orchestration check`) |
| Build one integrated mission context | `backend.integrations.simulation_adapter.SimulationContext` (shared by backend and headless) |
| Run, pause, resume, stop, persist, recover missions | `RuntimeManager` (backend only) |
| Headless execution of one mission | `orchestration/headless.py` (`run`) |
| Integration experiment matrix | `orchestration/matrix.py` (`matrix`) |
| Phase 5/6 research experiments | existing runners, dispatched by `experiment` |
| Reproducibility manifest | `orchestration/manifest.py` (also used for backend `git_commit`) |
| Backend process with graceful stop | `orchestration/serve.py` (`serve`, started by `start_system.ps1`) |
| Status | `orchestration/status.py` (`status`) and `scripts/status_system.ps1` |
| Start/stop of local services | `scripts/start_system.ps1`, `scripts/stop_system.ps1` |

A simulation is started only by `POST /missions/{id}/start` (backend) or by the headless runner
in its own process. `RuntimeManager.start` refuses a second start of the same mission
(`409 duplicate_execution`) and enforces `SWARM_MAX_CONCURRENT_SIMULATIONS`.

## 2. Configuration

| Source | Read by | Validated by | Notes |
|---|---|---|---|
| `configs/scenarios/*.json` | simulator, backend, runners | `Scenario`, `MissionConfig.validated()` | 22 fixtures; identifiers must match `^[a-z0-9_]{1,64}$` and exist; never a client-supplied path |
| Mission config (API body or CLI flags) | backend, headless runner | `MissionConfig` (extra fields forbidden) | `scenario_id`, `agents` 1–20, `seed`, `horizon` ≤ 5000, `coordination`, `command_mode`, `outage_steps` |
| `configs/model1.json` | `Fleet` | `agents.drone_agent.components.Settings` | Coordination runs enable movement |
| `configs/model2.json` | `simulation --command-config` only | `agents.command_agent.agent.Settings` | Equals the defaults; backend and runners use defaults plus `command_mode` |
| `configs/experiments/phase5_*.json`, `phase6_*.json`, `phase9_*.json` | runners | their `Experiment` / `MatrixPlan` models | Phase 9 plans are bounded by `max_runs` |
| `configs/default.toml` | `tests/unit/test_contracts.py` | `configs.settings.Settings` | Phase 1 contract example; not read at runtime |
| `.env` / `SWARM_*` environment | backend, Alembic, CLI | `BackendSettings` | `SWARM_JWT_SECRET` mandatory (≥ 32 characters) |
| `frontend/.env` (`VITE_*`) | Vite bundle | `orchestration check` scans names | Never secrets: bundled into the browser |
| `configs/backend/*.env.example` | documentation | — | Examples without secrets |

Precedence for backend settings: process environment, then `.env`, then defaults. Alembic uses
the same precedence (`configured_database_url`). Scenario values are overridden only by the
whitelisted mission fields above.

Validate before starting:

```powershell
.\.venv\Scripts\python.exe -m orchestration check                     # development profile
.\.venv\Scripts\python.exe -m orchestration check --profile headless  # no backend needed
```

The check validates Python, dependency groups, every scenario (including placement),
experiment plans, agent settings, backend settings (field names only, no values), the database
migration revision, the bind address, CORS and frontend variable names. Exit code 1 on any
error. Invalid mission configurations are also rejected by the API before a mission is created
(422) and before start.

## 3. Execution profiles

| Profile | What runs | Command | Mutates the backend database |
|---|---|---|---|
| Local development | backend + dashboard | `scripts\start_system.ps1` | yes (dev DB from `.env`) |
| Headless simulation | one integrated mission in-process | `scripts\start_system.ps1 -Headless -Scenario flood_basic -Agents 6 -Seed 42` or `python -m orchestration run ...` | no |
| Connected simulation | backend + dashboard, missions created by an authorized user | as development; sign in with "Connected simulation" | yes |
| Synthetic demonstration | dashboard only, labelled synthetic data | `scripts\start_system.ps1 -FrontendOnly`, choose "Synthetic demo" on sign-in | no (no `/api` or `/ws` requests; tested) |
| Research evaluation | matrix or Phase 5/6 runners | `python -m orchestration matrix --config configs\experiments\phase9_smoke.json` | no (writes `runs/`) |
| Automated testing | pytest, Vitest, Playwright | see END_TO_END_TESTING.md | pytest uses disposable SQLite copies in the system temp folder |

No profile switches silently: the dashboard's data source is chosen at sign-in, shown in the top
bar and changing it signs the user out and clears caches. A connected failure is shown as a
failure; synthetic data is never substituted.

## 4. Start, status and stop

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_system.ps1     # backend + dashboard
powershell -ExecutionPolicy Bypass -File scripts\status_system.ps1
powershell -ExecutionPolicy Bypass -File scripts\stop_system.ps1
```

`start_system.ps1` (switches `-BackendOnly`, `-FrontendOnly`, `-Headless`):

1. Checks the `.venv` Python version (3.11/3.12), Node.js ≥ 20 and `frontend/node_modules`.
   It never installs Docker, PostgreSQL or npm packages.
2. Runs `orchestration check`; applies `alembic upgrade head` if only the migration is behind.
3. Backend: if a process started by this script is running, does nothing. If port 8000 is
   held by something else, uses it when `/health/live` answers, otherwise stops with an error,
   and never terminates that process. Otherwise starts `python -m orchestration serve --log
   runs\system\backend.log` hidden, waits for `/health/ready` (60 s) and records the PID and
   process start time in `runs\system\backend.process.json`.
4. Dashboard: same ownership rules for port 5173; starts Vite through `cmd /c` with output in
   `runs\system\frontend.log`, records the `node` PID and waits for HTTP 200.
5. Prints the URLs, PIDs and the status and stop commands. Secrets are never printed.

Services are started without inherited console handles, so the script's own output can be piped
or redirected (verified: returns in 8 s with output redirected to a file).

`status_system.ps1` lists managed processes (alive only if PID and start time match) and runs
`python -m orchestration status`: backend live/ready probes, database dialect and revision,
active missions with persisted Model 2 and communication state, dashboard reachability and the
WebSocket endpoint. Per-connection WebSocket metrics are in `GET /api/v1/system/health`
(administrator).

`stop_system.ps1` stops only processes whose PID and start time match the start record:

1. Backend: writes `runs\system\backend.stop`. The server sets uvicorn's `should_exit`, so the
   lifespan shutdown runs: new requests stop, active and paused missions are stopped and
   recorded (`status=stopped`, reason `backend shutdown`), pending tick data is persisted,
   WebSocket connections close and database connections are disposed. Only after 45 s without
   exit is the owned process (and its interpreter child, checked by parent PID) terminated,
   with a warning; such missions are marked stopped at the next start.
2. Dashboard: the owned `node` process is terminated (it holds no mission state).
3. Any other process on ports 8000/5173 is reported and left running.

Verified in Phase 9: five graceful stop/start cycles; held missions were recorded as stopped with reason
"backend shutdown"; no Python or Node process remained; data survived the restart.

Limitations: the stop signal is a local file, so any local account with write access to
`runs\system` can stop the backend. The scripts are Windows PowerShell only. Vite's log is not
size-rotated (it writes little).

## 5. Dependencies and setup

Verified on Windows 11, Python 3.12.10, Node.js 23.11.0 (any Node 20+ is expected to work;
23.x is not an LTS release), npm 10.9.2:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,simulation,backend]"
.\.venv\Scripts\python.exe -m pip check                 # "No broken requirements found."
Copy-Item .env.example .env                              # set SWARM_JWT_SECRET (>= 32 chars)
.\.venv\Scripts\python.exe -m alembic upgrade head
$env:SWARM_NEW_USER_PASSWORD = "<choose>"
.\.venv\Scripts\python.exe -m backend.cli create-user --username coordinator --role coordinator
cd frontend; npm ci; cd ..
```

Optional dependency groups are unchanged: `dev`, `simulation` (numpy, gymnasium, pettingzoo,
pygame), `backend`, `ml` (empty). No new Python or JavaScript dependency was added in Phase 9.

## 6. Logging

- Backend loggers emit one JSON object per line (`time`, `level`, `logger` as the component,
  `request_id`, `message`, optional `data`) via `backend/core/logging.py`, with a single handler
  (no duplicates). Credential-like keys and token-like strings are redacted.
- Mission and agent identifiers appear in `data` where the code supplies them; there is no
  dedicated mission or agent field.
- Exceptions are logged with the exception type, not the traceback (keeps paths and values out
  of logs, but limits diagnosis).
- Uvicorn access logs record method, path and status; tokens are never in URLs.
- Level: `SWARM_LOG_LEVEL` (`DEBUG`, `INFO`, `WARNING`, `ERROR`).
- Size: the owned server's log rotates at 10 MiB keeping one previous copy.
- Ground truth, private agent memory and evidence content are not logged.
