# Phase 7 implementation and verification: backend and database infrastructure

**Phase 8 readiness: READY WITH LIMITATIONS.** The backend, SQLite persistence, authentication, mission-scoped authorization, REST and WebSocket interfaces, and simulator, Model 1 and Model 2 integration work and are tested. **PostgreSQL and PostGIS were not available on the development host: that code path is implemented but unverified.** The independent Phase 7 audit is outstanding. Phase 7 work is uncommitted; Phase 6 was committed beforehand as `d0d471b` (tag `v0.6.0`) so the phases are not mixed.

## Preliminary audit

- Branch `main`; tags `v0.1.0` to `v0.5.0` before Phase 7. The Phase 6 readiness audit (`docs/PHASE_6_AUDIT_REPORT.md`) fixed a revision-supersession defect in Model 2 corroboration before committing Phase 6.
- The `origin` remote is the placeholder `https://github.com/YOUR_USERNAME/SWARM-AID.git` and was left unchanged.
- Environment: Windows 11, CPython 3.12.10 (`.venv`). No backend packages were installed initially; no PostgreSQL, PostGIS or Docker.
- Components named in the brief that did not exist: `HumanOversightManager` (oversight lives in `CommandAgent.consume` plus `validate_decision`), a Model 2 memory abstraction (`CommandAgent` journal checkpoint and restore were used), and domain-event types (created in `backend/services/events.py`).

## What was built

| Area | Implementation |
|---|---|
| Structure | Modular monolith `backend/` (core, database, services, integrations, persistence, realtime, api); app factory with lifespan; `backend/cli.py`. |
| Dependencies | `backend` extra extended with Alembic, pydantic-settings, PyJWT, pwdlib[argon2] and HTTPX (FastAPI 0.165, SQLAlchemy 2.1.9, Alembic 1.20.1, PyJWT 2.15.1, pwdlib 0.4.2, uvicorn 0.54). `httpx` was added to the `dev` extra. Package discovery and mypy now include `backend` and `migrations`. No requirements.txt. |
| Configuration | `BackendSettings` (SWARM_* environment or .env); mandatory signing secret of at least 32 characters; production rules; sanitized configuration errors. Templates in `.env.example` and `configs/backend/*.env.example`. |
| Database | 27 tables, consolidated from the logical entities (mapping in `docs/backend/DATABASE.md`); composite mission-scoped foreign keys; append-only audit triggers; optimistic version columns; UTC timestamps; mission-scoped Model 2 identifiers. |
| Migrations | Alembic revision `0001`; PostgreSQL-only PostGIS extension, generated `geometry(Point,0)` columns and GiST indexes. |
| Security | Argon2id; HS256 JWT with audience, issuer and purpose; refresh rotation with reuse revocation; separate machine credentials; deny-by-default mission-scoped permissions; rate limiting; body limits; redaction; denied-access audit. |
| API | 80 REST operations on 76 paths under `/api/v1` plus health probes; OpenAPI at `/docs`, `/redoc`, `/openapi.json`. |
| Events and real time | 29 typed events in a transactional outbox with per-mission sequences; `/ws/v1/missions/{id}` with first-frame auth, topics, replay, heartbeats with re-authorization, bounded queues and resynchronization. |
| Integration | `RuntimeManager` (bounded, one Model 2 per mission execution) and `Model2Sync` (per-tick, transactional, idempotent persistence of Model 1 reports and Model 2 outputs); human decisions relayed to Model 2's validator. |
| Persistent memory | Checkpoints and read models with SHA-256 digests, SQL and in-memory repositories, restoration through `CommandAgent.restore`, verification endpoint. |
| Evidence | Content-addressed local store with media-type and size checks and path containment. |
| Exports, benchmark, demo | JSON and CSV exports with reproducibility metadata (git commit marked `-dirty` for uncommitted trees); `evaluation/backend_benchmark.py`; `scripts/backend_demo.py`. |
| Infrastructure | Optional `docker-compose.yml` (PostGIS 16-3.4, localhost-only port, health check, volume). Not executed: Docker is not installed. |

## Verification (actual commands and results)

| Command (from the repository root) | Result |
|---|---|
| `.venv\Scripts\python.exe -m pip install -e ".[dev,simulation,backend]"` and `pip check` | Installed; "No broken requirements found." |
| `.venv\Scripts\python.exe -m pytest -q` | **173 passed, 1 skipped** (the PostGIS test; `SWARM_TEST_POSTGRES_URL` not set), 3 warnings: 2 PettingZoo deprecations and 1 Starlette TestClient/httpx deprecation. |
| `.tools\python\python.exe -m pytest -q` (Phase 1-6 environment, no backend extra) | 124 passed; backend tests are excluded automatically. |
| `ruff check .` and `ruff format --check .` | All checks passed; all files formatted. |
| `mypy` (strict, 110 files) | No issues. |
| `alembic upgrade head`, `current`, `history` on a fresh SQLite file | `0001 (head)`; tests also verify downgrade to an empty schema and re-upgrade. |
| Import of `backend.application` from outside the repository | Resolves to the editable install. |
| Simulator CLI `--communication --command-agent` | Unchanged behaviour (standalone runs need no backend). |

Backend tests: 50 tests in `tests/backend_api/` covering database, authentication, authorization, oversight, ingestion, WebSocket, recovery, security, exports and health, geospatial handling and the mission workflow (details in `docs/backend/BACKEND_TESTING.md`). Python 3.11 was not executed.

