"""Scenario and experiment catalogs (Phase 8 dashboard support). Read-only."""

import asyncio

from fastapi import APIRouter

from backend.api.dependencies import ContainerDep, PrincipalDep
from backend.core.errors import Forbidden, NotFound
from backend.core.permissions import GlobalRole
from backend.services.catalog import (
    ExperimentCatalog,
    ExperimentDetail,
    ExperimentInfo,
    ScenarioInfo,
    scenario_catalog,
)

router = APIRouter()
RESEARCH_ROLES = {GlobalRole.ADMINISTRATOR, GlobalRole.RESEARCHER}


@router.get("/scenarios", response_model=list[ScenarioInfo], tags=["catalog"])
async def scenarios(principal: PrincipalDep) -> list[ScenarioInfo]:
    """Scenario fixtures a mission may use. Configuration only; no simulator ground truth."""
    principal.require_human()
    return await asyncio.to_thread(scenario_catalog)


def _research(principal: PrincipalDep) -> None:
    principal.require_human()
    if principal.global_role not in RESEARCH_ROLES:
        raise Forbidden("researcher or administrator role required")


@router.get("/experiments", response_model=list[ExperimentInfo], tags=["catalog"])
async def experiments(principal: PrincipalDep, services: ContainerDep) -> list[ExperimentInfo]:
    """Stored Phase 5 and Phase 6 experiment comparisons (evaluator-measured)."""
    _research(principal)
    return await asyncio.to_thread(ExperimentCatalog(services.settings.experiments_dir).list)


@router.get("/experiments/{experiment_id}", response_model=ExperimentDetail, tags=["catalog"])
async def experiment(
    experiment_id: str, principal: PrincipalDep, services: ContainerDep
) -> ExperimentDetail:
    _research(principal)
    found = await asyncio.to_thread(
        ExperimentCatalog(services.settings.experiments_dir).get, experiment_id
    )
    if found is None:
        raise NotFound("experiment not found")
    return found
