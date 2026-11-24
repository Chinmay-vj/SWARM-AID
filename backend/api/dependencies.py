"""Explicit service container and request dependencies."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query, Request

from backend.core.config import BackendSettings
from backend.core.errors import NotAuthenticated
from backend.core.permissions import Principal
from backend.database.session import Database
from backend.integrations.runtime import RuntimeManager
from backend.monitoring import Metrics
from backend.persistence.evidence_store import LocalEvidenceStore
from backend.realtime.hub import Hub
from backend.services.auth import AuthService
from backend.services.exports import ExportService
from backend.services.missions import MissionService
from backend.services.oversight import OversightService
from backend.services.queries import QueryService


@dataclass
class Container:
    settings: BackendSettings
    db: Database
    auth: AuthService
    runtime: RuntimeManager
    hub: Hub
    missions: MissionService
    queries: QueryService
    oversight: OversightService
    exports: ExportService
    evidence: LocalEvidenceStore
    metrics: Metrics


def container(request: Request) -> Container:
    services: Container = request.app.state.container
    return services


ContainerDep = Annotated[Container, Depends(container)]


def bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise NotAuthenticated("bearer token required")
    return token.strip()


def principal(request: Request, services: ContainerDep) -> Principal:
    token = bearer_token(request)
    with services.db.read() as session:
        resolved = services.auth.resolve(session, token)
    request.state.principal = resolved
    return resolved


PrincipalDep = Annotated[Principal, Depends(principal)]


@dataclass(frozen=True)
class PageParams:
    limit: int
    offset: int


def page_params(
    services: ContainerDep,
    limit: Annotated[int | None, Query(ge=1)] = None,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> PageParams:
    chosen = services.settings.page_size_default if limit is None else limit
    return PageParams(min(chosen, services.settings.page_size_max), offset)


PageDep = Annotated[PageParams, Depends(page_params)]
