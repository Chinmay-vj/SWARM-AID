# Phase 13 cluster 3 handoff (not started)

Needs an explicit owner request. Read the cluster 1, cluster 2 and cluster FIX 2 reports; do not
repeat their measurements.

## 13G bounded symbolic scalability

20 agents took 51–61 ms per tick (13A). Do not change random streams. Engine, sensor, messaging
and fleet changes can alter learned-policy behaviour without failing the checkpoint identity check:
require trace equality on development seeds. No movement or coordination optimization.

## 13H final verification

PostgreSQL and dashboard verification are now possible. Open: timeout handling and render-level
dashboard performance; `system_demo.py`; frontend dependency advisories; RTX 2060.

## Environment

- Node: add `D:\SWARM-AID-DATA\tools\node-v24.22.3-win-x64` to `PATH` for the session.
- PostgreSQL (stopped), start in a window you can leave open:
  `D:\SWARM-AID-DATA\tools\pg16\pgsql\bin\pg_ctl.exe start -D D:\SWARM-AID-DATA\postgres\data-fix2 -l D:\SWARM-AID-DATA\postgres\fix2.log`
- Credentials: `D:\SWARM-AID-DATA\postgres\fix2*.secrets.json`. Never copy them into the repository.
- PostGIS test: set `SWARM_TEST_POSTGRES_URL`. Backend suite on PostgreSQL: also set
  `SWARM_TEST_BACKEND_ON_POSTGRES=1` (empties every table of that database).
- Connected browser tests:
  `D:\SWARM-AID-DATA\runs\phase13\cluster-fix2\restart_e2e_backend.py`, then in `frontend` set
  `E2E_PASSWORD` and run `npm run test:e2e:connected`.

## Carried restrictions

No training. Learned operator-facing integration blocked (D3). Checkpoints unchanged (D2). New
baselines deferred (D8). Seeds 900000–900099 locked, 42–46 retired. Artifacts on D:. No push
without approval.
