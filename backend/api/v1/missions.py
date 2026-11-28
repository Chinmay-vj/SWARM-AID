"""Mission management, lifecycle, membership, events, audit and exports."""

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, status
from fastapi.responses import PlainTextResponse, Response

from backend.api.dependencies import ContainerDep, PageDep, PrincipalDep
from backend.core.errors import AppError
from backend.schemas import (
    AgentCredentialCreate,
    AgentCredentialOut,
    AuditOut,
    EventOut,
    LifecycleRequest,
    MembershipCreate,
    MembershipResponse,
    MissionCreate,
    MissionOut,
    MissionPatch,
    MissionSummary,
    Page,
    RecoveryReport,
    SnapshotOut,
    StatusHistoryOut,
)

router = APIRouter(tags=["missions"])
MissionStatus = Literal["draft", "running", "paused", "completed", "stopped", "failed"]


@router.post("/missions", response_model=MissionOut, status_code=status.HTTP_201_CREATED)
def create_mission(
    body: MissionCreate, principal: PrincipalDep, services: ContainerDep
) -> MissionOut:
    return services.missions.create(principal, body)


@router.get("/missions", response_model=Page[MissionOut])
def list_missions(
    principal: PrincipalDep,
    services: ContainerDep,
    page: PageDep,
    status_filter: Annotated[MissionStatus | None, Query(alias="status")] = None,
) -> Page[MissionOut]:
    items, total = services.missions.list_missions(
        principal, status_filter, page.limit, page.offset
    )
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/missions/{mission_id}", response_model=MissionOut)
def get_mission(mission_id: UUID, principal: PrincipalDep, services: ContainerDep) -> MissionOut:
    return services.missions.get(principal, mission_id)


@router.patch("/missions/{mission_id}", response_model=MissionOut)
def patch_mission(
    mission_id: UUID, body: MissionPatch, principal: PrincipalDep, services: ContainerDep
) -> MissionOut:
    return services.missions.patch(principal, mission_id, body)


async def _control(
    services: ContainerDep, principal: Any, mission_id: UUID, action: str, reason: str
) -> MissionOut:
    import asyncio

    await asyncio.to_thread(services.missions.authorize_control, principal, mission_id)
    runtime = services.runtime
    try:
        if action == "start":
            await runtime.start(mission_id, principal.subject)
        elif action == "pause":
            await runtime.pause(mission_id, principal.subject, reason)
        elif action == "resume":
            await runtime.resume(mission_id, principal.subject, reason)
        else:
            await runtime.stop(mission_id, principal.subject, reason)
    except AppError:
        await asyncio.to_thread(
            services.missions.audit_control, principal, mission_id, action, reason, "failure"
        )
        raise
    await asyncio.to_thread(services.missions.audit_control, principal, mission_id, action, reason)
    return await asyncio.to_thread(services.missions.get, principal, mission_id)


@router.post("/missions/{mission_id}/start", response_model=MissionOut)
async def start_mission(
    mission_id: UUID,
    principal: PrincipalDep,
    services: ContainerDep,
    body: LifecycleRequest | None = None,
) -> MissionOut:
    return await _control(
        services, principal, mission_id, "start", body.reason if body else "start"
    )


@router.post("/missions/{mission_id}/pause", response_model=MissionOut)
async def pause_mission(
    mission_id: UUID,
    principal: PrincipalDep,
    services: ContainerDep,
    body: LifecycleRequest | None = None,
) -> MissionOut:
    return await _control(
        services, principal, mission_id, "pause", body.reason if body else "pause"
    )


@router.post("/missions/{mission_id}/resume", response_model=MissionOut)
async def resume_mission(
    mission_id: UUID,
    principal: PrincipalDep,
    services: ContainerDep,
    body: LifecycleRequest | None = None,
) -> MissionOut:
    return await _control(
        services, principal, mission_id, "resume", body.reason if body else "resume"
    )


@router.post("/missions/{mission_id}/stop", response_model=MissionOut)
async def stop_mission(
    mission_id: UUID,
    principal: PrincipalDep,
    services: ContainerDep,
    body: LifecycleRequest | None = None,
) -> MissionOut:
    return await _control(services, principal, mission_id, "stop", body.reason if body else "stop")


@router.get("/missions/{mission_id}/summary", response_model=MissionSummary)
def mission_summary(
    mission_id: UUID, principal: PrincipalDep, services: ContainerDep
) -> MissionSummary:
    return services.missions.summary(principal, mission_id)


@router.get("/missions/{mission_id}/history", response_model=list[StatusHistoryOut])
def mission_history(
    mission_id: UUID, principal: PrincipalDep, services: ContainerDep
) -> list[StatusHistoryOut]:
    return services.missions.history(principal, mission_id)


@router.get("/missions/{mission_id}/metrics")
def mission_metrics(
    mission_id: UUID, principal: PrincipalDep, services: ContainerDep
) -> dict[str, object]:
    return services.missions.metrics(principal, mission_id)


