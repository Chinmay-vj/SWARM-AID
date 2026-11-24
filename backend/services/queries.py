"""Read models for the API and the Phase 8 dashboard. No private Model 1 memory and no
simulator ground truth is exposed: every value here was reported by an agent or decided by
Model 2 or a human."""

from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.errors import NotFound
from backend.core.permissions import Permission, Principal
from backend.database import models as m
from backend.database.session import Database
from backend.integrations.runtime import RuntimeManager
from backend.integrations.simulation_adapter import MissionConfig
from backend.schemas import (
    AgentOut,
    AgentReportOut,
    AlertOut,
    AuditOut,
    DecisionOut,
    EventOut,
    EvidenceGroupOut,
    EvidenceOut,
    HazardOut,
    IncidentOut,
    IncidentRevisionOut,
    IncidentTransitionOut,
    Location,
    MapFeature,
    MapLayer,
    MapResponse,
    ObservationOut,
    RecommendationOut,
    RecommendationStatusOut,
    ReviewItem,
    SectorOut,
    TaskEventOut,
    TaskOut,
    location,
)
from backend.services.access import mission_for, owned, paginate

FRESHNESS_MS = 1500  # matches Model 2's default freshness window
STALE_TASK_MS = 3000


class QueryService:
    def __init__(self, db: Database, runtime: RuntimeManager) -> None:
        self.db = db
        self.runtime = runtime

    @staticmethod
    def _now(session: Session, mission_id: UUID) -> int:
        state = session.get(m.MissionRuntime, mission_id)
        return state.last_sim_ms if state else 0

    # ----- agents --------------------------------------------------------------------------
    @staticmethod
    def agent_out(a: m.Agent) -> AgentOut:
        return AgentOut(
            id=a.id,
            mission_id=a.mission_id,
            agent_key=a.agent_key,
            kind=a.kind,
            availability=a.availability,
            reported_state=a.reported_state,
            communication=a.communication,
            battery_fraction=a.battery_fraction,
            degraded_sensors=list(a.degraded_sensors),
            last_report_ms=a.last_report_ms,
            location=location(a),
            last_location_ms=a.last_location_ms,
        )

    def agents(self, principal: Principal, mission_id: UUID) -> list[AgentOut]:
        with self.db.read() as session:
            mission_for(session, principal, mission_id, Permission.MISSION_READ)
            rows = session.scalars(
                select(m.Agent).where(m.Agent.mission_id == mission_id).order_by(m.Agent.agent_key)
            )
            return [self.agent_out(a) for a in rows]

    def agent(self, principal: Principal, agent_id: UUID) -> AgentOut:
        with self.db.read() as session:
            return self.agent_out(owned(session, principal, m.Agent, agent_id))

    def agent_reports(
        self, principal: Principal, agent_id: UUID, report_type: str | None, limit: int, offset: int
    ) -> tuple[list[AgentReportOut], int]:
        with self.db.read() as session:
            owned(session, principal, m.Agent, agent_id)
            query = (
                select(m.AgentReport)
                .where(m.AgentReport.agent_id == agent_id)
                .order_by(m.AgentReport.sim_time_ms.desc())
            )
            if report_type:
                query = query.where(m.AgentReport.report_type == report_type)
            rows, total = paginate(session, query, limit, offset)
            return [
                AgentReportOut(
                    report_type=r.report_type,
                    sim_time_ms=r.sim_time_ms,
                    state=r.state,
                    battery_fraction=r.battery_fraction,
                    location=location(r),
                    details=r.details,
                )
                for r in rows
            ], total

    # ----- observations and evidence -------------------------------------------------------
    @staticmethod
    def observation_out(o: m.Observation, now: int) -> ObservationOut:
        age = max(0, now - o.observed_ms)
        return ObservationOut(
            id=o.id,
            mission_id=o.mission_id,
            observation_id=o.observation_id,
            message_id=o.message_id,
            reporter=o.reporter,
            kind=o.kind,
            label=o.label,
            confidence=o.confidence,
            observed_ms=o.observed_ms,
            received_ms=o.received_ms,
            age_ms=age,
            stale=age >= FRESHNESS_MS,
            outcome=o.outcome,
            source=o.source,
            location=location(o, o.map_ref),
        )

    def observations(
        self,
        principal: Principal,
        mission_id: UUID,
        *,
        kind: str | None,
        reporter: str | None,
        outcome: str | None,
        bbox: tuple[float, float, float, float] | None,
        since_ms: int | None,
        sort: str,
        limit: int,
        offset: int,
        agent_id: UUID | None = None,
    ) -> tuple[list[ObservationOut], int]:
        with self.db.read() as session:
            mission_for(session, principal, mission_id, Permission.MISSION_READ)
            query = select(m.Observation).where(m.Observation.mission_id == mission_id)
            if kind:
                query = query.where(m.Observation.kind == kind)
            if reporter:
                query = query.where(m.Observation.reporter == reporter)
            if agent_id:
                query = query.where(m.Observation.agent_id == agent_id)
            if outcome:
                query = query.where(m.Observation.outcome == outcome)
            if since_ms is not None:
                query = query.where(m.Observation.observed_ms >= since_ms)
            if bbox:
                x0, y0, x1, y1 = bbox
                query = query.where(
                    m.Observation.x.between(min(x0, x1), max(x0, x1)),
                    m.Observation.y.between(min(y0, y1), max(y0, y1)),
                )
            order = m.Observation.observed_ms
            query = query.order_by(
                order.desc() if sort == "-observed_ms" else order, m.Observation.id
            )
            rows, total = paginate(session, query, limit, offset)
            now = self._now(session, mission_id)
            return [self.observation_out(o, now) for o in rows], total

    def observation(self, principal: Principal, pk: UUID) -> ObservationOut:
        with self.db.read() as session:
            o = owned(session, principal, m.Observation, pk)
            return self.observation_out(o, self._now(session, o.mission_id))

    def evidence(self, principal: Principal, pk: UUID) -> list[EvidenceOut]:
        with self.db.read() as session:
            owned(session, principal, m.Observation, pk)
            rows = session.scalars(select(m.Evidence).where(m.Evidence.observation_pk == pk))
            return [
                EvidenceOut(
                    evidence_id=e.evidence_id,
                    origin=e.origin,
                    captured_ms=e.captured_ms,
                    modality=e.modality,
                    artifact_key=e.artifact_key,
                    object_id=e.object_id,
                )
                for e in rows
            ]

    def evidence_group(self, principal: Principal, incident_id: UUID) -> EvidenceGroupOut:
        with self.db.read() as session:
            incident = owned(session, principal, m.Incident, incident_id)
            rows = session.scalars(
                select(m.Observation)
                .join(m.IncidentEvidence, m.IncidentEvidence.observation_pk == m.Observation.id)
                .where(m.IncidentEvidence.incident_id == incident_id)
                .order_by(m.Observation.observed_ms)
            ).all()
            now = self._now(session, incident.mission_id)
            return EvidenceGroupOut(
                evidence_group_id=incident.id,
                incident_id=incident.id,
                observations=[self.observation_out(o, now) for o in rows],
                distinct_reporters=sorted({o.reporter for o in rows}),
            )

    # ----- incidents -----------------------------------------------------------------------
    def incident_out(self, session: Session, i: m.Incident, now: int) -> IncidentOut:
        current = session.scalar(
            select(m.Recommendation.id).where(
                m.Recommendation.incident_id == i.id, m.Recommendation.status == "pending"
            )
        )
        roles = dict(
            session.execute(
                select(m.IncidentEvidence.role, func.count())
                .where(m.IncidentEvidence.incident_id == i.id)
                .group_by(m.IncidentEvidence.role)
            ).all()
        )
        return IncidentOut(
            id=i.id,
            mission_id=i.mission_id,
            revision=i.current_revision,
            category=i.category,
            disposition=i.disposition,
            priority_level=i.priority_level,
            priority_reason=i.priority_reason,
            operator_priority=i.operator_priority,
            location=location(i),
            opened_sim_ms=i.opened_sim_ms,
            updated_sim_ms=i.updated_sim_ms,
            freshness_ms=max(0, now - i.updated_sim_ms),
            current_recommendation_id=current,
            supporting_observations=int(roles.get("supporting", 0)),
            conflicting_observations=int(roles.get("conflicting", 0)),
        )

    def incidents(
        self,
        principal: Principal,
        mission_id: UUID,
        disposition: str | None,
        category: str | None,
        priority: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[IncidentOut], int]:
        with self.db.read() as session:
            mission_for(session, principal, mission_id, Permission.MISSION_READ)
            query = select(m.Incident).where(m.Incident.mission_id == mission_id)
            if disposition:
                query = query.where(m.Incident.disposition == disposition)
            if category:
                query = query.where(m.Incident.category == category)
            if priority:
                query = query.where(m.Incident.priority_level == priority)
            query = query.order_by(m.Incident.updated_sim_ms.desc(), m.Incident.id)
            rows, total = paginate(session, query, limit, offset)
            now = self._now(session, mission_id)
            return [self.incident_out(session, i, now) for i in rows], total

    def incident(self, principal: Principal, incident_id: UUID) -> IncidentOut:
        with self.db.read() as session:
            i = owned(session, principal, m.Incident, incident_id)
            return self.incident_out(session, i, self._now(session, i.mission_id))

    def incident_revisions(
        self, principal: Principal, incident_id: UUID
    ) -> list[IncidentRevisionOut]:
        with self.db.read() as session:
            owned(session, principal, m.Incident, incident_id)
            rows = session.scalars(
                select(m.IncidentRevision)
                .where(m.IncidentRevision.incident_id == incident_id)
                .order_by(m.IncidentRevision.revision)
            )
            return [IncidentRevisionOut.model_validate(r) for r in rows]

    def incident_history(
        self, principal: Principal, incident_id: UUID
    ) -> list[IncidentTransitionOut]:
        with self.db.read() as session:
            owned(session, principal, m.Incident, incident_id)
            rows = session.scalars(
                select(m.IncidentTransition)
                .where(m.IncidentTransition.incident_id == incident_id)
                .order_by(m.IncidentTransition.sim_time_ms, m.IncidentTransition.revision)
            )
            return [IncidentTransitionOut.model_validate(r) for r in rows]

    # ----- recommendations -----------------------------------------------------------------
    def recommendations(
        self, principal: Principal, mission_id: UUID, status: str | None, limit: int, offset: int
    ) -> tuple[list[RecommendationOut], int]:
        with self.db.read() as session:
            mission_for(session, principal, mission_id, Permission.MISSION_READ)
            query = select(m.Recommendation).where(m.Recommendation.mission_id == mission_id)
            if status:
                query = query.where(m.Recommendation.status == status)
            query = query.order_by(m.Recommendation.created_sim_ms.desc(), m.Recommendation.id)
            rows, total = paginate(session, query, limit, offset)
            return [RecommendationOut.model_validate(r) for r in rows], total

    def recommendation(self, principal: Principal, rec_id: UUID) -> RecommendationOut:
        with self.db.read() as session:
            return RecommendationOut.model_validate(
                owned(session, principal, m.Recommendation, rec_id)
            )

    def recommendation_versions(
        self, principal: Principal, rec_id: UUID
    ) -> list[RecommendationOut]:
        with self.db.read() as session:
            rec = owned(session, principal, m.Recommendation, rec_id)
            rows = session.scalars(
                select(m.Recommendation)
                .where(m.Recommendation.incident_id == rec.incident_id)
                .order_by(m.Recommendation.incident_revision)
            )
            return [RecommendationOut.model_validate(r) for r in rows]

    def recommendation_history(
        self, principal: Principal, rec_id: UUID
    ) -> list[RecommendationStatusOut]:
        with self.db.read() as session:
            owned(session, principal, m.Recommendation, rec_id)
            rows = session.scalars(
                select(m.RecommendationStatusHistory)
                .where(m.RecommendationStatusHistory.recommendation_id == rec_id)
                .order_by(m.RecommendationStatusHistory.created_at)
            )
            return [RecommendationStatusOut.model_validate(r) for r in rows]

    def recommendation_evidence(self, principal: Principal, rec_id: UUID) -> list[EvidenceOut]:
        with self.db.read() as session:
            rec = owned(session, principal, m.Recommendation, rec_id)
            ids = [UUID(e) for e in rec.evidence_ids]
            rows = session.scalars(
                select(m.Evidence).where(
                    m.Evidence.mission_id == rec.mission_id, m.Evidence.evidence_id.in_(ids)
                )
            )
            return [
                EvidenceOut(
                    evidence_id=e.evidence_id,
                    origin=e.origin,
                    captured_ms=e.captured_ms,
                    modality=e.modality,
                    artifact_key=e.artifact_key,
                    object_id=e.object_id,
                )
                for e in rows
            ]

    # ----- oversight read models -----------------------------------------------------------
    def review_queue(self, principal: Principal, mission_id: UUID) -> list[ReviewItem]:
        with self.db.read() as session:
            mission_for(session, principal, mission_id, Permission.MISSION_READ)
            now = self._now(session, mission_id)
            rows = session.scalars(
                select(m.Recommendation)
                .where(
                    m.Recommendation.mission_id == mission_id,
                    m.Recommendation.status == "pending",
                    m.Recommendation.expires_ms > now,
                )
                .order_by(m.Recommendation.expires_ms)
            )
            items = []
            for rec in rows:
                incident = session.get(m.Incident, rec.incident_id)
                assert incident is not None
                if incident.disposition != "human_review_pending":
                    continue
                items.append(
                    ReviewItem(
                        incident=self.incident_out(session, incident, now),
                        recommendation=RecommendationOut.model_validate(rec),
                        remaining_ms=rec.expires_ms - now,
                    )
                )
            rank = {"potentially_urgent": 0, "elevated": 1, "review_required": 2}
            return sorted(
                items, key=lambda i: (rank.get(i.incident.priority_level or "", 3), i.remaining_ms)
            )

    def alerts(
        self, principal: Principal, mission_id: UUID, unacknowledged: bool, limit: int, offset: int
    ) -> tuple[list[AlertOut], int]:
        with self.db.read() as session:
            mission_for(session, principal, mission_id, Permission.MISSION_READ)
            query = select(m.Alert).where(m.Alert.mission_id == mission_id)
            if unacknowledged:
                query = query.where(m.Alert.acknowledged_at.is_(None))
            rows, total = paginate(
                session, query.order_by(m.Alert.sent_sim_ms.desc(), m.Alert.id), limit, offset
            )
            return [AlertOut.model_validate(a) for a in rows], total

    def decisions(
        self, principal: Principal, mission_id: UUID, limit: int, offset: int
    ) -> tuple[list[DecisionOut], int]:
        with self.db.read() as session:
            mission_for(session, principal, mission_id, Permission.MISSION_READ)
            query = (
                select(m.HumanDecision)
                .where(m.HumanDecision.mission_id == mission_id)
                .order_by(m.HumanDecision.submitted_at.desc())
            )
            rows, total = paginate(session, query, limit, offset)
            return [DecisionOut.model_validate(d) for d in rows], total

    # ----- coordination --------------------------------------------------------------------
    @staticmethod
    def task_out(t: m.Task, now: int) -> TaskOut:
        terminal = {"completed", "expired", "failed", "cancelled"}
        knowledge: Literal["coordinator_known", "reported", "conflicting", "stale", "unknown"]
        if t.reported_status is None:
            knowledge = (
                "stale"
                if t.coordinator_state not in terminal and now - t.updated_ms > STALE_TASK_MS
                else "coordinator_known"
            )
        elif (t.reported_status == "completed") != (t.coordinator_state == "completed"):
            knowledge = "conflicting"
        else:
            knowledge = "reported"
        return TaskOut(
            id=t.id,
            member=t.member,
            target=Location(crs=t.crs, x=t.target_x, y=t.target_y, units="cell"),
            category=t.category,
            coordinator_state=t.coordinator_state,
            reported_status=t.reported_status,
            reported_ms=t.reported_ms,
            knowledge=knowledge,
            created_ms=t.created_ms,
            expires_ms=t.expires_ms,
            updated_ms=t.updated_ms,
        )

    def tasks(
        self,
        principal: Principal,
        mission_id: UUID,
        member: str | None,
        state: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[TaskOut], int]:
        with self.db.read() as session:
            mission_for(session, principal, mission_id, Permission.MISSION_READ)
            query = select(m.Task).where(m.Task.mission_id == mission_id)
            if member:
                query = query.where(m.Task.member == member)
            if state:
                query = query.where(m.Task.coordinator_state == state)
            rows, total = paginate(
                session, query.order_by(m.Task.created_ms, m.Task.id), limit, offset
            )
            now = self._now(session, mission_id)
            return [self.task_out(t, now) for t in rows], total

    def task(self, principal: Principal, task_id: UUID) -> TaskOut:
        with self.db.read() as session:
            t = owned(session, principal, m.Task, task_id)
            return self.task_out(t, self._now(session, t.mission_id))

    def task_history(self, principal: Principal, task_id: UUID) -> list[TaskEventOut]:
        with self.db.read() as session:
            owned(session, principal, m.Task, task_id)
            rows = session.scalars(
                select(m.TaskEvent)
                .where(m.TaskEvent.task_id == task_id)
                .order_by(m.TaskEvent.ordinal)
            )
            return [TaskEventOut.model_validate(e) for e in rows]

    def sectors(self, principal: Principal, mission_id: UUID) -> list[SectorOut]:
        """Sector geometry is public mission configuration, recomputed deterministically."""
        from agents.shared.coordination import MissionContext
        from simulation.adapters.coordination import sector_cells
        from simulation.core.engine import Engine

        with self.db.read() as session:
            mission = mission_for(session, principal, mission_id, Permission.MISSION_READ)
            config = MissionConfig.model_validate(mission.config)
        if config.coordination == "independent":
            return []
        scenario = config.scenario()
        engine = Engine(scenario)
        # Built exactly as simulation.adapters.model1.Fleet builds the coordination context.
        context = MissionContext(
            engine.mission_id,
            tuple(engine.drones),
            scenario.width,
            scenario.height,
            frozenset(scenario.terrain.get("restricted", ())),
            scenario.horizon * scenario.tick_ms,
            disaster=scenario.disaster,
            objective=scenario.mission_objective,
            sectors=tuple(scenario.sectors.items()),
        )
        return [
            SectorOut(member=a, cells=[(c.x, c.y) for c in sector_cells(context, a)])
            for a in context.members
        ]

    def coverage(self, principal: Principal, mission_id: UUID) -> dict[str, Any]:
        """Cells reported by agents (command-visible), not simulator-verified coverage."""
        with self.db.read() as session:
            mission = mission_for(session, principal, mission_id, Permission.MISSION_READ)
            config = MissionConfig.model_validate(mission.config)
            scenario = config.scenario()
            now = self._now(session, mission_id)
            rows = session.execute(
                select(m.Observation.x, m.Observation.y, func.max(m.Observation.observed_ms))
                .where(m.Observation.mission_id == mission_id, m.Observation.x.is_not(None))
                .group_by(m.Observation.x, m.Observation.y)
            ).all()
        reported = [
            {
                "cell": [int(cast(float, x)), int(cast(float, y))],
                "last_reported_ms": int(t),
                "stale": now - int(t) >= FRESHNESS_MS,
            }
            for x, y, t in rows
        ]
        total = scenario.width * scenario.height
        return {
            "crs": m.LOCAL_CRS,
            "units": "cell",
            "width": scenario.width,
            "height": scenario.height,
            "sim_time_ms": now,
            "reported_cells": reported,
            "reported_fraction": len(reported) / total,
            "unknown_cells": total - len(reported),
            "note": "Reported by agents; not verified coverage.",
        }

    def coordination_conflicts(
        self, principal: Principal, mission_id: UUID
    ) -> list[dict[str, Any]]:
        with self.db.read() as session:
            mission_for(session, principal, mission_id, Permission.MISSION_READ)
            snap = session.scalar(
                select(m.MissionSnapshot)
                .where(
                    m.MissionSnapshot.mission_id == mission_id,
                    m.MissionSnapshot.kind == "coordination",
                )
                .order_by(m.MissionSnapshot.sim_time_ms.desc(), m.MissionSnapshot.created_at.desc())
            )
            conflicts = list(snap.payload.get("conflicts", [])) if snap else []
            tasks = session.scalars(select(m.Task).where(m.Task.mission_id == mission_id)).all()
            now = self._now(session, mission_id)
        result = [
            {"source": "coordinator", "sim_time_ms": c[0], "message_id": c[1], "reason": c[2]}
            for c in conflicts
        ]
        result += [
            {
                "source": "task_state",
                "task_id": str(t.id),
                "reason": "agent report disagrees with coordinator state",
                "coordinator_state": t.coordinator_state,
                "reported_status": t.reported_status,
            }
            for t in tasks
            if self.task_out(t, now).knowledge == "conflicting"
        ]
        return result

    # ----- environment and map -------------------------------------------------------------
    def hazards(self, principal: Principal, mission_id: UUID) -> list[HazardOut]:
        with self.db.read() as session:
            mission_for(session, principal, mission_id, Permission.MISSION_READ)
            now = self._now(session, mission_id)
            rows = session.scalars(
                select(m.Hazard)
                .where(m.Hazard.mission_id == mission_id)
                .order_by(m.Hazard.first_reported_ms)
            )
            return [self.hazard_out(h, now) for h in rows]

    @staticmethod
    def hazard_out(h: m.Hazard, now: int) -> HazardOut:
        return HazardOut(
            id=h.id,
            label=h.label,
            location=location(h),
            first_reported_ms=h.first_reported_ms,
            last_reported_ms=h.last_reported_ms,
            report_count=h.report_count,
            reporters=list(h.reporters),
            stale=now - h.last_reported_ms >= FRESHNESS_MS,
        )

    def hazard(self, principal: Principal, hazard_id: UUID) -> HazardOut:
        with self.db.read() as session:
            h = owned(session, principal, m.Hazard, hazard_id)
            return self.hazard_out(h, self._now(session, h.mission_id))

    def environment(self, principal: Principal, mission_id: UUID) -> dict[str, Any]:
        with self.db.read() as session:
            mission_for(session, principal, mission_id, Permission.MISSION_READ)
            snap = session.scalar(
                select(m.MissionSnapshot)
                .where(
                    m.MissionSnapshot.mission_id == mission_id,
                    m.MissionSnapshot.kind == "model2_read_model",
                )
                .order_by(m.MissionSnapshot.sim_time_ms.desc(), m.MissionSnapshot.created_at.desc())
            )
            world = snap.payload.get("world", []) if snap else []
            return {
                "crs": m.LOCAL_CRS,
                "units": "cell",
                "snapshot_sim_ms": snap.sim_time_ms if snap else None,
                "source": "Model 2 global world model (latest checkpointed read model)",
                "cells": world,
                "hazards": [h.model_dump(mode="json") for h in self.hazards(principal, mission_id)],
            }

    def map(
        self, principal: Principal, mission_id: UUID, layers: set[str] | None = None
    ) -> MapResponse:
        with self.db.read() as session:
            mission = mission_for(session, principal, mission_id, Permission.MISSION_READ)
            config = MissionConfig.model_validate(mission.config)
            scenario = config.scenario()
            now = self._now(session, mission_id)
            agents = session.scalars(select(m.Agent).where(m.Agent.mission_id == mission_id)).all()
            incidents = session.scalars(
                select(m.Incident).where(m.Incident.mission_id == mission_id)
            ).all()
            hazards = session.scalars(
                select(m.Hazard).where(m.Hazard.mission_id == mission_id)
            ).all()
            sightings = session.scalars(
                select(m.Observation).where(
                    m.Observation.mission_id == mission_id,
                    m.Observation.kind == "possible_human",
                    m.Observation.outcome == "admitted",
                )
            ).all()
        built: list[MapLayer] = [
            MapLayer(
                name="agents",
                description="Last reported agent positions (agent health reports)",
                features=[
                    MapFeature(
                        id=a.agent_key,
                        layer="agents",
                        location=location(a, scenario.scenario_id),
                        properties={
                            "communication": a.communication,
                            "availability": a.availability,
                            "last_location_ms": a.last_location_ms,
                            "stale": a.last_location_ms is None
                            or now - a.last_location_ms >= FRESHNESS_MS,
                        },
                    )
                    for a in agents
                ],
            ),
            MapLayer(
                name="incidents",
                description="Model 2 incidents at the first reported cell",
                features=[
                    MapFeature(
                        id=str(i.id),
                        layer="incidents",
                        location=location(i, scenario.scenario_id),
                        properties={
                            "category": i.category,
                            "disposition": i.disposition,
                            "priority": i.priority_level,
                        },
                    )
                    for i in incidents
                ],
            ),
            MapLayer(
                name="hazards",
                description="Reported environmental hazards",
                features=[
                    MapFeature(
                        id=str(h.id),
                        layer="hazards",
                        location=location(h, scenario.scenario_id),
                        properties={
                            "label": h.label,
                            "reports": h.report_count,
                            "stale": now - h.last_reported_ms >= FRESHNESS_MS,
                        },
                    )
                    for h in hazards
                ],
            ),
            MapLayer(
                name="stale_observations",
                description="Admitted sightings older than the freshness window",
                features=[
                    MapFeature(
                        id=str(o.id),
                        layer="stale_observations",
                        location=location(o, o.map_ref),
                        properties={"observed_ms": o.observed_ms, "reporter": o.reporter},
                    )
                    for o in sightings
                    if now - o.observed_ms >= FRESHNESS_MS
                ],
            ),
        ]
        sectors = self.sectors(principal, mission_id)
        built.append(
            MapLayer(
                name="sectors",
                description="Search sector assignment (public configuration)",
                features=[
                    MapFeature(
                        id=s.member, layer="sectors", location=None, properties={"cells": s.cells}
                    )
                    for s in sectors
                ],
            )
        )
        coverage = self.coverage(principal, mission_id)
        built.append(
            MapLayer(
                name="coverage",
                description="Reported cells and unknown area (not verified coverage)",
                features=[
                    MapFeature(
                        id="coverage",
                        layer="coverage",
                        location=None,
                        properties={
                            "reported_cells": coverage["reported_cells"],
                            "unknown_cells": coverage["unknown_cells"],
                        },
                    )
                ],
            )
        )
        if layers:
            built = [layer for layer in built if layer.name in layers]
        return MapResponse(
            crs=m.LOCAL_CRS,
            units="cell",
            width=scenario.width,
            height=scenario.height,
            map_ref=scenario.scenario_id,
            sim_time_ms=now,
            layers=built,
        )

    # ----- events and audit ----------------------------------------------------------------
    def events(
        self,
        principal: Principal,
        mission_id: UUID,
        after_sequence: int,
        event_type: str | None,
        limit: int,
    ) -> list[EventOut]:
        with self.db.read() as session:
            mission_for(session, principal, mission_id, Permission.MISSION_READ)
            query = (
                select(m.DomainEvent)
                .where(
                    m.DomainEvent.mission_id == mission_id, m.DomainEvent.sequence > after_sequence
                )
                .order_by(m.DomainEvent.sequence)
                .limit(limit)
            )
            if event_type:
                query = query.where(m.DomainEvent.event_type == event_type)
            return [EventOut.model_validate(e) for e in session.scalars(query)]

    def audit(
        self,
        principal: Principal,
        mission_id: UUID | None,
        action: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[AuditOut], int]:
        with self.db.read() as session:
            query = select(m.AuditLog).order_by(m.AuditLog.occurred_at.desc())
            if mission_id is not None:
                mission_for(session, principal, mission_id, Permission.AUDIT_READ)
                query = query.where(m.AuditLog.mission_id == mission_id)
            elif not principal.is_admin:
                raise NotFound("audit scope not found")
            if action:
                query = query.where(m.AuditLog.action == action)
            rows, total = paginate(session, query, limit, offset)
            return [AuditOut.model_validate(a) for a in rows], total
