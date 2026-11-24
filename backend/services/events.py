"""Typed domain events written to the transactional outbox.

Each event is inserted in the same transaction as the state change it describes and receives a
per-mission sequence number. Delivery to WebSocket clients is at-least-once; consumers
de-duplicate by (mission_id, sequence). Exactly-once delivery is not claimed.
"""

from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.core.logging import request_id_var
from backend.database.models import DomainEvent, MissionRuntime

EVENT_SCHEMA_VERSION = "1"


class EventType(StrEnum):
    MISSION_CREATED = "MISSION_CREATED"
    MISSION_STARTED = "MISSION_STARTED"
    MISSION_PAUSED = "MISSION_PAUSED"
    MISSION_RESUMED = "MISSION_RESUMED"
    MISSION_STOPPED = "MISSION_STOPPED"
    MISSION_COMPLETED = "MISSION_COMPLETED"
    AGENT_REGISTERED = "AGENT_REGISTERED"
    AGENT_STATUS_UPDATED = "AGENT_STATUS_UPDATED"
    AGENT_HEALTH_UPDATED = "AGENT_HEALTH_UPDATED"
    OBSERVATION_RECEIVED = "OBSERVATION_RECEIVED"
    EVIDENCE_GROUP_UPDATED = "EVIDENCE_GROUP_UPDATED"
    INCIDENT_CREATED = "INCIDENT_CREATED"
    INCIDENT_UPDATED = "INCIDENT_UPDATED"
    INCIDENT_ESCALATED = "INCIDENT_ESCALATED"
    HAZARD_REPORTED = "HAZARD_REPORTED"
    RECOMMENDATION_CREATED = "RECOMMENDATION_CREATED"
    RECOMMENDATION_REVISED = "RECOMMENDATION_REVISED"
    RECOMMENDATION_APPROVED = "RECOMMENDATION_APPROVED"
    RECOMMENDATION_REJECTED = "RECOMMENDATION_REJECTED"
    HUMAN_REVIEW_REQUESTED = "HUMAN_REVIEW_REQUESTED"
    HUMAN_DECISION_RESOLVED = "HUMAN_DECISION_RESOLVED"
    HUMAN_OVERRIDE_RECORDED = "HUMAN_OVERRIDE_RECORDED"
    ALERT_RAISED = "ALERT_RAISED"
    TASK_UPDATED = "TASK_UPDATED"
    COMMUNICATION_DEGRADED = "COMMUNICATION_DEGRADED"
    COMMUNICATION_RESTORED = "COMMUNICATION_RESTORED"
    MODEL_2_UNAVAILABLE = "MODEL_2_UNAVAILABLE"
    MODEL_2_RECOVERED = "MODEL_2_RECOVERED"
    METRICS_UPDATED = "METRICS_UPDATED"


# WebSocket subscription topic for each event type.
TOPICS: dict[EventType, str] = {
    EventType.MISSION_CREATED: "mission",
    EventType.MISSION_STARTED: "mission",
    EventType.MISSION_PAUSED: "mission",
    EventType.MISSION_RESUMED: "mission",
    EventType.MISSION_STOPPED: "mission",
    EventType.MISSION_COMPLETED: "mission",
    EventType.AGENT_REGISTERED: "agents",
    EventType.AGENT_STATUS_UPDATED: "agents",
    EventType.AGENT_HEALTH_UPDATED: "agents",
    EventType.OBSERVATION_RECEIVED: "observations",
    EventType.EVIDENCE_GROUP_UPDATED: "incidents",
    EventType.INCIDENT_CREATED: "incidents",
    EventType.INCIDENT_UPDATED: "incidents",
    EventType.INCIDENT_ESCALATED: "incidents",
    EventType.HAZARD_REPORTED: "hazards",
    EventType.RECOMMENDATION_CREATED: "recommendations",
    EventType.RECOMMENDATION_REVISED: "recommendations",
    EventType.RECOMMENDATION_APPROVED: "recommendations",
    EventType.RECOMMENDATION_REJECTED: "recommendations",
    EventType.HUMAN_REVIEW_REQUESTED: "review",
    EventType.HUMAN_DECISION_RESOLVED: "review",
    EventType.HUMAN_OVERRIDE_RECORDED: "review",
    EventType.ALERT_RAISED: "alerts",
    EventType.TASK_UPDATED: "coverage",
    EventType.COMMUNICATION_DEGRADED: "communication",
    EventType.COMMUNICATION_RESTORED: "communication",
    EventType.MODEL_2_UNAVAILABLE: "model2",
    EventType.MODEL_2_RECOVERED: "model2",
    EventType.METRICS_UPDATED: "metrics",
}
ALL_TOPICS = frozenset(TOPICS.values())


def next_sequence(session: Session, mission_id: UUID) -> int:
    """Atomically allocate the next per-mission sequence (row-locking UPDATE ... RETURNING)."""
    sequence = session.execute(
        update(MissionRuntime)
        .where(MissionRuntime.mission_id == mission_id)
        .values(last_event_sequence=MissionRuntime.last_event_sequence + 1)
        .returning(MissionRuntime.last_event_sequence)
    ).scalar_one()
    return int(sequence)


def emit(
    session: Session,
    mission_id: UUID,
    event_type: EventType,
    *,
    source: str,
    resource_type: str,
    resource_id: object,
    payload: dict[str, Any],
    sim_time_ms: int | None = None,
    correlation_id: str | None = None,
) -> DomainEvent:
    event = DomainEvent(
        mission_id=mission_id,
        sequence=next_sequence(session, mission_id),
        event_type=event_type.value,
        schema_version=EVENT_SCHEMA_VERSION,
        source=source,
        sim_time_ms=sim_time_ms,
        correlation_id=correlation_id or request_id_var.get(),
        resource_type=resource_type,
        resource_id=str(resource_id),
        payload=payload,
    )
    session.add(event)
    return event
