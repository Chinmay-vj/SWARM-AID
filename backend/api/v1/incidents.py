"""Incidents, recommendations and human oversight.

Decision endpoints return 202: the decision is durably recorded and forwarded to Model 2,
whose validator accepts or rejects it. Poll GET /missions/{id}/human-decisions or subscribe to
the "review" WebSocket topic for the outcome.
"""

import asyncio
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, status

from backend.api.dependencies import ContainerDep, PageDep, PrincipalDep
from backend.schemas import (
    AlertAckRequest,
    AlertOut,
    ApproveRequest,
    DecisionOut,
    DecisionRequest,
    EvidenceGroupOut,
    EvidenceOut,
    FeedbackRequest,
    IncidentActionRequest,
    IncidentOut,
    IncidentRevisionOut,
    IncidentTransitionOut,
    OverrideRequest,
    Page,
    RecommendationOut,
    RecommendationStatusOut,
    ReviewItem,
)

router = APIRouter()
Accepted = status.HTTP_202_ACCEPTED


# ----- incidents ---------------------------------------------------------------------------
@router.get(
    "/missions/{mission_id}/incidents", response_model=Page[IncidentOut], tags=["incidents"]
)
def list_incidents(
    mission_id: UUID,
    principal: PrincipalDep,
    services: ContainerDep,
    page: PageDep,
    disposition: Annotated[str | None, Query(max_length=32)] = None,
    category: Annotated[str | None, Query(max_length=32)] = None,
    priority: Literal["review_required", "elevated", "potentially_urgent"] | None = None,
) -> Page[IncidentOut]:
    items, total = services.queries.incidents(
        principal, mission_id, disposition, category, priority, page.limit, page.offset
    )
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/incidents/{incident_id}", response_model=IncidentOut, tags=["incidents"])
def get_incident(incident_id: UUID, principal: PrincipalDep, services: ContainerDep) -> IncidentOut:
    return services.queries.incident(principal, incident_id)


@router.get(
    "/incidents/{incident_id}/evidence", response_model=EvidenceGroupOut, tags=["incidents"]
)
def incident_evidence(
    incident_id: UUID, principal: PrincipalDep, services: ContainerDep
) -> EvidenceGroupOut:
    return services.queries.evidence_group(principal, incident_id)


@router.get(
    "/incidents/{incident_id}/history",
    response_model=list[IncidentTransitionOut],
    tags=["incidents"],
)
def incident_history(
    incident_id: UUID, principal: PrincipalDep, services: ContainerDep
) -> list[IncidentTransitionOut]:
    return services.queries.incident_history(principal, incident_id)


@router.get(
    "/incidents/{incident_id}/assessments",
    response_model=list[IncidentRevisionOut],
    tags=["incidents"],
)
def incident_assessments(
    incident_id: UUID, principal: PrincipalDep, services: ContainerDep
) -> list[IncidentRevisionOut]:
    return services.queries.incident_revisions(principal, incident_id)


@router.post(
    "/incidents/{incident_id}/acknowledge",
    response_model=DecisionOut,
    status_code=Accepted,
    tags=["oversight"],
)
async def acknowledge_incident(
    incident_id: UUID, body: IncidentActionRequest, principal: PrincipalDep, services: ContainerDep
) -> DecisionOut:
    """Acknowledge the pending review (Model 2 'approve_review' on the current recommendation)."""
    return await asyncio.to_thread(
        services.oversight.acknowledge_incident,
        principal,
        incident_id,
        body.revision,
        body.reason,
        body.idempotency_key,
    )


@router.post(
    "/incidents/{incident_id}/request-review",
    response_model=DecisionOut,
    status_code=Accepted,
    tags=["oversight"],
)
async def request_review(
    incident_id: UUID, body: IncidentActionRequest, principal: PrincipalDep, services: ContainerDep
) -> DecisionOut:
    """Flag the incident for priority human review (Model 2 'prioritize')."""
    return await asyncio.to_thread(
        services.oversight.incident_review,
        principal,
        incident_id,
        "prioritize",
        body.revision,
        body.reason,
        body.idempotency_key,
    )


@router.post(
    "/incidents/{incident_id}/resolution-report",
    response_model=DecisionOut,
    status_code=Accepted,
    tags=["oversight"],
)
async def resolution_report(
    incident_id: UUID, body: IncidentActionRequest, principal: PrincipalDep, services: ContainerDep
) -> DecisionOut:
    """Human report that the incident was resolved. Not a claim of physical rescue."""
    return await asyncio.to_thread(
        services.oversight.incident_review,
        principal,
        incident_id,
        "resolve",
        body.revision,
        body.reason,
        body.idempotency_key,
    )


@router.post(
    "/incidents/{incident_id}/close",
    response_model=DecisionOut,
    status_code=Accepted,
    tags=["oversight"],
)
async def close_incident(
    incident_id: UUID, body: IncidentActionRequest, principal: PrincipalDep, services: ContainerDep
) -> DecisionOut:
    """Close after a resolution report. Coordinator only."""
    return await asyncio.to_thread(
        services.oversight.incident_review,
        principal,
        incident_id,
        "close",
        body.revision,
        body.reason,
        body.idempotency_key,
    )


# ----- recommendations ---------------------------------------------------------------------
@router.get(
    "/missions/{mission_id}/recommendations",
    response_model=Page[RecommendationOut],
    tags=["recommendations"],
)
def list_recommendations(
    mission_id: UUID,
    principal: PrincipalDep,
    services: ContainerDep,
    page: PageDep,
    status_filter: Annotated[str | None, Query(alias="status", max_length=32)] = None,
) -> Page[RecommendationOut]:
    items, total = services.queries.recommendations(
        principal, mission_id, status_filter, page.limit, page.offset
    )
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/recommendations/{rec_id}", response_model=RecommendationOut, tags=["recommendations"])
def get_recommendation(
    rec_id: UUID, principal: PrincipalDep, services: ContainerDep
) -> RecommendationOut:
    return services.queries.recommendation(principal, rec_id)


