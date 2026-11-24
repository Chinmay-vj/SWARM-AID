"""Deny-by-default, mission-scoped permission matrix.

Administrators manage accounts and missions but hold no decision authority on a mission
unless they are also a member with an authorizing role. Domain safety rules apply to all.
"""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from backend.core.errors import Forbidden


class GlobalRole(StrEnum):
    ADMINISTRATOR = "administrator"
    COORDINATOR = "coordinator"
    OPERATOR = "operator"
    RESEARCHER = "researcher"
    OBSERVER = "observer"


class MissionRole(StrEnum):
    COORDINATOR = "coordinator"
    OPERATOR = "operator"
    RESEARCHER = "researcher"
    OBSERVER = "observer"


class MachineKind(StrEnum):
    AGENT = "agent"
    SERVICE = "service"


class Permission(StrEnum):
    MISSION_READ = "mission.read"
    MISSION_UPDATE = "mission.update"
    MISSION_CONTROL = "mission.control"
    MISSION_OVERRIDE = "mission.override"
    MEMBERSHIP_MANAGE = "membership.manage"
    INCIDENT_ACKNOWLEDGE = "incident.acknowledge"
    INCIDENT_REQUEST_REVIEW = "incident.request_review"
    INCIDENT_RESOLUTION_REPORT = "incident.resolution_report"
    INCIDENT_CLOSE = "incident.close"
    RECOMMENDATION_DECIDE = "recommendation.decide"
    RECOMMENDATION_CONFIRM = "recommendation.confirm"
    ALERT_ACKNOWLEDGE = "alert.acknowledge"
    FEEDBACK_CORRECT = "feedback.correct"
    METRICS_READ = "metrics.read"
    EXPORT_OPERATIONAL = "export.operational"
    EXPORT_RESEARCH = "export.research"
    AUDIT_READ = "audit.read"
    OBSERVATION_INGEST = "observation.ingest"
    AGENT_REPORT = "agent.report"


_READ = {Permission.MISSION_READ}
MISSION_MATRIX: dict[MissionRole, frozenset[Permission]] = {
    MissionRole.COORDINATOR: frozenset(
        _READ
        | {
            Permission.MISSION_UPDATE,
            Permission.MISSION_CONTROL,
            Permission.MISSION_OVERRIDE,
            Permission.MEMBERSHIP_MANAGE,
            Permission.INCIDENT_ACKNOWLEDGE,
            Permission.INCIDENT_REQUEST_REVIEW,
            Permission.INCIDENT_RESOLUTION_REPORT,
            Permission.INCIDENT_CLOSE,
            Permission.RECOMMENDATION_DECIDE,
            Permission.RECOMMENDATION_CONFIRM,
            Permission.ALERT_ACKNOWLEDGE,
            Permission.FEEDBACK_CORRECT,
            Permission.METRICS_READ,
            Permission.EXPORT_OPERATIONAL,
            Permission.AUDIT_READ,
        }
    ),
    MissionRole.OPERATOR: frozenset(
        _READ
        | {
            Permission.INCIDENT_ACKNOWLEDGE,
            Permission.INCIDENT_REQUEST_REVIEW,
            Permission.INCIDENT_RESOLUTION_REPORT,
            Permission.ALERT_ACKNOWLEDGE,
            Permission.FEEDBACK_CORRECT,
        }
    ),
    MissionRole.RESEARCHER: frozenset(
        _READ | {Permission.METRICS_READ, Permission.EXPORT_OPERATIONAL, Permission.EXPORT_RESEARCH}
    ),
    MissionRole.OBSERVER: frozenset(_READ),
}
# Administrators may read and manage any mission, never decide on it.
ADMIN_MISSION_PERMISSIONS = frozenset(
    {Permission.MISSION_READ, Permission.MEMBERSHIP_MANAGE, Permission.AUDIT_READ}
)
MACHINE_MATRIX: dict[MachineKind, frozenset[Permission]] = {
    MachineKind.AGENT: frozenset({Permission.OBSERVATION_INGEST, Permission.AGENT_REPORT}),
    MachineKind.SERVICE: frozenset({Permission.MISSION_READ}),
}


@dataclass(frozen=True)
class Principal:
    """An authenticated identity. Roles come from the database, never from the client."""

    subject: str
    kind: str  # "human" | "agent" | "service"
    user_id: UUID | None = None
    global_role: GlobalRole | None = None
    memberships: tuple[tuple[UUID, MissionRole], ...] = ()
    machine_mission: UUID | None = None
    credential_id: UUID | None = None

    @property
    def is_admin(self) -> bool:
        return self.global_role == GlobalRole.ADMINISTRATOR

    def mission_role(self, mission_id: UUID) -> MissionRole | None:
        return next((r for m, r in self.memberships if m == mission_id), None)

    def permissions(self, mission_id: UUID) -> frozenset[Permission]:
        if self.kind == "human":
            role = self.mission_role(mission_id)
            granted = MISSION_MATRIX[role] if role else frozenset()
            return granted | ADMIN_MISSION_PERMISSIONS if self.is_admin else granted
        if self.machine_mission != mission_id:
            return frozenset()
        return MACHINE_MATRIX[MachineKind(self.kind)]

    def can(self, permission: Permission, mission_id: UUID) -> bool:
        return permission in self.permissions(mission_id)

    def require(self, permission: Permission, mission_id: UUID) -> None:
        if not self.can(permission, mission_id):
            raise Forbidden("not permitted for this mission", code="permission_denied")

    def require_human(self) -> None:
        if self.kind != "human":
            raise Forbidden("human identity required", code="human_required")

    def can_create_missions(self) -> bool:
        return self.kind == "human" and self.global_role in (
            GlobalRole.ADMINISTRATOR,
            GlobalRole.COORDINATOR,
        )
