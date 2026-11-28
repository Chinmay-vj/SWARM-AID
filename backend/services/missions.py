"""Mission creation, membership, lifecycle and summaries."""

from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select

from backend.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from backend.core.permissions import MachineKind, MissionRole, Permission, Principal
from backend.database import models as m
from backend.database.session import Database
from backend.integrations.runtime import RuntimeManager
from backend.schemas import (
    AgentCredentialOut,
    MissionCreate,
    MissionOut,
    MissionPatch,
    MissionSummary,
    StatusHistoryOut,
)
from backend.services import audit
from backend.services.access import mission_for, paginate
from backend.services.auth import AuthService
from backend.services.events import EventType, emit


def mission_out(mission: m.Mission, runtime: m.MissionRuntime | None) -> MissionOut:
    out = MissionOut.model_validate(mission)
    if runtime is not None:
        out = out.model_copy(
            update={
                "last_sim_ms": runtime.last_sim_ms,
                "model2_state": runtime.model2_state,
                "communication_state": runtime.communication_state,
                "last_event_sequence": runtime.last_event_sequence,
                "current_run_id": runtime.current_run_id,
            }
        )
    return out


class MissionService:
    def __init__(
        self,
        db: Database,
        runtime: RuntimeManager,
        auth: AuthService,
        *,
        development: bool = False,
    ) -> None:
        self.development = development
        self.db = db
        self.runtime = runtime
        self.auth = auth

    def create(self, principal: Principal, body: MissionCreate) -> MissionOut:
        if not principal.can_create_missions():
            raise Forbidden("mission creation requires a coordinator or administrator account")
        if self.development:
            # Never fall back to the historical default seed or touch the final-evaluation range.
            if "seed" not in body.config.model_fields_set:
                raise Unprocessable(
                    "development missions need an explicit seed (12000-12999)",
                    code="seed_required",
                )
            if 900000 <= body.config.seed < 900100:
                raise Unprocessable("seed is reserved for final evaluation", code="seed_reserved")
        try:
            scenario = body.config.validated()
        except ValueError as exc:
            raise Unprocessable(str(exc), code="invalid_configuration") from exc
        from simulation.core.engine import Engine

        sim_mission_id = Engine(scenario).mission_id
        assert principal.user_id is not None
        with self.db.transaction() as session:
            mission = m.Mission(
                name=body.name,
                description=body.description,
                scenario_id=body.config.scenario_id,
                sim_mission_id=sim_mission_id,
                config=body.config.model_dump(mode="json"),
                created_by=principal.user_id,
            )
            session.add(mission)
            session.flush()
            session.add(m.MissionRuntime(mission_id=mission.id))
            session.add(
                m.MissionMembership(
                    mission_id=mission.id,
                    user_id=principal.user_id,
                    role=MissionRole.COORDINATOR.value,
                    granted_by=principal.subject,
                )
            )
            session.flush()
            emit(
                session,
                mission.id,
                EventType.MISSION_CREATED,
                source=principal.subject,
                resource_type="mission",
                resource_id=mission.id,
                payload={"name": mission.name, "scenario_id": mission.scenario_id},
            )
            audit.record(
                session,
                principal,
                "mission.create",
                resource_type="mission",
                resource_id=mission.id,
                mission_id=mission.id,
                details={"scenario_id": mission.scenario_id, "config": mission.config},
            )
            return mission_out(mission, session.get(m.MissionRuntime, mission.id))

    def list_missions(
        self, principal: Principal, status: str | None, limit: int, offset: int
    ) -> tuple[list[MissionOut], int]:
        with self.db.read() as session:
            query = select(m.Mission).order_by(m.Mission.created_at.desc())
            if not principal.is_admin:
                visible = [mid for mid, _ in principal.memberships]
                if principal.machine_mission:
                    visible.append(principal.machine_mission)
                query = query.where(m.Mission.id.in_(visible))
            if status:
                query = query.where(m.Mission.status == status)
            rows, total = paginate(session, query, limit, offset)
            return [mission_out(r, session.get(m.MissionRuntime, r.id)) for r in rows], total

    def get(self, principal: Principal, mission_id: UUID) -> MissionOut:
        with self.db.read() as session:
            mission = mission_for(session, principal, mission_id, Permission.MISSION_READ)
            return mission_out(mission, session.get(m.MissionRuntime, mission_id))

    def patch(self, principal: Principal, mission_id: UUID, body: MissionPatch) -> MissionOut:
        with self.db.transaction() as session:
            mission = mission_for(session, principal, mission_id, Permission.MISSION_UPDATE)
            if mission.version != body.version:
                raise Conflict(
                    "mission was modified; reload and retry",
                    code="stale_version",
                    details={"current_version": mission.version},
                )
            changes = body.model_dump(exclude={"version"}, exclude_none=True)
            for key, value in changes.items():
                setattr(mission, key, value)
            session.flush()
            audit.record(
                session,
                principal,
                "mission.update",
                resource_type="mission",
                resource_id=mission_id,
                mission_id=mission_id,
                details={"fields": sorted(changes)},
            )
            return mission_out(mission, session.get(m.MissionRuntime, mission_id))

    def authorize_control(self, principal: Principal, mission_id: UUID) -> None:
        with self.db.read() as session:
            mission_for(session, principal, mission_id, Permission.MISSION_CONTROL)

    def audit_control(
        self,
        principal: Principal,
        mission_id: UUID,
        action: str,
        reason: str,
        outcome: str = "success",
    ) -> None:
        with self.db.transaction() as session:
            audit.record(
                session,
                principal,
                f"mission.{action}",
                resource_type="mission",
                resource_id=mission_id,
                mission_id=mission_id,
                outcome="success" if outcome == "success" else "failure",
                details={"reason": reason},
            )

    def history(self, principal: Principal, mission_id: UUID) -> list[StatusHistoryOut]:
        with self.db.read() as session:
            mission_for(session, principal, mission_id, Permission.MISSION_READ)
            rows = session.scalars(
                select(m.MissionStatusHistory)
                .where(m.MissionStatusHistory.mission_id == mission_id)
                .order_by(m.MissionStatusHistory.created_at)
            )
            return [StatusHistoryOut.model_validate(r) for r in rows]

    def summary(self, principal: Principal, mission_id: UUID) -> MissionSummary:
        with self.db.read() as session:
            mission = mission_for(session, principal, mission_id, Permission.MISSION_READ)

            def count(model: Any, *where: Any) -> int:
                value = session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.mission_id == mission_id, *where)
                )
                return int(value or 0)

            def grouped(column: Any, model: Any) -> dict[str, int]:
                rows = session.execute(
                    select(column, func.count())
                    .where(model.mission_id == mission_id)
                    .group_by(column)
                )
                return {str(k): int(cast(int, v)) for k, v in rows}

            return MissionSummary(
                mission=mission_out(mission, session.get(m.MissionRuntime, mission_id)),
                agents=count(m.Agent),
                agents_connected=count(m.Agent, m.Agent.communication == "connected"),
                observations=count(m.Observation),
                incidents_by_disposition=grouped(m.Incident.disposition, m.Incident),
                pending_recommendations=count(
                    m.Recommendation, m.Recommendation.status == "pending"
                ),
                open_alerts=count(m.Alert, m.Alert.acknowledged_at.is_(None)),
                hazards=count(m.Hazard),
                tasks_by_state=grouped(m.Task.coordinator_state, m.Task),
            )

    def metrics(self, principal: Principal, mission_id: UUID) -> dict[str, object]:
        """Operational metrics only. Evaluator ground truth is limited to research exports."""
        with self.db.read() as session:
            mission_for(session, principal, mission_id, Permission.METRICS_READ)
            state = session.get(m.MissionRuntime, mission_id)
            runs = session.scalars(
                select(m.SimulationRun)
                .where(m.SimulationRun.mission_id == mission_id)
                .order_by(m.SimulationRun.started_at)
            )
            live: dict[str, object] | None = None
            rt = self.runtime.runtimes.get(mission_id)
            if rt is not None and rt.task is not None and not rt.task.done():
                with rt.ctx.lock:
                    live = rt.sync.operational_metrics()
            decisions = session.execute(
                select(m.HumanDecision.status, func.count())
                .where(m.HumanDecision.mission_id == mission_id)
                .group_by(m.HumanDecision.status)
            )
            return {
                "mission_id": str(mission_id),
                "sim_time_ms": state.last_sim_ms if state else 0,
                "live": live,
                "human_decisions": {str(k): int(v) for k, v in decisions},
                "runs": [
                    {
                        "run_id": str(r.id),
                        "started_at": r.started_at.isoformat(),
                        "ended_at": r.ended_at.isoformat() if r.ended_at else None,
                        "end_reason": r.end_reason,
                        "final_sim_ms": r.final_sim_ms,
                        "operational_metrics": r.operational_metrics,
                    }
                    for r in runs
                ],
            }

    # ----- membership and machine credentials ----------------------------------------------
    def add_member(
        self, principal: Principal, mission_id: UUID, user_id: UUID, role: MissionRole
    ) -> m.MissionMembership:
        with self.db.transaction() as session:
            mission_for(session, principal, mission_id, Permission.MEMBERSHIP_MANAGE)
            if session.get(m.User, user_id) is None:
                raise NotFound("user not found")
            if session.scalar(
                select(m.MissionMembership.id).where(
                    m.MissionMembership.mission_id == mission_id,
                    m.MissionMembership.user_id == user_id,
                )
            ):
                raise Conflict("user is already a member", code="duplicate_membership")
            membership = m.MissionMembership(
                mission_id=mission_id,
                user_id=user_id,
                role=role.value,
                granted_by=principal.subject,
            )
            session.add(membership)
            session.flush()
            audit.record(
                session,
                principal,
                "membership.grant",
                resource_type="membership",
                resource_id=membership.id,
                mission_id=mission_id,
                details={"user_id": str(user_id), "role": role.value},
            )
            return membership

    def create_agent_credential(
        self, principal: Principal, mission_id: UUID, agent_key: str
    ) -> AgentCredentialOut:
        with self.db.transaction() as session:
            mission = mission_for(session, principal, mission_id, Permission.MISSION_CONTROL)
            agents = int(mission.config.get("agents", 0))
            if agent_key not in {f"d{i}" for i in range(agents)}:
                raise Unprocessable("agent key is not part of this mission", code="unknown_agent")
            credential, secret = self.auth.create_machine_credential(
                session, MachineKind.AGENT, agent_key, mission_id
            )
            audit.record(
                session,
                principal,
                "credential.create",
                resource_type="machine_credential",
                resource_id=credential.id,
                mission_id=mission_id,
                details={"agent_key": agent_key},
            )
            return AgentCredentialOut(
                credential_id=credential.id,
                agent_key=agent_key,
                mission_id=mission_id,
                secret=secret,
            )
