# Backend testing

Run from the repository root with the project virtual environment (dev, simulation and backend extras installed):

```powershell
.\.venv\Scripts\python.exe -m pytest -q                       # all phases
.\.venv\Scripts\python.exe -m pytest tests/backend_api -q     # backend only
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy
```

Backend tests live in `tests/backend_api/` (that name avoids shadowing the `backend` package). Fixtures are in `tests/backend_support.py` and are registered by `tests/conftest.py` only when FastAPI is installed, so the Phase 1-6 suite still runs without the backend extra (`.tools\python\python.exe -m pytest`).

Every test gets a fresh SQLite database copied from a template that the real Alembic migration built (not `create_all`), with its own app instance, `TestClient` and lifespan. Simulations run with no tick delay; oversight tests pace ticks at 40 ms and pause the mission to act deterministically.

| File | Tests | Covers |
|---|---:|---|
| test_database.py | 8 | Upgrade, downgrade and re-upgrade; no-op upgrade over existing rows; foreign and unique keys; composite-key cross-mission rejection; append-only audit triggers; rollback; optimistic concurrency; UTC enforcement; database-unavailable mapping |
| test_auth.py | 7 | Login, invalid and expired tokens, forged and `alg=none` tokens, wrong issuer, audience and purpose; refresh rotation and reuse revocation; logout; deactivation; machine identity separation and revocation; login rate limit; settings validation |
| test_authorization.py | 4 | Matrix deny-by-default; roles; cross-mission 404s; administrators cannot control or decide; mass-assignment rejection; stale `PATCH`; lifecycle state machine; denied-access audit |
| test_oversight.py | 5 | Approval accepted by Model 2 and persisted; idempotency; outdated version; unauthorized approval and closure; rejection, resolution and closure through Model 2; override; alert acknowledgement; decisions need a running mission |
| test_ingestion.py | 3 | Agent reports through Model 2 into incidents; duplicate, conflict and future-time handling; classification fields refused; identity and mission scoping; evidence objects, media types, size limits and path traversal |
| test_websocket.py | 3 | Unauthenticated, forged, non-member and unknown-mission rejection; live ordered delivery; cross-mission isolation; topic filters; replay; ping; heartbeat; slow-client cutoff |
| test_recovery.py | 5 | Restart persistence; interrupted missions stopped on startup; Model 2 restoration matches the read model; corruption detected; database failure mid-tick loses nothing; Model 2 and communication outage events |
| test_security.py | 6 | SQL injection strings; scenario path traversal; error hygiene and request IDs; request size limit; credential redaction in logs and audit; configuration errors never echo values |
| test_exports_health_geo.py | 5 | Operational and research export separation, CSV, audit; health and readiness (including an unmigrated database); OpenAPI; CRS validation; bounding-box query; **PostGIS test (skipped without `SWARM_TEST_POSTGRES_URL`)** |
| test_mission_workflow.py | 4 | Full mission persistence; identical-scenario isolation regression; concurrent simulation limit; Phase 5 coordination, sectors, coverage, map and metrics without ground truth |

The PostGIS test is skipped unless `SWARM_TEST_POSTGRES_URL` points to a disposable PostgreSQL database with PostGIS available. A skipped test is reported as skipped, never as passed.

Defects found by these tests and fixed in Phase 7: deterministic simulator IDs colliding across missions, nondeterministic task-history ordering, read models using expired rows after session close, a missing-runtime path in duplicate ingestion, misleading completion reasons, and configuration errors echoing the database URL. The end-to-end demonstration (`python scripts/backend_demo.py`) and the benchmark (`python -m evaluation.backend_benchmark`) run against a real uvicorn process and write their measured output under `runs/backend/`.