@router.post(
    "/missions/{mission_id}/members",
    response_model=MembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_member(
    mission_id: UUID, body: MembershipCreate, principal: PrincipalDep, services: ContainerDep
) -> MembershipResponse:
    membership = services.missions.add_member(principal, mission_id, body.user_id, body.role)
    return MembershipResponse.model_validate(membership)


@router.post(
    "/missions/{mission_id}/agent-credentials",
    response_model=AgentCredentialOut,
    status_code=status.HTTP_201_CREATED,
)
def create_agent_credential(
    mission_id: UUID, body: AgentCredentialCreate, principal: PrincipalDep, services: ContainerDep
) -> AgentCredentialOut:
    return services.missions.create_agent_credential(principal, mission_id, body.agent_key)


@router.get("/missions/{mission_id}/events", response_model=list[EventOut], tags=["events"])
def mission_events(
    mission_id: UUID,
    principal: PrincipalDep,
    services: ContainerDep,
    after_sequence: Annotated[int, Query(ge=0)] = 0,
    event_type: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[EventOut]:
    """Replay and resynchronization feed: events strictly after `after_sequence`."""
    return services.queries.events(principal, mission_id, after_sequence, event_type, limit)


@router.get("/missions/{mission_id}/audit", response_model=Page[AuditOut], tags=["audit"])
def mission_audit(
    mission_id: UUID,
    principal: PrincipalDep,
    services: ContainerDep,
    page: PageDep,
    action: str | None = None,
) -> Page[AuditOut]:
    items, total = services.queries.audit(principal, mission_id, action, page.limit, page.offset)
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/audit", response_model=Page[AuditOut], tags=["audit"])
def system_audit(
    principal: PrincipalDep, services: ContainerDep, page: PageDep, action: str | None = None
) -> Page[AuditOut]:
    items, total = services.queries.audit(principal, None, action, page.limit, page.offset)
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/missions/{mission_id}/exports/{kind}", tags=["exports"])
def export_mission(
    mission_id: UUID,
    kind: Literal["operational", "research"],
    principal: PrincipalDep,
    services: ContainerDep,
    format: Literal["json", "csv"] = "json",
) -> Response:
    record = services.exports.build(principal, mission_id, kind)
    if format == "csv":
        return PlainTextResponse(
            services.exports.to_csv(record),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="mission-{mission_id}-{kind}.csv"'
            },
        )
    import json

    return Response(json.dumps(record, default=str), media_type="application/json")


@router.get("/missions/{mission_id}/snapshots", response_model=list[SnapshotOut], tags=["model2"])
def snapshots(
    mission_id: UUID, principal: PrincipalDep, services: ContainerDep
) -> list[SnapshotOut]:
    from sqlalchemy import select
    from sqlalchemy.orm import defer

    from backend.core.permissions import Permission
    from backend.database import models as m
    from backend.services.access import mission_for

    with services.db.read() as session:
        mission_for(session, principal, mission_id, Permission.METRICS_READ)
        rows = session.scalars(
            select(m.MissionSnapshot)
            # The listing returns metadata only; payloads can be megabytes each.
            .options(defer(m.MissionSnapshot.payload, raiseload=True))
            .where(m.MissionSnapshot.mission_id == mission_id)
            .order_by(m.MissionSnapshot.sim_time_ms.desc(), m.MissionSnapshot.created_at.desc())
            .limit(50)
        )
        return [SnapshotOut.model_validate(r) for r in rows]


@router.post(
    "/missions/{mission_id}/model2/recovery", response_model=RecoveryReport, tags=["model2"]
)
def verify_recovery(
    mission_id: UUID, principal: PrincipalDep, services: ContainerDep
) -> RecoveryReport:
    """Restore Model 2 memory from the latest checkpoint and compare it to the stored read model.
    Read-only: the restored instance is not attached to any simulation."""
    from sqlalchemy import select

    from backend.core.permissions import Permission
    from backend.database import models as m
    from backend.persistence.memory_adapter import SqlSnapshotRepository, normalized, restore_model2
    from backend.services import audit
    from backend.services.access import mission_for

    with services.db.read() as session:
        mission = mission_for(session, principal, mission_id, Permission.MISSION_CONTROL)
        sim_mission_id = mission.sim_mission_id
    result = restore_model2(SqlSnapshotRepository(services.db), mission_id, sim_mission_id)
    matches: bool | None = None
    if result.agent is not None and result.snapshot is not None:
        with services.db.read() as session:
            read_model = session.scalar(
                select(m.MissionSnapshot).where(
                    m.MissionSnapshot.mission_id == mission_id,
                    m.MissionSnapshot.kind == "model2_read_model",
                    m.MissionSnapshot.run_id
                    == select(m.MissionSnapshot.run_id)
                    .where(m.MissionSnapshot.id == result.snapshot.snapshot_id)
                    .scalar_subquery(),
                    m.MissionSnapshot.sim_time_ms == result.snapshot.sim_time_ms,
                )
            )
        if read_model is not None:
            matches = normalized(result.agent.snapshot()) == read_model.payload
    with services.db.transaction() as session:
        audit.record(
            session,
            principal,
            "model2.recovery",
            resource_type="mission",
            resource_id=mission_id,
            mission_id=mission_id,
            outcome="success" if result.agent is not None else "failure",
            details={"detail": result.detail, "matches_read_model": matches},
        )
    return RecoveryReport(
        mission_id=mission_id,
        snapshot_id=result.snapshot.snapshot_id if result.snapshot else None,
        sim_time_ms=result.snapshot.sim_time_ms if result.snapshot else None,
        integrity_ok=result.integrity_ok,
        restored=result.agent is not None,
        restored_incidents=len(result.agent.incidents) if result.agent else 0,
        matches_persisted_read_model=matches,
        detail=result.detail,
    )
