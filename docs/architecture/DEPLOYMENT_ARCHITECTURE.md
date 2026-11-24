# Deployment stages

| Stage | Processes and storage | Entry point |
|---|---|---|
| Phase 1 | One Windows CPU process, Python 3.11/3.12, local TOML and typed values | Run configuration check or pytest from repository root |
| Simulation | One deterministic scheduler, isolated logical agents and an in-process asynchronous broker | Future headless runner; optional Pygame observer |
| Command service | FastAPI ingestion and WebSocket updates, SQLAlchemy transaction boundary, PostgreSQL plus PostGIS | Future local server with role-scoped endpoints |
| Dashboard | React, TypeScript and Tailwind CSS client | Future authenticated operator session |
| Reproducible packaging | Git revision plus pinned run manifest; optional Docker services | Future CPU-only integration profile |

The simulation clock advances independently of wall time. AsyncIO transport drains eligible events at a scheduler barrier. Rendering is an observer and may skip frames. A future split into processes must serialize exactly the in-process wire schema. Store imagery separately from incident records; the scoped sensor resolver serves local samples in simulation and the backend mediates retrieval for dashboard users.

The default install requires Pydantic. Development adds pytest, Ruff and mypy. NumPy, PettingZoo, Gymnasium and Pygame are reserved for simulation. The backend extra covers Python service adapters; PostgreSQL, PostGIS, Docker and browser tooling are future system dependencies. The ML extra is intentionally empty pending selection of a research provider. LangGraph is optional future work.
