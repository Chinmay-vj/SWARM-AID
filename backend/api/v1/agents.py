"""Agents, observation ingestion, observations, evidence and evidence objects."""

import asyncio
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, status
from fastapi.responses import Response
from sqlalchemy import select

from backend.api.dependencies import ContainerDep, PageDep, PrincipalDep
from backend.core.errors import Conflict, Unprocessable
from backend.core.permissions import Permission
from backend.database import models as m
from backend.schemas import (
    AgentHealthIn,
    AgentOut,
    AgentReportOut,
    EvidenceGroupOut,
    EvidenceObjectOut,
    EvidenceOut,
    ObservationIn,
    ObservationIngestResult,
    ObservationOut,
    Page,
)
from backend.services import audit
from backend.services.access import mission_for, owned

router = APIRouter(tags=["agents"])


@router.get("/missions/{mission_id}/agents", response_model=list[AgentOut])
def mission_agents(
    mission_id: UUID, principal: PrincipalDep, services: ContainerDep
) -> list[AgentOut]:
    return services.queries.agents(principal, mission_id)


@router.get("/agents/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: UUID, principal: PrincipalDep, services: ContainerDep) -> AgentOut:
    return services.queries.agent(principal, agent_id)


@router.get("/agents/{agent_id}/status", response_model=Page[AgentReportOut])
def agent_status(
    agent_id: UUID, principal: PrincipalDep, services: ContainerDep, page: PageDep
) -> Page[AgentReportOut]:
    items, total = services.queries.agent_reports(
        principal, agent_id, "status", page.limit, page.offset
    )
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/agents/{agent_id}/health", response_model=Page[AgentReportOut])
def agent_health(
    agent_id: UUID, principal: PrincipalDep, services: ContainerDep, page: PageDep
) -> Page[AgentReportOut]:
    items, total = services.queries.agent_reports(
        principal, agent_id, "health", page.limit, page.offset
    )
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/agents/{agent_id}/location-history", response_model=Page[AgentReportOut])
def agent_locations(
    agent_id: UUID, principal: PrincipalDep, services: ContainerDep, page: PageDep
) -> Page[AgentReportOut]:
    items, total = services.queries.agent_reports(
        principal, agent_id, "health", page.limit, page.offset
    )
    located = [i for i in items if i.location is not None]
    return Page(items=located, total=total, limit=page.limit, offset=page.offset)


@router.get("/agents/{agent_id}/observations", response_model=Page[ObservationOut])
def agent_observations(
    agent_id: UUID, principal: PrincipalDep, services: ContainerDep, page: PageDep
) -> Page[ObservationOut]:
    agent = services.queries.agent(principal, agent_id)
    items, total = services.queries.observations(
        principal,
        agent.mission_id,
        kind=None,
        reporter=None,
        outcome=None,
        bbox=None,
        since_ms=None,
        sort="-observed_ms",
        limit=page.limit,
        offset=page.offset,
        agent_id=agent_id,
    )
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


# ----- ingestion (agent identities) --------------------------------------------------------
@router.post(
    "/missions/{mission_id}/observations",
    response_model=ObservationIngestResult,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["ingestion"],
)
async def ingest_observation(
    mission_id: UUID, body: ObservationIn, principal: PrincipalDep, services: ContainerDep
) -> ObservationIngestResult:
    """Authenticated agent report. The reporter identity comes from the credential, never the
    body. Incident classification is not accepted here: Model 2 performs assessment."""

    def check() -> UUID | None:
        with services.db.read() as session:
            mission_for(session, principal, mission_id, Permission.OBSERVATION_INGEST)
            existing = session.scalar(
                select(m.Observation).where(
                    m.Observation.mission_id == mission_id,
                    m.Observation.observation_id == body.observation_id,
                )
            )
            if existing is None:
                return None
            same = (
                existing.reporter == principal.subject
                and existing.kind == body.kind
                and existing.observed_ms == body.observed_ms
                and existing.confidence == body.confidence
            )
            if not same:
                raise Conflict(
                    "observation identity reused with different content", code="conflict"
                )
            return existing.message_id

    if principal.kind != "agent":
        raise Unprocessable(
            "observation ingestion requires an agent identity", code="agent_required"
        )
    previous = await asyncio.to_thread(check)
    if previous is not None:
        return ObservationIngestResult(
            observation_id=body.observation_id,
            message_id=previous,
            outcome="duplicate",
            duplicate=True,
        )
    outcome, message_id = await asyncio.to_thread(
        services.runtime.ingest_observation,
        mission_id,
        principal.subject,
        body.kind,
        body.observation_id,
        body.cell,
        body.observed_ms,
        body.confidence,
        body.label,
        [e.model_dump() for e in body.evidence],
    )
    await services.hub.dispatch(mission_id)
    return ObservationIngestResult(
        observation_id=body.observation_id,
        message_id=message_id,
        outcome=outcome,
        duplicate=outcome == "duplicate",
    )


@router.post(
    "/missions/{mission_id}/agent-health",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AgentOut,
    tags=["ingestion"],
)
def report_health(
    mission_id: UUID, body: AgentHealthIn, principal: PrincipalDep, services: ContainerDep
) -> AgentOut:
    """Out-of-band health report from an agent identity (supplements simulated transport)."""
    with services.db.transaction() as session:
        mission_for(session, principal, mission_id, Permission.AGENT_REPORT)
        agent = session.scalar(
            select(m.Agent).where(
                m.Agent.mission_id == mission_id, m.Agent.agent_key == principal.subject
            )
        )
        if agent is None:
            raise Conflict("agent is not registered for this mission", code="not_registered")
        state = session.get(m.MissionRuntime, mission_id)
        now = state.last_sim_ms if state else 0
        agent.battery_fraction = body.battery_fraction
        agent.degraded_sensors = list(body.degraded_sensors)
        agent.last_report_ms = now
        if body.cell:
            agent.x, agent.y, agent.crs, agent.uncertainty = (
                float(body.cell[0]),
                float(body.cell[1]),
                m.LOCAL_CRS,
                0.5,
            )
            agent.last_location_ms = now
        session.add(
            m.AgentReport(
                mission_id=mission_id,
                agent_id=agent.id,
                report_type="health",
                sim_time_ms=now,
                battery_fraction=body.battery_fraction,
                x=float(body.cell[0]) if body.cell else None,
                y=float(body.cell[1]) if body.cell else None,
                crs=m.LOCAL_CRS if body.cell else None,
                uncertainty=0.5 if body.cell else None,
                details={"degraded_sensors": list(body.degraded_sensors), "channel": "api"},
            )
        )
        from backend.services.events import EventType, emit

        emit(
            session,
            mission_id,
            EventType.AGENT_HEALTH_UPDATED,
            source=principal.subject,
            resource_type="agent",
            resource_id=agent.id,
            payload={
                "agent_key": agent.agent_key,
                "battery_fraction": body.battery_fraction,
                "channel": "api",
            },
            sim_time_ms=now,
        )
        session.flush()
        return services.queries.agent_out(agent)


# ----- observations and evidence -----------------------------------------------------------
@router.get(
    "/missions/{mission_id}/observations",
    response_model=Page[ObservationOut],
    tags=["observations"],
)
def list_observations(
    mission_id: UUID,
    principal: PrincipalDep,
    services: ContainerDep,
    page: PageDep,
    kind: Literal["environment", "hazard", "possible_human"] | None = None,
    reporter: Annotated[str | None, Query(max_length=100)] = None,
    outcome: Annotated[str | None, Query(max_length=32)] = None,
    since_ms: Annotated[int | None, Query(ge=0)] = None,
    bbox: Annotated[
        str | None, Query(description="x0,y0,x1,y1 in the mission's local grid", max_length=80)
    ] = None,
    sort: Literal["observed_ms", "-observed_ms"] = "-observed_ms",
) -> Page[ObservationOut]:
    box: tuple[float, float, float, float] | None = None
    if bbox:
        try:
            x0, y0, x1, y1 = (float(v) for v in bbox.split(","))
        except ValueError as exc:
            raise Unprocessable("bbox must be four comma-separated numbers") from exc
        box = (x0, y0, x1, y1)
    items, total = services.queries.observations(
        principal,
        mission_id,
        kind=kind,
        reporter=reporter,
        outcome=outcome,
        bbox=box,
        since_ms=since_ms,
        sort=sort,
        limit=page.limit,
        offset=page.offset,
    )
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/observations/{observation_id}", response_model=ObservationOut, tags=["observations"])
def get_observation(
    observation_id: UUID, principal: PrincipalDep, services: ContainerDep
) -> ObservationOut:
    return services.queries.observation(principal, observation_id)


@router.get(
    "/observations/{observation_id}/evidence",
    response_model=list[EvidenceOut],
    tags=["observations"],
)
def observation_evidence(
    observation_id: UUID, principal: PrincipalDep, services: ContainerDep
) -> list[EvidenceOut]:
    return services.queries.evidence(principal, observation_id)


@router.get("/evidence-groups/{group_id}", response_model=EvidenceGroupOut, tags=["observations"])
def evidence_group(
    group_id: UUID, principal: PrincipalDep, services: ContainerDep
) -> EvidenceGroupOut:
    return services.queries.evidence_group(principal, group_id)


@router.post(
    "/missions/{mission_id}/evidence-objects",
    response_model=EvidenceObjectOut,
    status_code=status.HTTP_201_CREATED,
    tags=["evidence"],
)
async def upload_evidence(
    mission_id: UUID,
    request: Request,
    principal: PrincipalDep,
    services: ContainerDep,
    content_type: Annotated[str, Header()] = "application/octet-stream",
) -> EvidenceObjectOut:
    """Store a synthetic evidence object (raw request body). Content-addressed; no paths."""
    data = await request.body()
    media_type = content_type.split(";")[0].strip().lower()

    def store() -> EvidenceObjectOut:
        with services.db.transaction() as session:
            mission_for(session, principal, mission_id, Permission.OBSERVATION_INGEST)
            key, digest, size = services.evidence.put(mission_id, data, media_type)
            row = session.scalar(
                select(m.EvidenceObject).where(
                    m.EvidenceObject.mission_id == mission_id, m.EvidenceObject.sha256 == digest
                )
            )
            if row is None:
                row = m.EvidenceObject(
                    mission_id=mission_id,
                    sha256=digest,
                    media_type=media_type,
                    size_bytes=size,
                    storage_key=key,
                    source_subject=principal.subject,
                )
                session.add(row)
                session.flush()
                audit.record(
                    session,
                    principal,
                    "evidence.store",
                    resource_type="evidence_object",
                    resource_id=row.id,
                    mission_id=mission_id,
                    details={"sha256": digest, "size": size, "media_type": media_type},
                )
            return EvidenceObjectOut.model_validate(row)

    return await asyncio.to_thread(store)


@router.get("/evidence-objects/{object_id}", response_model=EvidenceObjectOut, tags=["evidence"])
def evidence_object(
    object_id: UUID, principal: PrincipalDep, services: ContainerDep
) -> EvidenceObjectOut:
    with services.db.read() as session:
        return EvidenceObjectOut.model_validate(
            owned(session, principal, m.EvidenceObject, object_id)
        )


@router.get("/evidence-objects/{object_id}/content", tags=["evidence"])
def evidence_content(object_id: UUID, principal: PrincipalDep, services: ContainerDep) -> Response:
    with services.db.read() as session:
        row = owned(session, principal, m.EvidenceObject, object_id)
        key, media_type = row.storage_key, row.media_type
    return Response(
        services.evidence.read(key),
        media_type=media_type,
        headers={"X-Content-Type-Options": "nosniff", "Content-Disposition": "attachment"},
    )
