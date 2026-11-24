"""Request and response schemas. Requests forbid unknown fields to block mass assignment."""

from datetime import datetime
from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from backend.core.permissions import GlobalRole, MissionRole
from backend.integrations.simulation_adapter import MissionConfig

T = TypeVar("T")
Reason = Annotated[str, StringConstraints(min_length=1, max_length=100, pattern=r"\S")]
IdempotencyKey = Annotated[
    str, StringConstraints(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")
]


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Response(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str
    details: Any = None


class ErrorResponse(BaseModel):
    error: ErrorBody


# ----- locations ---------------------------------------------------------------------------
class Location(BaseModel):
    """A reported location with its coordinate reference system.

    crs "swarm-aid:grid" means local simulator grid cells (unit: cell). These are not
    geographic coordinates. "EPSG:4326" is accepted only for valid longitude/latitude.
    """

    crs: str
    x: float
    y: float
    units: str
    uncertainty: float | None = None
    map_ref: str | None = None

    @model_validator(mode="after")
    def check_geographic(self) -> "Location":
        if self.crs == "EPSG:4326" and not (-180 <= self.x <= 180 and -90 <= self.y <= 90):
            raise ValueError("EPSG:4326 requires longitude in [-180,180] and latitude in [-90,90]")
        if self.uncertainty is not None and self.uncertainty < 0:
            raise ValueError("uncertainty must be non-negative")
        return self


def location(row: Any, map_ref: str | None = None) -> Location | None:
    if getattr(row, "x", None) is None or getattr(row, "y", None) is None or row.crs is None:
        return None
    units = "cell" if row.crs == "swarm-aid:grid" else "degree"
    return Location(
        crs=row.crs, x=row.x, y=row.y, units=units, uncertainty=row.uncertainty, map_ref=map_ref
    )


# ----- auth --------------------------------------------------------------------------------
class LoginRequest(Request):
    username: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=256)]


class RefreshRequest(Request):
    refresh_token: Annotated[str, StringConstraints(min_length=1, max_length=4096)]


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    access_expires_at: datetime
    refresh_expires_at: datetime


class MachineTokenRequest(Request):
    credential_id: UUID
    secret: Annotated[str, StringConstraints(min_length=1, max_length=256)]


class MachineTokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime


class MembershipOut(BaseModel):
    mission_id: UUID
    role: MissionRole


class MeResponse(BaseModel):
    subject: str
    kind: str
    user_id: UUID | None
    global_role: GlobalRole | None
    memberships: list[MembershipOut]
    machine_mission: UUID | None


class UserCreate(Request):
    username: Annotated[str, StringConstraints(min_length=3, max_length=64)]
    password: Annotated[str, StringConstraints(min_length=12, max_length=256)]
    global_role: GlobalRole
    display_name: Annotated[str, StringConstraints(max_length=128)] | None = None


class UserOut(Response):
    id: UUID
    username: str
    display_name: str
    global_role: str
    is_active: bool
    created_at: datetime


class MembershipCreate(Request):
    user_id: UUID
    role: MissionRole


class MembershipResponse(Response):
    id: UUID
    mission_id: UUID
    user_id: UUID
    role: str
    granted_by: str
    created_at: datetime