@router.get(
    "/recommendations/{rec_id}/versions",
    response_model=list[RecommendationOut],
    tags=["recommendations"],
)
def recommendation_versions(
    rec_id: UUID, principal: PrincipalDep, services: ContainerDep
) -> list[RecommendationOut]:
    return services.queries.recommendation_versions(principal, rec_id)


@router.get(
    "/recommendations/{rec_id}/history",
    response_model=list[RecommendationStatusOut],
    tags=["recommendations"],
)
def recommendation_history(
    rec_id: UUID, principal: PrincipalDep, services: ContainerDep
) -> list[RecommendationStatusOut]:
    return services.queries.recommendation_history(principal, rec_id)


@router.get(
    "/recommendations/{rec_id}/evidence", response_model=list[EvidenceOut], tags=["recommendations"]
)
def recommendation_evidence(
    rec_id: UUID, principal: PrincipalDep, services: ContainerDep
) -> list[EvidenceOut]:
    return services.queries.recommendation_evidence(principal, rec_id)


@router.post(
    "/recommendations/{rec_id}/approve",
    response_model=DecisionOut,
    status_code=Accepted,
    tags=["oversight"],
)
async def approve(
    rec_id: UUID, body: ApproveRequest, principal: PrincipalDep, services: ContainerDep
) -> DecisionOut:
    decision: Literal["approve_review", "confirm_rescue_need"] = (
        "confirm_rescue_need" if body.confirm_rescue_need else "approve_review"
    )
    return await asyncio.to_thread(
        services.oversight.decide,
        principal,
        rec_id,
        decision,
        body.version,
        body.reason,
        body.idempotency_key,
    )


@router.post(
    "/recommendations/{rec_id}/reject",
    response_model=DecisionOut,
    status_code=Accepted,
    tags=["oversight"],
)
async def reject(
    rec_id: UUID, body: DecisionRequest, principal: PrincipalDep, services: ContainerDep
) -> DecisionOut:
    return await asyncio.to_thread(
        services.oversight.decide,
        principal,
        rec_id,
        "reject",
        body.version,
        body.reason,
        body.idempotency_key,
    )


@router.post(
    "/recommendations/{rec_id}/request-revision",
    response_model=DecisionOut,
    status_code=Accepted,
    tags=["oversight"],
)
async def request_revision(
    rec_id: UUID, body: DecisionRequest, principal: PrincipalDep, services: ContainerDep
) -> DecisionOut:
    """Human correction: Model 2 revises the incident and withdraws this recommendation."""
    return await asyncio.to_thread(
        services.oversight.request_revision,
        principal,
        rec_id,
        body.version,
        body.reason,
        body.idempotency_key,
    )


# ----- human oversight ---------------------------------------------------------------------
@router.get(
    "/missions/{mission_id}/review-queue", response_model=list[ReviewItem], tags=["oversight"]
)
def review_queue(
    mission_id: UUID, principal: PrincipalDep, services: ContainerDep
) -> list[ReviewItem]:
    return services.queries.review_queue(principal, mission_id)


@router.get("/missions/{mission_id}/alerts", response_model=Page[AlertOut], tags=["oversight"])
def alerts(
    mission_id: UUID,
    principal: PrincipalDep,
    services: ContainerDep,
    page: PageDep,
    unacknowledged: bool = False,
) -> Page[AlertOut]:
    items, total = services.queries.alerts(
        principal, mission_id, unacknowledged, page.limit, page.offset
    )
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertOut, tags=["oversight"])
def acknowledge_alert(
    alert_id: UUID,
    principal: PrincipalDep,
    services: ContainerDep,
    body: AlertAckRequest | None = None,
) -> AlertOut:
    return services.oversight.acknowledge_alert(
        principal, alert_id, body.reason if body else "seen"
    )


@router.get(
    "/missions/{mission_id}/human-decisions", response_model=Page[DecisionOut], tags=["oversight"]
)
def human_decisions(
    mission_id: UUID, principal: PrincipalDep, services: ContainerDep, page: PageDep
) -> Page[DecisionOut]:
    items, total = services.queries.decisions(principal, mission_id, page.limit, page.offset)
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "/missions/{mission_id}/human-feedback",
    response_model=DecisionOut,
    status_code=Accepted,
    tags=["oversight"],
)
async def human_feedback(
    mission_id: UUID, body: FeedbackRequest, principal: PrincipalDep, services: ContainerDep
) -> DecisionOut:
    """Human correction or prioritization of an incident in this mission."""
    return await asyncio.to_thread(
        services.oversight.incident_review,
        principal,
        body.incident_id,
        body.action,
        body.revision,
        body.reason,
        body.idempotency_key,
        mission_id=mission_id,
    )


@router.post(
    "/missions/{mission_id}/override",
    response_model=DecisionOut,
    status_code=Accepted,
    tags=["oversight"],
)
async def override(
    mission_id: UUID, body: OverrideRequest, principal: PrincipalDep, services: ContainerDep
) -> DecisionOut:
    """Revision-bound simulated assignment override (pause, resume or end) sent to Model 2.
    There is no physical drone control."""
    return await asyncio.to_thread(
        services.oversight.override,
        principal,
        mission_id,
        body.action,
        body.reason,
        body.idempotency_key,
    )
