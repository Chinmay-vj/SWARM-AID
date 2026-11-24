"""Typed ORM models. ORM objects never leave the service layer; APIs return schemas.

Isolation: every mission-owned table carries mission_id. Links between mission-owned rows use
composite foreign keys on (mission_id, id) so a row cannot reference another mission's data.
Evidence, decisions and audit rows have no delete cascades.
"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base, JSONType, utcnow

LOCAL_CRS = "swarm-aid:grid"


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


MISSION_STATUSES = ("draft", "running", "paused", "completed", "stopped", "failed")
GLOBAL_ROLES = ("administrator", "coordinator", "operator", "researcher", "observer")
MISSION_ROLES = ("coordinator", "operator", "researcher", "observer")
DECISION_STATUSES = ("submitted", "accepted", "rejected", "recorded", "undeliverable")
RECOMMENDATION_STATUSES = (
    "pending",
    "approved",
    "confirmed",
    "rejected",
    "expired",
    "superseded",
    "revision_requested",
)


class LocationMixin:
    """A reported location. Simulator coordinates are local grid cells, never lon/lat."""

    x: Mapped[float | None] = mapped_column(default=None)
    y: Mapped[float | None] = mapped_column(default=None)
    crs: Mapped[str | None] = mapped_column(String(64), default=None)
    uncertainty: Mapped[float | None] = mapped_column(default=None)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(_in("global_role", GLOBAL_ROLES), name="global_role"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(255))
    global_role: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class MissionMembership(Base):
    __tablename__ = "mission_memberships"
    __table_args__ = (
        UniqueConstraint("mission_id", "user_id"),
        CheckConstraint(_in("role", MISSION_ROLES), name="role"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    mission_id: Mapped[UUID] = mapped_column(ForeignKey("missions.id"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(32))
    granted_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class RefreshToken(Base):
    """Rotating refresh tokens. Only a SHA-256 fingerprint of the token is stored."""

    __tablename__ = "refresh_tokens"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    family_id: Mapped[UUID] = mapped_column(index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    issued_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None] = mapped_column(default=None)
    replaced_by: Mapped[UUID | None] = mapped_column(default=None)


class MachineCredential(Base):
    """Agent and service credentials, kept separate from human accounts."""

    __tablename__ = "machine_credentials"
    __table_args__ = (
        CheckConstraint(_in("kind", ("agent", "service")), name="kind"),
        CheckConstraint("kind = 'service' OR mission_id IS NOT NULL", name="agent_mission"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    kind: Mapped[str] = mapped_column(String(16))
    subject: Mapped[str] = mapped_column(String(100))
    mission_id: Mapped[UUID | None] = mapped_column(ForeignKey("missions.id"), index=True)
    secret_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(default=None)


class Mission(Base):
    __tablename__ = "missions"
    __table_args__ = (CheckConstraint(_in("status", MISSION_STATUSES), name="status"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    scenario_id: Mapped[str] = mapped_column(String(100))
    sim_mission_id: Mapped[UUID]
    config: Mapped[dict[str, Any]] = mapped_column(JSONType)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class MissionRuntime(Base):
    """Fast-changing runtime counters, kept apart so user edits do not conflict with ticks."""

    __tablename__ = "mission_runtime"

    mission_id: Mapped[UUID] = mapped_column(ForeignKey("missions.id"), primary_key=True)
    last_event_sequence: Mapped[int] = mapped_column(Integer, default=0)
    current_run_id: Mapped[UUID | None] = mapped_column(default=None)
    last_sim_ms: Mapped[int] = mapped_column(Integer, default=0)
    model2_state: Mapped[str] = mapped_column(String(16), default="inactive")
    communication_state: Mapped[str] = mapped_column(String(16), default="unknown")
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class MissionStatusHistory(Base):
    __tablename__ = "mission_status_history"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    mission_id: Mapped[UUID] = mapped_column(ForeignKey("missions.id"), index=True)
    previous: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    actor: Mapped[str] = mapped_column(String(128))
    reason: Mapped[str] = mapped_column(String(500), default="")
    sim_time_ms: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    mission_id: Mapped[UUID] = mapped_column(ForeignKey("missions.id"), index=True)
    scenario_id: Mapped[str] = mapped_column(String(100))
    seed: Mapped[int]
    agents: Mapped[int]
    config: Mapped[dict[str, Any]] = mapped_column(JSONType)
    software_version: Mapped[str] = mapped_column(String(32))
    git_commit: Mapped[str | None] = mapped_column(String(64), default=None)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(default=None)
    end_reason: Mapped[str | None] = mapped_column(String(64), default=None)
    final_sim_ms: Mapped[int] = mapped_column(Integer, default=0)
    operational_metrics: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    # Evaluator-only ground-truth metrics. Exposed solely through research exports.
    research_metrics: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class Agent(Base, LocationMixin):
    __tablename__ = "agents"
    __table_args__ = (
        UniqueConstraint("mission_id", "agent_key"),
        UniqueConstraint("mission_id", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    mission_id: Mapped[UUID] = mapped_column(ForeignKey("missions.id"), index=True)
    agent_key: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(16), default="drone")
    registered_at: Mapped[datetime] = mapped_column(default=utcnow)
    availability: Mapped[str] = mapped_column(String(16), default="unknown")
    reported_state: Mapped[str | None] = mapped_column(String(32), default=None)
    communication: Mapped[str] = mapped_column(String(16), default="unknown")
    battery_fraction: Mapped[float | None] = mapped_column(default=None)
    degraded_sensors: Mapped[list[str]] = mapped_column(JSONType, default=list)
    last_report_ms: Mapped[int | None] = mapped_column(default=None)
    last_location_ms: Mapped[int | None] = mapped_column(default=None)


class AgentReport(Base, LocationMixin):
    """Consolidated agent status, health and reported-location history."""

    __tablename__ = "agent_reports"
    __table_args__ = (
        CheckConstraint(_in("report_type", ("status", "health", "communication")), name="type"),
        ForeignKeyConstraint(["mission_id", "agent_id"], ["agents.mission_id", "agents.id"]),
        Index(None, "agent_id", "sim_time_ms"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    mission_id: Mapped[UUID] = mapped_column(index=True)
    agent_id: Mapped[UUID]
    report_type: Mapped[str] = mapped_column(String(16))
    sim_time_ms: Mapped[int]
    received_at: Mapped[datetime] = mapped_column(default=utcnow)
    state: Mapped[str | None] = mapped_column(String(32), default=None)
    battery_fraction: Mapped[float | None] = mapped_column(default=None)
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class Observation(Base, LocationMixin):
    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint("mission_id", "observation_id"),
        UniqueConstraint("mission_id", "id"),
        ForeignKeyConstraint(["mission_id", "agent_id"], ["agents.mission_id", "agents.id"]),
        CheckConstraint(_in("kind", ("environment", "hazard", "possible_human")), name="kind"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence"),
        Index(None, "mission_id", "observed_ms"),
        Index(None, "mission_id", "kind"),
        Index(None, "mission_id", "x", "y"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    mission_id: Mapped[UUID] = mapped_column(ForeignKey("missions.id"))
    observation_id: Mapped[UUID]
    message_id: Mapped[UUID]
    agent_id: Mapped[UUID | None] = mapped_column(default=None)
    reporter: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(16))
    label: Mapped[str | None] = mapped_column(String(100), default=None)
    confidence: Mapped[float]
    observed_ms: Mapped[int]
    received_ms: Mapped[int]
    received_at: Mapped[datetime] = mapped_column(default=utcnow)
    map_ref: Mapped[str] = mapped_column(String(100))
    outcome: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(16))


class EvidenceObject(Base):
    __tablename__ = "evidence_objects"
    __table_args__ = (
        UniqueConstraint("mission_id", "sha256"),
        UniqueConstraint("mission_id", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    mission_id: Mapped[UUID] = mapped_column(ForeignKey("missions.id"), index=True)
    sha256: Mapped[str] = mapped_column(String(64))
    media_type: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int]
    storage_key: Mapped[str] = mapped_column(String(200))
    source_subject: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        UniqueConstraint("observation_pk", "evidence_id"),
        ForeignKeyConstraint(
            ["mission_id", "observation_pk"], ["observations.mission_id", "observations.id"]
        ),
        ForeignKeyConstraint(
            ["mission_id", "object_id"], ["evidence_objects.mission_id", "evidence_objects.id"]
        ),
        Index(None, "mission_id", "evidence_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    mission_id: Mapped[UUID]
    observation_pk: Mapped[UUID]
    evidence_id: Mapped[UUID]
    origin: Mapped[str] = mapped_column(String(100))
    captured_ms: Mapped[int]
    modality: Mapped[str] = mapped_column(String(16))
    artifact_key: Mapped[str] = mapped_column(String(100))
    object_id: Mapped[UUID | None] = mapped_column(default=None)


class Incident(Base, LocationMixin):
    """id is backend-scoped (uuid5(mission, model2_id)); model2_id is Model 2's identifier.
    Deterministic simulator IDs repeat across missions with the same scenario and seed."""

    __tablename__ = "incidents"
    __table_args__ = (
        UniqueConstraint("mission_id", "id"),
        UniqueConstraint("mission_id", "model2_id"),
        Index(None, "mission_id", "disposition"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    mission_id: Mapped[UUID] = mapped_column(ForeignKey("missions.id"), index=True)
    model2_id: Mapped[UUID]
    current_revision: Mapped[int]
    category: Mapped[str] = mapped_column(String(32))
    disposition: Mapped[str] = mapped_column(String(32))
    priority_level: Mapped[str | None] = mapped_column(String(32), default=None)
    priority_reason: Mapped[str | None] = mapped_column(String(200), default=None)
    operator_priority: Mapped[str | None] = mapped_column(String(200), default=None)
    opened_sim_ms: Mapped[int]
    updated_sim_ms: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class IncidentRevision(Base):
    """Assessment and urgency history: one row per Model 2 incident revision."""

    __tablename__ = "incident_revisions"
    __table_args__ = (
        UniqueConstraint("incident_id", "revision"),
        ForeignKeyConstraint(
            ["mission_id", "incident_id"], ["incidents.mission_id", "incidents.id"]
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    mission_id: Mapped[UUID] = mapped_column(index=True)
    incident_id: Mapped[UUID]
    revision: Mapped[int]
    category: Mapped[str] = mapped_column(String(32))
    report_message_ids: Mapped[list[str]] = mapped_column(JSONType)
    uncertainties: Mapped[list[str]] = mapped_column(JSONType)
    confirmation_id: Mapped[UUID | None] = mapped_column(default=None)
    priority_level: Mapped[str | None] = mapped_column(String(32), default=None)
    priority_reason: Mapped[str | None] = mapped_column(String(200), default=None)
    sim_time_ms: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class IncidentEvidence(Base):
    """Fusion group membership: which observations support or contradict an incident."""

    __tablename__ = "incident_evidence"
    __table_args__ = (
        UniqueConstraint("incident_id", "observation_pk"),
        ForeignKeyConstraint(
            ["mission_id", "incident_id"], ["incidents.mission_id", "incidents.id"]
        ),
        ForeignKeyConstraint(
            ["mission_id", "observation_pk"], ["observations.mission_id", "observations.id"]
        ),
        CheckConstraint(_in("role", ("supporting", "conflicting")), name="role"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    mission_id: Mapped[UUID] = mapped_column(index=True)
    incident_id: Mapped[UUID]
    observation_pk: Mapped[UUID]
    first_revision: Mapped[int]
    role: Mapped[str] = mapped_column(String(16), default="supporting")


class IncidentTransition(Base):
    __tablename__ = "incident_transitions"
    __table_args__ = (
        UniqueConstraint("incident_id", "revision", "state", "reference"),
        ForeignKeyConstraint(
            ["mission_id", "incident_id"], ["incidents.mission_id", "incidents.id"]
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    mission_id: Mapped[UUID] = mapped_column(index=True)
    incident_id: Mapped[UUID]
    revision: Mapped[int]
    previous: Mapped[str] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(32))
    actor: Mapped[str] = mapped_column(String(100))
    reference: Mapped[UUID]
    sim_time_ms: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Recommendation(Base):
    """One row per recommendation version. Model 2 issues one per incident revision."""

    __tablename__ = "recommendations"
    __table_args__ = (
        UniqueConstraint("incident_id", "incident_revision"),
        UniqueConstraint("mission_id", "id"),
        UniqueConstraint("mission_id", "model2_id"),
        ForeignKeyConstraint(
            ["mission_id", "incident_id"], ["incidents.mission_id", "incidents.id"]
        ),
        CheckConstraint(_in("status", RECOMMENDATION_STATUSES), name="status"),
        Index(None, "mission_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    mission_id: Mapped[UUID]
    model2_id: Mapped[UUID]
    incident_id: Mapped[UUID]
    incident_revision: Mapped[int]
    request: Mapped[str] = mapped_column(String(32))
    evidence_ids: Mapped[list[str]] = mapped_column(JSONType)
    unknowns: Mapped[list[str]] = mapped_column(JSONType)
    expires_ms: Mapped[int]
    status: Mapped[str] = mapped_column(String(32), default="pending")
    created_sim_ms: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class RecommendationStatusHistory(Base):
    __tablename__ = "recommendation_status_history"
    __table_args__ = (
        ForeignKeyConstraint(
            ["mission_id", "recommendation_id"],
            ["recommendations.mission_id", "recommendations.id"],
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    mission_id: Mapped[UUID] = mapped_column(index=True)
    recommendation_id: Mapped[UUID] = mapped_column(index=True)
    previous: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(String(200))
    sim_time_ms: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("mission_id", "id"),
        ForeignKeyConstraint(
            ["mission_id", "incident_id"], ["incidents.mission_id", "incidents.id"]
        ),
        Index(None, "mission_id", "sent_sim_ms"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    mission_id: Mapped[UUID]
    message_id: Mapped[UUID]
    incident_id: Mapped[UUID]
    incident_revision: Mapped[int]
    priority: Mapped[str] = mapped_column(String(32))
    priority_reason: Mapped[str] = mapped_column(String(200))
    review_state: Mapped[str] = mapped_column(String(32))
    supporting_evidence: Mapped[list[str]] = mapped_column(JSONType)
    sent_sim_ms: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    acknowledged_at: Mapped[datetime | None] = mapped_column(default=None)
    acknowledged_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), default=None)


class HumanDecision(Base):
    """Human approvals, reviews, overrides, resolution reports and acknowledgements."""

    __tablename__ = "human_decisions"
    __table_args__ = (
        UniqueConstraint("mission_id", "actor_user_id", "idempotency_key"),
        CheckConstraint(_in("status", DECISION_STATUSES), name="status"),
        CheckConstraint(
            _in("kind", ("approval", "incident_review", "override", "alert_acknowledgement")),
            name="kind",
        ),
        Index(None, "mission_id", "submitted_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    mission_id: Mapped[UUID] = mapped_column(ForeignKey("missions.id"))
    kind: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(32))
    incident_id: Mapped[UUID | None] = mapped_column(default=None)
    recommendation_id: Mapped[UUID | None] = mapped_column(default=None)
    expected_revision: Mapped[int | None] = mapped_column(default=None)
    actor_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    actor_role: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(String(100))
    idempotency_key: Mapped[str | None] = mapped_column(String(100), default=None)
    message_id: Mapped[UUID | None] = mapped_column(default=None, index=True)
    status: Mapped[str] = mapped_column(String(16), default="submitted")
    outcome_reason: Mapped[str | None] = mapped_column(String(100), default=None)
    request_id: Mapped[str] = mapped_column(String(64))
    sim_time_ms: Mapped[int | None] = mapped_column(default=None)
    submitted_at: Mapped[datetime] = mapped_column(default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(default=None)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("mission_id", "id"),
        UniqueConstraint("mission_id", "model2_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    mission_id: Mapped[UUID] = mapped_column(ForeignKey("missions.id"), index=True)
    model2_id: Mapped[UUID]
    member: Mapped[str] = mapped_column(String(100))
    target_x: Mapped[int]
    target_y: Mapped[int]
    crs: Mapped[str] = mapped_column(String(64), default=LOCAL_CRS)
    category: Mapped[str] = mapped_column(String(32))
    coordinator_state: Mapped[str] = mapped_column(String(32))
    reported_status: Mapped[str | None] = mapped_column(String(32), default=None)
    reported_ms: Mapped[int | None] = mapped_column(default=None)
    created_ms: Mapped[int]
    expires_ms: Mapped[int]
    updated_ms: Mapped[int]


class TaskEvent(Base):
    __tablename__ = "task_events"
    __table_args__ = (
        UniqueConstraint("task_id", "ordinal"),
        ForeignKeyConstraint(["mission_id", "task_id"], ["tasks.mission_id", "tasks.id"]),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    mission_id: Mapped[UUID] = mapped_column(index=True)
    task_id: Mapped[UUID] = mapped_column(index=True)
    ordinal: Mapped[int]  # position in the coordinator's task history; orders same-tick events
    sim_time_ms: Mapped[int]
    state: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(16))


class Hazard(Base, LocationMixin):
    """Environmental hazards aggregated from admitted hazard reports per reported cell."""

    __tablename__ = "hazards"
    __table_args__ = (UniqueConstraint("mission_id", "x", "y", "label"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    mission_id: Mapped[UUID] = mapped_column(ForeignKey("missions.id"), index=True)
    label: Mapped[str] = mapped_column(String(100))
    first_reported_ms: Mapped[int]
    last_reported_ms: Mapped[int]
    report_count: Mapped[int] = mapped_column(Integer, default=1)
    reporters: Mapped[list[str]] = mapped_column(JSONType, default=list)


class MissionSnapshot(Base):
    """Versioned Model 2 checkpoints and read models with integrity digests."""

    __tablename__ = "mission_snapshots"
    __table_args__ = (
        CheckConstraint(
            _in("kind", ("model2_checkpoint", "model2_read_model", "coordination")), name="kind"
        ),
        Index(None, "mission_id", "kind", "sim_time_ms"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    mission_id: Mapped[UUID] = mapped_column(ForeignKey("missions.id"))
    run_id: Mapped[UUID | None] = mapped_column(ForeignKey("simulation_runs.id"), default=None)
    kind: Mapped[str] = mapped_column(String(32))
    schema_version: Mapped[str] = mapped_column(String(16))
    sim_time_ms: Mapped[int]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType)
    sha256: Mapped[str] = mapped_column(String(64))
    complete: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class DomainEvent(Base):
    """Transactional outbox. Written in the same transaction as the state change."""

    __tablename__ = "domain_events"
    __table_args__ = (
        UniqueConstraint("mission_id", "sequence"),
        Index(None, "dispatched_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    mission_id: Mapped[UUID] = mapped_column(ForeignKey("missions.id"))
    sequence: Mapped[int]
    event_type: Mapped[str] = mapped_column(String(48))
    schema_version: Mapped[str] = mapped_column(String(8))
    source: Mapped[str] = mapped_column(String(100))
    occurred_at: Mapped[datetime] = mapped_column(default=utcnow)
    sim_time_ms: Mapped[int | None] = mapped_column(default=None)
    correlation_id: Mapped[str] = mapped_column(String(64))
    resource_type: Mapped[str] = mapped_column(String(32))
    resource_id: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType)
    dispatched_at: Mapped[datetime | None] = mapped_column(default=None)


class AuditLog(Base):
    """Append-only audit trail. Database triggers reject UPDATE and DELETE."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint(_in("outcome", ("success", "failure", "denied")), name="outcome"),
        Index(None, "mission_id", "occurred_at"),
        Index(None, "action"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    occurred_at: Mapped[datetime] = mapped_column(default=utcnow)
    actor: Mapped[str] = mapped_column(String(128))
    actor_type: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(64))
    resource_type: Mapped[str] = mapped_column(String(32))
    resource_id: Mapped[str | None] = mapped_column(String(100), default=None)
    # Deliberately no foreign key: denied requests may name missions that do not exist.
    mission_id: Mapped[UUID | None] = mapped_column(default=None)
    request_id: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(16))
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
