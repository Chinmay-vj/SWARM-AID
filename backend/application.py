"""FastAPI application factory with explicit lifespan management.

Startup never creates tables (use Alembic) and never starts simulations. Each call returns an
independent application, so tests can run isolated instances side by side.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine

from backend import __version__
from backend.api.dependencies import Container
from backend.api.errors import RequestContextMiddleware, install_error_handlers
from backend.api.v1 import agents, auth, catalog, coordination, incidents, missions, system
from backend.core.config import BackendSettings, load_settings
from backend.core.logging import configure_logging
from backend.database.session import Database, build_engine
from backend.integrations.runtime import RuntimeManager
from backend.monitoring import Metrics
from backend.persistence.evidence_store import LocalEvidenceStore
from backend.realtime.hub import Hub
from backend.services.auth import AuthService
from backend.services.exports import ExportService
from backend.services.missions import MissionService
from backend.services.oversight import OversightService
from backend.services.queries import QueryService

log = logging.getLogger("backend")

DESCRIPTION = """
Integration, persistence and security layer for the SWARM-AID synthetic disaster
search-and-rescue research simulator. Model 1 drone agents and the Model 2 command agent do
all reasoning; this API stores and exposes their outputs and relays authenticated human
decisions. **Simulation only: no physical drone control.** Human decisions remain
authoritative for every consequential outcome.
"""


def build_container(settings: BackendSettings, engine: Engine | None = None) -> Container:
    db = Database(engine or build_engine(settings))
    auth_service = AuthService(db, settings)
    runtime = RuntimeManager(db, settings)
    hub = Hub(db, settings, auth_service)
    runtime.notify = hub.dispatch
    return Container(
        settings=settings,
        db=db,
        auth=auth_service,
        runtime=runtime,
        hub=hub,
        missions=MissionService(
            db, runtime, auth_service, development=settings.environment == "development"
        ),
        queries=QueryService(db, runtime),
        oversight=OversightService(db, runtime),
        exports=ExportService(db),
        evidence=LocalEvidenceStore(
            settings.evidence_dir, settings.evidence_max_bytes, settings.evidence_media_types
        ),
        metrics=Metrics(),
    )


def create_app(settings: BackendSettings | None = None, *, engine: Engine | None = None) -> FastAPI:
    resolved = settings or load_settings()
    configure_logging(resolved.log_level)
    services = build_container(resolved, engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        import asyncio

        from backend.api.v1.system import HEAD_REVISION

        revision = await asyncio.to_thread(services.db.migration_revision)
        if revision != HEAD_REVISION:
            log.error(
                "database schema not at migration head; run: python -m alembic upgrade head",
                extra={"data": {"current": revision, "expected": HEAD_REVISION}},
            )
        else:
            recovered = await asyncio.to_thread(services.runtime.recover_interrupted)
            if recovered:
                log.warning(
                    "marked interrupted missions stopped",
                    extra={"data": {"missions": [str(m) for m in recovered]}},
                )
        try:
            yield
        finally:
            await services.runtime.shutdown()
            await services.hub.close_all()
            services.db.dispose()

    app = FastAPI(
        title=resolved.app_name,
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
        debug=resolved.debug,
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.state.container = services
    install_error_handlers(app)
    if resolved.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(resolved.cors_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        )
    app.add_middleware(
        RequestContextMiddleware,
        max_bytes=resolved.max_request_bytes,
        observe=services.metrics.observe,
    )
    app.include_router(system.public)
    for module in (auth, missions, agents, incidents, coordination, system, catalog):
        app.include_router(module.router, prefix=resolved.api_prefix)

    @app.websocket("/ws/v1/missions/{mission_id}")
    async def mission_socket(websocket: WebSocket, mission_id: UUID) -> None:
        await services.hub.serve(websocket, mission_id)

    return app