### Database integration

SQLite only, verified through migrations, constraints, triggers, transactions and concurrency tests. **PostgreSQL and PostGIS: not verified.** The migration's PostgreSQL branch, generated geometry columns, GiST indexes and append-only trigger function have never been executed, and the corresponding test was skipped.

### End-to-end demonstration (`scripts/backend_demo.py`, real uvicorn process)

Two runs (`runs/backend/demo-20261124T100718Z` and `demo-20261124T102937Z`) produced identical results with seed 42:

| Step | Observed |
|---|---|
| Migrate, create synthetic users via CLI, start server | `0001 (head)`; ready in 1.6-2.2 s |
| Coordinator login; create six-agent flood mission (horizon 60, command outage at steps 25-28); start | Mission running |
| First review | Incident `uncertain_need`, urgency `elevated`, 2 supporting observations, recommendation version 2 |
| Approval through Model 2 | `accepted`, "validated by Model 2" |
| Later recommendation from new evidence, rejected | `accepted` by Model 2 |
| Mission end | `completed` at 6000 simulated ms; Model 2 counts: 348 admitted, 12 incidents opened, 31 revisions, 222 corroborations held, 15 expirations |
| Communication interruption | 1 MODEL_2_UNAVAILABLE, 1 MODEL_2_RECOVERED, 2 COMMUNICATION_DEGRADED, 1 COMMUNICATION_RESTORED |
| WebSocket | 986 events received in order (REST: 987; the difference is MISSION_CREATED, before the welcome cursor), 9 heartbeats |
| Abrupt kill and restart | Old server confirmed unreachable; new server ready in 2.1 s; mission summary identical (348 observations) |
| Model 2 recovery | Restored, integrity verified, restored read model equal to the persisted one, 12 incidents |
| Research export (researcher) and CSV | Reproducibility metadata including git commit; ground truth only in the research export |
| Audit history | 12 mission-scoped entries (create, start, pauses, resumes, approve, reject, membership, recovery, exports) |

### Benchmarks

See `docs/research/BACKEND_PERFORMANCE_METRICS.md` (run `benchmark-20261124T102605Z`, all requests succeeded): ingestion through Model 2 at about 12-14 reports/s regardless of fleet size (median latency 186 ms at 3 agents, 1100 ms at 20); duplicate detection median about 3 ms; summary reads median about 6 ms; login median 61 ms; 50 of 50 concurrent WebSocket connections; restart to ready 2.0 s; server peak working set 316 MB.

## Defects found and fixed during Phase 7

1. **Cross-mission identifier collision.** Simulator IDs are deterministic per scenario and seed, so a second identical mission failed on primary-key conflicts. Backend IDs are now mission-scoped, with `model2_id` kept for Model 2 messages. Regression: `test_identical_scenarios_stay_isolated`.
2. Task history ordering was nondeterministic for same-tick events; fixed with an `ordinal` column.
3. Read models used ORM rows after `rollback()` had expired them; read sessions now only close.
4. Duplicate observation ingestion required a running mission; it now returns the stored message ID.
5. Completion reason always said "horizon reached"; it now records the engine reason (`horizon` or `inactive`).
6. Configuration validation errors echoed all settings, including database URLs with passwords; now sanitized. Regression test added.
7. An unenforced `feedback.prioritize` permission was removed so the documented matrix matches enforcement.
8. Benchmark methodology: per-request HTTP client creation (about 200 ms on Windows) and battery-exhausted missions were corrected before recording results.

## Known limitations and outstanding issues

- PostgreSQL and PostGIS unverified (no server available); Docker Compose not executed. Python 3.11 not executed.
- Single-process runtime: simulations, rate limits and WebSocket state live in one worker; run one uvicorn worker. Simulations do not resume after a restart: they are marked stopped, and Model 2 memory can only be inspected from checkpoints. Router queues and simulator state are not durable.
- API ingestion throughput is bounded by the single Model 2 instance per mission plus SQLite's single writer (about 12-14 reports/s measured).
- **Model 2 behaviour (Phase 6, not changed in Phase 7):** after a human decision, every new corroborating report creates a new incident revision. Follow-up reviews (resolution report, closure) are frequently rejected as `rejected_amendment` because in-flight reports arrive first. While drones keep reporting a cell, new evidence re-opens a resolved incident before closure is possible. Tests exercise closure with one moving drone; clients must re-read and retry. A Model 2 change (for example, holding corroboration briefly after a decision) needs a separate decision.
- Audit records are append-only by trigger but not cryptographically chained; retention pruning is not implemented. No TLS, MFA, secret management or dependency vulnerability scan. Service identities are defined but cannot be issued.
- Not stored: per-packet communication events, system health snapshots, geographic (SRID 4326) geometry.
- `evidence_objects` are not yet linked to `evidence` rows by any producer, because the simulator emits only artifact keys.
- Benchmarks are single-host, short-duration and SQLite-only.

## Phase 8 readiness

READY WITH LIMITATIONS: the dashboard contracts (REST read models, WebSocket protocol, map schema, approval workflow) are implemented, documented in `docs/backend/DASHBOARD_INTEGRATION.md` and exercised by tests and the demonstration. PostgreSQL and PostGIS verification and the independent Phase 7 audit should precede any non-local use. Phase 8 work has not started.