class AgentCredentialCreate(Request):
    agent_key: Annotated[
        str, StringConstraints(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    ]


class AgentCredentialOut(BaseModel):
    credential_id: UUID
    agent_key: str
    mission_id: UUID
    secret: str = Field(description="Shown once. Store it securely; it cannot be retrieved.")


# ----- missions ----------------------------------------------------------------------------
class MissionCreate(Request):
    name: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    description: Annotated[str, StringConstraints(max_length=2000)] = ""
    config: MissionConfig


class MissionPatch(Request):
    """Only descriptive fields. Status changes use the lifecycle endpoints."""

    version: int = Field(ge=1, description="Expected current version (optimistic concurrency)")
    name: Annotated[str, StringConstraints(min_length=1, max_length=128)] | None = None
    description: Annotated[str, StringConstraints(max_length=2000)] | None = None


class LifecycleRequest(Request):
    reason: Reason = "operator request"


class MissionOut(Response):
    id: UUID
    name: str
    description: str
    scenario_id: str
    sim_mission_id: UUID
    config: dict[str, Any]
    status: str
    version: int
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    last_sim_ms: int = 0
    model2_state: str = "inactive"
    communication_state: str = "unknown"
    last_event_sequence: int = 0
    current_run_id: UUID | None = None


class StatusHistoryOut(Response):
    previous: str
    status: str
    actor: str
    reason: str
    sim_time_ms: int | None
    created_at: datetime


class MissionSummary(BaseModel):
    mission: MissionOut
    agents: int
    agents_connected: int
    observations: int
    incidents_by_disposition: dict[str, int]
    pending_recommendations: int
    open_alerts: int
    hazards: int
    tasks_by_state: dict[str, int]


# ----- agents ------------------------------------------------------------------------------
class AgentOut(BaseModel):
    id: UUID
    mission_id: UUID
    agent_key: str
    kind: str
    availability: str = Field(
        description="Coordinator-known: unknown, available, unavailable, stale"
    )
    reported_state: str | None
    communication: str
    battery_fraction: float | None
    degraded_sensors: list[str]
    last_report_ms: int | None
    location: Location | None
    last_location_ms: int | None


class AgentReportOut(BaseModel):
    report_type: str
    sim_time_ms: int
    state: str | None
    battery_fraction: float | None
    location: Location | None
    details: dict[str, Any]


class AgentHealthIn(Request):
    battery_fraction: float = Field(ge=0, le=1)
    degraded_sensors: list[Annotated[str, StringConstraints(min_length=1, max_length=50)]] = Field(
        default_factory=list, max_length=20
    )
    cell: tuple[int, int] | None = None


# ----- observations and evidence -----------------------------------------------------------
class EvidenceIn(Request):
    evidence_id: UUID
    captured_ms: int = Field(ge=0)
    modality: Literal["image", "video", "thermal", "text", "gps", "imu", "environment", "peer"]
    artifact_key: Annotated[
        str, StringConstraints(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._:/-]+$")
    ]


class ObservationIn(Request):
    """Agent report. Incident classification is deliberately absent: Model 2 assesses."""

    observation_id: UUID
    kind: Literal["environment", "hazard", "possible_human"]
    label: Annotated[str, StringConstraints(min_length=1, max_length=100)] | None = None
    observed_ms: int = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    cell: tuple[int, int] | None = None
    evidence: list[EvidenceIn] = Field(min_length=1, max_length=20)


class ObservationIngestResult(BaseModel):
    observation_id: UUID
    message_id: UUID
    outcome: str
    duplicate: bool


class EvidenceOut(BaseModel):
    evidence_id: UUID
    origin: str
    captured_ms: int
    modality: str
    artifact_key: str
    object_id: UUID | None


class ObservationOut(BaseModel):
    id: UUID
    mission_id: UUID
    observation_id: UUID
    message_id: UUID
    reporter: str
    kind: str
    label: str | None
    confidence: float
    observed_ms: int
    received_ms: int
    age_ms: int
    stale: bool
    outcome: str
    source: str
    location: Location | None


class EvidenceGroupOut(BaseModel):
    """A Model 2 fusion group. Each incident is one evidence group."""

    evidence_group_id: UUID
    incident_id: UUID
    observations: list[ObservationOut]
    distinct_reporters: list[str]


class EvidenceObjectOut(Response):
    id: UUID
    mission_id: UUID
    sha256: str
    media_type: str
    size_bytes: int
    source_subject: str
    created_at: datetime


# ----- incidents and recommendations -------------------------------------------------------
class IncidentOut(BaseModel):
    id: UUID
    mission_id: UUID
    revision: int
    category: str
    disposition: str
    priority_level: str | None
    priority_reason: str | None
    operator_priority: str | None
    location: Location | None
    opened_sim_ms: int
    updated_sim_ms: int
    freshness_ms: int
    current_recommendation_id: UUID | None
    supporting_observations: int
    conflicting_observations: int


class IncidentRevisionOut(Response):
    revision: int
    category: str
    report_message_ids: list[str]
    uncertainties: list[str]
    confirmation_id: UUID | None
    priority_level: str | None
    priority_reason: str | None
    sim_time_ms: int
    created_at: datetime


class IncidentTransitionOut(Response):
    revision: int
    previous: str
    state: str
    actor: str
    reference: UUID
    sim_time_ms: int
    created_at: datetime


class RecommendationOut(Response):
    id: UUID
    mission_id: UUID
    incident_id: UUID
    version: int = Field(validation_alias="incident_revision")
    request: str
    evidence_ids: list[str]
    unknowns: list[str]
    expires_ms: int
    status: str
    created_sim_ms: int
    created_at: datetime


class RecommendationStatusOut(Response):
    previous: str
    status: str
    reason: str
    sim_time_ms: int
    created_at: datetime


class DecisionRequest(Request):
    version: int = Field(ge=1, description="Recommendation version (incident revision) shown")
    reason: Reason
    idempotency_key: IdempotencyKey | None = None


class ApproveRequest(DecisionRequest):
    confirm_rescue_need: bool = Field(
        default=False,
        description="Record a human-confirmed rescue need (requires a sighting, not a hazard).",
    )


class IncidentActionRequest(Request):
    revision: int = Field(ge=1, description="Incident revision shown to the operator")
    reason: Reason
    idempotency_key: IdempotencyKey | None = None


class FeedbackRequest(IncidentActionRequest):
    incident_id: UUID
    action: Literal["correct", "prioritize"]


class OverrideRequest(Request):
    action: Literal["pause", "resume", "end"]
    reason: Reason
    idempotency_key: IdempotencyKey | None = None


class AlertAckRequest(Request):
    reason: Reason = "seen"


class DecisionOut(Response):
    id: UUID
    mission_id: UUID
    kind: str
    action: str
    incident_id: UUID | None
    recommendation_id: UUID | None
    expected_revision: int | None
    actor_user_id: UUID
    actor_role: str
    reason: str
    message_id: UUID | None
    status: str
    outcome_reason: str | None
    sim_time_ms: int | None
    submitted_at: datetime
    resolved_at: datetime | None


class AlertOut(Response):
    id: UUID
    incident_id: UUID
    incident_revision: int
    priority: str
    priority_reason: str
    review_state: str
    supporting_evidence: list[str]
    sent_sim_ms: int
    acknowledged_at: datetime | None
    acknowledged_by: UUID | None


class ReviewItem(BaseModel):
    incident: IncidentOut
    recommendation: RecommendationOut
    remaining_ms: int


# ----- coordination, environment, map ------------------------------------------------------
class TaskOut(BaseModel):
    id: UUID
    member: str
    target: Location
    category: str
    coordinator_state: str
    reported_status: str | None
    reported_ms: int | None
    knowledge: Literal["coordinator_known", "reported", "conflicting", "stale", "unknown"]
    created_ms: int
    expires_ms: int
    updated_ms: int


class TaskEventOut(Response):
    sim_time_ms: int
    state: str
    reason: str
    source: str


class HazardOut(BaseModel):
    id: UUID
    label: str
    location: Location | None
    first_reported_ms: int
    last_reported_ms: int
    report_count: int
    reporters: list[str]
    stale: bool


class SectorOut(BaseModel):
    member: str
    cells: list[tuple[int, int]]


class MapFeature(BaseModel):
    id: str
    layer: str
    location: Location | None
    properties: dict[str, Any]


class MapLayer(BaseModel):
    name: str
    description: str
    features: list[MapFeature]


class MapResponse(BaseModel):
    """Simulation map in local grid coordinates. Not geographic; GeoJSON is not used."""

    crs: str
    units: str
    width: int
    height: int
    map_ref: str
    sim_time_ms: int
    layers: list[MapLayer]


class EventOut(Response):
    id: UUID
    mission_id: UUID
    sequence: int
    event_type: str
    schema_version: str
    source: str
    occurred_at: datetime
    sim_time_ms: int | None
    correlation_id: str
    resource_type: str
    resource_id: str
    payload: dict[str, Any]


class AuditOut(Response):
    id: UUID
    occurred_at: datetime
    actor: str
    actor_type: str
    action: str
    resource_type: str
    resource_id: str | None
    mission_id: UUID | None
    request_id: str
    outcome: str
    details: dict[str, Any]


class SnapshotOut(Response):
    id: UUID
    kind: str
    schema_version: str
    sim_time_ms: int
    sha256: str
    complete: bool
    created_at: datetime


class RecoveryReport(BaseModel):
    mission_id: UUID
    snapshot_id: UUID | None
    sim_time_ms: int | None
    integrity_ok: bool
    restored: bool
    restored_incidents: int
    matches_persisted_read_model: bool | None
    detail: str


class TraceIncidentOut(BaseModel):
    """An incident that this observation supports or contradicts."""

    incident: IncidentOut
    role: str
    first_revision: int
    revisions_citing_report: list[int]


class ObservationTraceOut(BaseModel):
    """Processing history of one reported observation, for research diagnostics.

    Persisted, authorized records only: the report as received, its evidence references, the
    Model 2 incidents and recommendation versions it fed, the human decisions on those
    recommendations and the mission events about any of them. Private agent memory, Model 2
    internals and evaluator ground truth are never included.
    """

    observation: ObservationOut
    evidence: list[EvidenceOut]
    incidents: list[TraceIncidentOut]
    recommendations: list[RecommendationOut]
    decisions: list[DecisionOut]
    events: list[EventOut]
    events_truncated: bool
