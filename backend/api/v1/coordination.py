"""Coordination, environment and map read models (Phase 5 coordination, Model 2 world model)."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter

from backend.api.dependencies import ContainerDep, PageDep, PrincipalDep
from backend.schemas import HazardOut, MapResponse, Page, SectorOut, TaskEventOut, TaskOut

router = APIRouter()
LAYERS = {"agents", "incidents", "hazards", "stale_observations", "sectors", "coverage"}


@router.get("/missions/{mission_id}/tasks", response_model=Page[TaskOut], tags=["coordination"])
def tasks(
    mission_id: UUID,
    principal: PrincipalDep,
    services: ContainerDep,
    page: PageDep,
    member: str | None = None,
    state: str | None = None,
) -> Page[TaskOut]:
    items, total = services.queries.tasks(
        principal, mission_id, member, state, page.limit, page.offset
    )
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/tasks/{task_id}", response_model=TaskOut, tags=["coordination"])
def task(task_id: UUID, principal: PrincipalDep, services: ContainerDep) -> TaskOut:
    return services.queries.task(principal, task_id)


@router.get("/tasks/{task_id}/history", response_model=list[TaskEventOut], tags=["coordination"])
def task_history(
    task_id: UUID, principal: PrincipalDep, services: ContainerDep
) -> list[TaskEventOut]:
    return services.queries.task_history(principal, task_id)


@router.get("/missions/{mission_id}/sectors", response_model=list[SectorOut], tags=["coordination"])
def sectors(mission_id: UUID, principal: PrincipalDep, services: ContainerDep) -> list[SectorOut]:
    return services.queries.sectors(principal, mission_id)


@router.get("/missions/{mission_id}/coverage", tags=["coordination"])
def coverage(mission_id: UUID, principal: PrincipalDep, services: ContainerDep) -> dict[str, Any]:
    return services.queries.coverage(principal, mission_id)


@router.get("/missions/{mission_id}/coordination-conflicts", tags=["coordination"])
def coordination_conflicts(
    mission_id: UUID, principal: PrincipalDep, services: ContainerDep
) -> list[dict[str, Any]]:
    return services.queries.coordination_conflicts(principal, mission_id)


@router.get("/missions/{mission_id}/environment", tags=["environment"])
def environment(
    mission_id: UUID, principal: PrincipalDep, services: ContainerDep
) -> dict[str, Any]:
    return services.queries.environment(principal, mission_id)


@router.get("/missions/{mission_id}/hazards", response_model=list[HazardOut], tags=["environment"])
def hazards(mission_id: UUID, principal: PrincipalDep, services: ContainerDep) -> list[HazardOut]:
    return services.queries.hazards(principal, mission_id)


@router.get("/hazards/{hazard_id}", response_model=HazardOut, tags=["environment"])
def hazard(hazard_id: UUID, principal: PrincipalDep, services: ContainerDep) -> HazardOut:
    return services.queries.hazard(principal, hazard_id)


@router.get("/missions/{mission_id}/map", response_model=MapResponse, tags=["map"])
def mission_map(
    mission_id: UUID, principal: PrincipalDep, services: ContainerDep, layers: str | None = None
) -> MapResponse:
    wanted = {name.strip() for name in layers.split(",")} & LAYERS if layers else None
    return services.queries.map(principal, mission_id, wanted)


@router.get("/missions/{mission_id}/map/layers", tags=["map"])
def map_layers(
    mission_id: UUID, principal: PrincipalDep, services: ContainerDep
) -> list[dict[str, Any]]:
    result = services.queries.map(principal, mission_id)
    return [
        {"name": layer.name, "description": layer.description, "features": len(layer.features)}
        for layer in result.layers
    ]
