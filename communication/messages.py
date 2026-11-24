"""Version 1 wire format. The discriminator lives inside the payload."""

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from agents.shared.domain import (
    Action,
    Cell,
    DroneState,
    Evidence,
    Id,
    Incident,
    Observation,
    Recommendation,
    Record,
    Score,
    Tick,
)


class Registration(Record):
    message_type: Literal["registration"]
    role: Literal["drone", "command", "operator"]
    session_id: UUID


class Heartbeat(Record):
    message_type: Literal["heartbeat"]
    state: DroneState


class EnvironmentalObservation(Record):
    message_type: Literal["environmental_observation"]
    observation: Observation
    feature: Id


class PossibleHumanDetection(Record):
    message_type: Literal["possible_human_detection"]
    observation: Observation


class HazardDetection(Record):
    message_type: Literal["hazard_detection"]
    observation: Observation
    hazard: Id


class IncidentUpdate(Record):
    message_type: Literal["incident_update"]
    incident: Incident
    recommendation: Recommendation | None = None


class EvidenceReference(Record):
    message_type: Literal["evidence_reference"]
    evidence: Evidence


class MissionInstruction(Record):
    message_type: Literal["mission_instruction"]
    task_id: UUID
    action: Action


class TaskStatus(Record):
    message_type: Literal["task_status"]
    task_id: UUID
    status: Literal["accepted", "active", "completed", "rejected", "expired"]


class AgentHealth(Record):
    message_type: Literal["agent_health"]
    battery_fraction: Score
    degraded_sensors: tuple[Id, ...]
    cell: Cell | None = None


class Acknowledgement(Record):
    message_type: Literal["acknowledgement"]
    acknowledged_id: UUID
    outcome: Literal["accepted", "duplicate", "rejected", "expired"]


class ConnectionLoss(Record):
    message_type: Literal["connection_loss"]
    peer: Id
    last_seen_ms: Tick


class Reconnection(Record):
    message_type: Literal["reconnection"]
    peer: Id
    session_id: UUID
    last_contiguous_sequence: Tick | None


class HumanApproval(Record):
    message_type: Literal["human_approval"]
    recommendation_id: UUID
    incident_id: UUID
    revision: Annotated[int, Field(strict=True, ge=1)]
    decision: Literal["approve_review", "reject", "confirm_rescue_need"]
    reason: Id


class HumanOverride(Record):
    message_type: Literal["human_override"]
    action: Literal["pause", "end", "resume"]
    reason: Id


class ErrorReport(Record):
    message_type: Literal["error_report"]
    code: Id
    related_id: UUID | None = None
    retryable: Annotated[bool, Field(strict=True)]


Payload = Annotated[
    Registration
    | Heartbeat
    | EnvironmentalObservation
    | PossibleHumanDetection
    | HazardDetection
    | IncidentUpdate
    | EvidenceReference
    | MissionInstruction
    | TaskStatus
    | AgentHealth
    | Acknowledgement
    | ConnectionLoss
    | Reconnection
    | HumanApproval
    | HumanOverride
    | ErrorReport,
    Field(discriminator="message_type"),
]


class Envelope(Record):
    schema_version: Literal["1.0"]
    message_id: UUID
    source: Id
    destination: Id
    mission_id: UUID
    session_id: UUID
    timestamp: AwareDatetime
    sent_ms: Tick
    sequence: Tick
    priority: Literal["routine", "urgent", "control"]
    correlation_id: UUID
    expires_ms: Tick | None = None
    payload: Payload

    @model_validator(mode="after")
    def check_consistency(self) -> Self:
        if self.expires_ms is not None and self.expires_ms <= self.sent_ms:
            raise ValueError("expiry must follow send time")
        if (
            isinstance(self.payload, (MissionInstruction, HumanApproval, HumanOverride))
            and self.expires_ms is None
        ):
            raise ValueError("control messages require expiry")
        if (
            isinstance(self.payload, (Registration, Reconnection))
            and self.payload.session_id != self.session_id
        ):
            raise ValueError("session mismatch")
        if (
            isinstance(
                self.payload, (EnvironmentalObservation, PossibleHumanDetection, HazardDetection)
            )
            and self.payload.observation.observed_ms > self.sent_ms
        ):
            raise ValueError("observation is later than send time")
        if (
            isinstance(self.payload, EvidenceReference)
            and self.payload.evidence.captured_ms > self.sent_ms
        ):
            raise ValueError("evidence is later than send time")
        if isinstance(self.payload, ConnectionLoss) and self.payload.last_seen_ms > self.sent_ms:
            raise ValueError("last contact is later than send time")
        if isinstance(self.payload, IncidentUpdate) and self.payload.recommendation:
            rec = self.payload.recommendation
            if rec.expires_ms <= self.sent_ms:
                raise ValueError("attached recommendation expired before publication")
            inc = self.payload.incident
            if (rec.incident_id, rec.incident_revision) != (inc.incident_id, inc.revision):
                raise ValueError("recommendation must reference the attached revision")
        return self
