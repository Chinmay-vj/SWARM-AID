"""Persist what Model 1 reported and what Model 2 decided, one transaction per tick.

This adapter only copies validated outputs. Incident assessment, urgency, recommendations and
decision validation stay inside agents.command_agent. Ground truth never enters these tables.
"""

import hashlib
import json
from collections import defaultdict
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.command_agent.agent import Transition
from agents.shared.domain import Category
from agents.shared.domain import Observation as DomainObservation
from backend.database import models as m
from backend.integrations.simulation_adapter import SimulationContext
from backend.services.events import EventType, emit
from communication.messages import (
    AgentHealth,
    CommandAlert,
    Envelope,
    EnvironmentalObservation,
    HazardDetection,
    Heartbeat,
    IncidentUpdate,
    PossibleHumanDetection,
)

SOURCE = "model2"
CELL_UNCERTAINTY = 0.5  # reports are cell-granular: +/- half a grid cell
CATEGORY_RANK = {c.value: i for i, c in enumerate(Category)}
PRIORITY_RANK = {"review_required": 0, "elevated": 1, "potentially_urgent": 2}
OUTCOME_ORDER = (
    "admitted",
    "duplicate",
    "conflict",
    "stale",
    "capacity",
    "invalid_scope",
    "unauthorized",
    "clock_reversal",
)
APPROVAL_STATUS = {"acknowledged": "approved", "confirmed": "confirmed", "rejected": "rejected"}
Detection = EnvironmentalObservation | HazardDetection | PossibleHumanDetection


def digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def finding_kind(payload: Detection) -> tuple[str, str | None]:
    if isinstance(payload, EnvironmentalObservation):
        return "environment", payload.feature
    if isinstance(payload, HazardDetection):
        return "hazard", payload.hazard
    return "possible_human", None


class Model2Sync:
    def __init__(self, ctx: SimulationContext, mission_id: UUID, run_id: UUID) -> None:
        self.ctx = ctx
        self.mission_id = mission_id
        self.run_id = run_id
        self.inbox_cursor = 0
        self.operator_cursor = 0
        self.agents: dict[str, UUID] = {}
        self.observations: dict[UUID, UUID] = {}  # message_id -> observation pk
        self.seen_updates: set[tuple[UUID, int]] = set()
        self.seen_transitions: set[tuple[UUID, int, str, UUID]] = set()
        self.task_history: dict[UUID, int] = {}
        self.task_reported: dict[UUID, str] = {}
        self.agent_health: dict[str, tuple[float, tuple[str, ...], tuple[int, int] | None]] = {}
        self.model2_state = "inactive"
        self.communication_state = "unknown"
        self.ticks = 0

    # ----- helpers -------------------------------------------------------------------------
    def scope(self, model2_id: UUID) -> UUID:
        """Backend resource ID for a Model 2 identifier. Simulator IDs are deterministic per
        scenario and seed, so they repeat across missions and cannot be global keys."""
        return uuid5(self.mission_id, f"model2/{model2_id}")

    def _emit(
        self,
        session: Session,
        kind: EventType,
        resource_type: str,
        resource_id: object,
        payload: dict[str, Any],
    ) -> None:
        emit(
            session,
            self.mission_id,
            kind,
            source=SOURCE,
            resource_type=resource_type,
            resource_id=resource_id,
            payload=payload,
            sim_time_ms=self.ctx.now_ms,
            correlation_id=str(self.run_id),
        )

    def _event_refs(self) -> dict[str, list[str]]:
        refs: dict[str, list[str]] = defaultdict(list)
        for _, kind, ref in self.ctx.command.events:
            if ref:
                refs[ref].append(kind)
        return refs

    # ----- registration --------------------------------------------------------------------
    def register_agents(self, session: Session) -> None:
        for key in self.ctx.engine.drones:
            agent = session.scalar(
                select(m.Agent).where(
                    m.Agent.mission_id == self.mission_id, m.Agent.agent_key == key
                )
            )
            if agent is None:
                agent = m.Agent(mission_id=self.mission_id, agent_key=key)
                session.add(agent)
                session.flush()
                self._emit(
                    session, EventType.AGENT_REGISTERED, "agent", agent.id, {"agent_key": key}
                )
            self.agents[key] = agent.id

    # ----- main entry ----------------------------------------------------------------------
    def sync(self, session: Session) -> None:
        # The session keeps unmodified rows only while something refers to them. Holding the
        # agents for this unit of work stops one query per report that mentions an agent.
        held = session.scalars(select(m.Agent).where(m.Agent.mission_id == self.mission_id)).all()
        refs = self._event_refs()
        self._sync_tasks(session)
        self._sync_inbox(session, refs)
        self._sync_incidents(session)
        self._sync_transitions(session)
        self._resolve_decisions(session, refs)
        self._sync_alerts(session)
        self._sync_runtime(session)
        self.ticks += 1
        del held

    def sync_model2_outputs(self, session: Session) -> None:
        """Persist only what an out-of-band report can change: incidents and transitions."""
        self._sync_incidents(session)
        self._sync_transitions(session)

    # ----- Model 1 reports -----------------------------------------------------------------
    def _sync_inbox(self, session: Session, refs: dict[str, list[str]]) -> None:
        inbox = self.ctx.network.history["command"]
        end = self.ctx.fleet.command_cursor
        for msg in inbox[self.inbox_cursor : end]:
            p = msg.payload
            if isinstance(p, Heartbeat):
                self._agent_status(session, msg, p)
            elif isinstance(p, AgentHealth):
                self._agent_health(session, msg, p)
            elif isinstance(p, (EnvironmentalObservation, HazardDetection, PossibleHumanDetection)):
                kinds = refs.get(str(msg.message_id), [])
                outcome = next((k for k in OUTCOME_ORDER if k in kinds), "not_processed")
                self.persist_observation(session, msg, p, outcome, "simulation", msg.sent_ms)
        self.inbox_cursor = max(self.inbox_cursor, end)

    def _agent(self, session: Session, key: str) -> m.Agent | None:
        pk = self.agents.get(key)
        return session.get(m.Agent, pk) if pk else None

    def _agent_status(self, session: Session, msg: Envelope, p: Heartbeat) -> None:
        agent = self._agent(session, msg.source)
        if agent is None:
            return
        changed = agent.reported_state != p.state.value
        agent.reported_state = p.state.value
        agent.last_report_ms = max(agent.last_report_ms or 0, msg.sent_ms)
        session.add(
            m.AgentReport(
                mission_id=self.mission_id,
                agent_id=agent.id,
                report_type="status",
                sim_time_ms=msg.sent_ms,
                state=p.state.value,
            )
        )
        if changed:
            self._emit(
                session,
                EventType.AGENT_STATUS_UPDATED,
                "agent",
                agent.id,
                {"agent_key": agent.agent_key, "reported_state": p.state.value},
            )

    def _agent_health(self, session: Session, msg: Envelope, p: AgentHealth) -> None:
        agent = self._agent(session, msg.source)
        if agent is None:
            return
        cell = (p.cell.x, p.cell.y) if p.cell else None
        agent.battery_fraction = p.battery_fraction
        agent.degraded_sensors = list(p.degraded_sensors)
        agent.last_report_ms = max(agent.last_report_ms or 0, msg.sent_ms)
        if cell and (agent.last_location_ms or -1) <= msg.sent_ms:
            agent.x, agent.y = float(cell[0]), float(cell[1])
            agent.crs, agent.uncertainty = m.LOCAL_CRS, CELL_UNCERTAINTY
            agent.last_location_ms = msg.sent_ms
        session.add(
            m.AgentReport(
                mission_id=self.mission_id,
                agent_id=agent.id,
                report_type="health",
                sim_time_ms=msg.sent_ms,
                battery_fraction=p.battery_fraction,
                x=float(cell[0]) if cell else None,
                y=float(cell[1]) if cell else None,
                crs=m.LOCAL_CRS if cell else None,
                uncertainty=CELL_UNCERTAINTY if cell else None,
                details={"degraded_sensors": list(p.degraded_sensors)},
            )
        )
        previous = self.agent_health.get(agent.agent_key)
        current = (p.battery_fraction, tuple(p.degraded_sensors), cell)
        self.agent_health[agent.agent_key] = current
        if previous is None or previous[1:] != current[1:] or abs(previous[0] - current[0]) >= 0.05:
            self._emit(
                session,
                EventType.AGENT_HEALTH_UPDATED,
                "agent",
                agent.id,
                {
                    "agent_key": agent.agent_key,
                    "battery_fraction": p.battery_fraction,
                    "degraded_sensors": list(p.degraded_sensors),
                    "reported_cell": list(cell) if cell else None,
                },
            )

    def persist_observation(
        self,
        session: Session,
        msg: Envelope,
        p: Detection,
        outcome: str,
        source: str,
        received_ms: int,
    ) -> m.Observation | None:
        obs: DomainObservation = p.observation
        existing = session.scalar(
            select(m.Observation).where(
                m.Observation.mission_id == self.mission_id,
                m.Observation.observation_id == obs.observation_id,
            )
        )
        if existing is not None:
            self.observations.setdefault(msg.message_id, existing.id)
            return None
        kind, label = finding_kind(p)
        row = m.Observation(
            mission_id=self.mission_id,
            observation_id=obs.observation_id,
            message_id=msg.message_id,
            agent_id=self.agents.get(msg.source),
            reporter=msg.source,
            kind=kind,
            label=label,
            confidence=obs.confidence,
            observed_ms=obs.observed_ms,
            received_ms=received_ms,
            map_ref=self.ctx.scenario.scenario_id,
            outcome=outcome,
            source=source,
            x=float(obs.cell.x) if obs.cell else None,
            y=float(obs.cell.y) if obs.cell else None,
            crs=m.LOCAL_CRS if obs.cell else None,
            uncertainty=CELL_UNCERTAINTY if obs.cell else None,
        )
        session.add(row)
        session.flush()
        for e in obs.evidence:
            session.add(
                m.Evidence(
                    mission_id=self.mission_id,
                    observation_pk=row.id,
                    evidence_id=e.evidence_id,
                    origin=e.origin,
                    captured_ms=e.captured_ms,
                    modality=e.modality,
                    artifact_key=e.artifact_key,
                )
            )
        self.observations[msg.message_id] = row.id
        if outcome == "admitted":
            self._emit(
                session,
                EventType.OBSERVATION_RECEIVED,
                "observation",
                row.id,
                {
                    "observation_id": str(obs.observation_id),
                    "kind": kind,
                    "label": label,
                    "reporter": msg.source,
                    "observed_ms": obs.observed_ms,
                    "cell": [obs.cell.x, obs.cell.y] if obs.cell else None,
                },
            )
            if kind == "hazard" and obs.cell is not None and label:
                self._hazard(session, obs, label, msg.source)
        return row

    def _hazard(self, session: Session, obs: DomainObservation, label: str, reporter: str) -> None:
        assert obs.cell is not None
        hid = uuid5(self.mission_id, f"hazard/{obs.cell.x}/{obs.cell.y}/{label}")
        hazard = session.get(m.Hazard, hid)
        if hazard is None:
            session.add(
                m.Hazard(
                    id=hid,
                    mission_id=self.mission_id,
                    label=label,
                    first_reported_ms=obs.observed_ms,
                    last_reported_ms=obs.observed_ms,
                    report_count=1,
                    reporters=[reporter],
                    x=float(obs.cell.x),
                    y=float(obs.cell.y),
                    crs=m.LOCAL_CRS,
                    uncertainty=CELL_UNCERTAINTY,
                )
            )
            self._emit(
                session,
                EventType.HAZARD_REPORTED,
                "hazard",
                hid,
                {"label": label, "cell": [obs.cell.x, obs.cell.y], "reporter": reporter},
            )
        else:
            hazard.report_count += 1
            hazard.last_reported_ms = max(hazard.last_reported_ms, obs.observed_ms)
            if reporter not in hazard.reporters:
                hazard.reporters = [*hazard.reporters, reporter]

    # ----- Model 2 incidents and recommendations -------------------------------------------
    def _sync_incidents(self, session: Session) -> None:
        for update in list(self.ctx.command.history):
            key = (update.incident.incident_id, update.incident.revision)
            if key in self.seen_updates:
                continue
            self.seen_updates.add(key)
            self.persist_update(session, update)

    def persist_update(self, session: Session, update: IncidentUpdate) -> None:
        inc = update.incident
        iid = self.scope(inc.incident_id)
        command = self.ctx.command
        priority = command.priorities.get(inc.incident_id)
        disposition = command.dispositions.get(inc.incident_id, "reported")
        if session.scalar(
            select(m.IncidentRevision.id).where(
                m.IncidentRevision.incident_id == iid,
                m.IncidentRevision.revision == inc.revision,
            )
        ):
            return
        first_obs = self.observations.get(inc.reports[0])
        located = session.get(m.Observation, first_obs) if first_obs else None
        row = session.get(m.Incident, iid)
        now = self.ctx.now_ms
        if row is None:
            row = m.Incident(
                id=iid,
                mission_id=self.mission_id,
                model2_id=inc.incident_id,
                current_revision=inc.revision,
                category=inc.category.value,
                disposition=disposition,
                opened_sim_ms=now,
                updated_sim_ms=now,
            )
            session.add(row)
            event = EventType.INCIDENT_CREATED
        else:
            escalated = CATEGORY_RANK[inc.category.value] > CATEGORY_RANK.get(row.category, 0) or (
                priority is not None
                and PRIORITY_RANK[priority.level] > PRIORITY_RANK.get(row.priority_level or "", -1)
            )
            event = EventType.INCIDENT_ESCALATED if escalated else EventType.INCIDENT_UPDATED
        if inc.revision >= row.current_revision:
            row.current_revision = inc.revision
            row.category = inc.category.value
            row.disposition = disposition
            row.updated_sim_ms = now
        if priority is not None:
            row.priority_level, row.priority_reason = priority.level, priority.reason
        row.operator_priority = command.operator_priorities.get(inc.incident_id)
        if located is not None and located.x is not None:
            row.x, row.y, row.crs, row.uncertainty = (
                located.x,
                located.y,
                located.crs,
                located.uncertainty,
            )
        session.flush()
        session.add(
            m.IncidentRevision(
                mission_id=self.mission_id,
                incident_id=iid,
                revision=inc.revision,
                category=inc.category.value,
                report_message_ids=[str(r) for r in inc.reports],
                uncertainties=list(inc.uncertainties),
                confirmation_id=inc.confirmation_id,
                priority_level=priority.level if priority else None,
                priority_reason=priority.reason if priority else None,
                sim_time_ms=now,
            )
        )
        linked = set(
            session.scalars(
                select(m.IncidentEvidence.observation_pk).where(
                    m.IncidentEvidence.incident_id == iid
                )
            )
        )
        added = []
        # Model 2 flags a report as conflicting when it contradicts another report for the same
        # cell and observation time. The flag is copied, not inferred, so the evidence group
        # shows the contradiction instead of counting the report as plain support.
        conflicting = {r.message_id for r in self.ctx.command.conflicts}
        for message_id in inc.reports:
            pk = self.observations.get(message_id)
            if pk is not None and pk not in linked:
                linked.add(pk)
                added.append(pk)
                session.add(
                    m.IncidentEvidence(
                        mission_id=self.mission_id,
                        incident_id=iid,
                        observation_pk=pk,
                        first_revision=inc.revision,
                        role="conflicting" if message_id in conflicting else "supporting",
                    )
                )
        summary = {
            "incident_id": str(iid),
            "revision": inc.revision,
            "category": inc.category.value,
            "disposition": disposition,
            "priority": priority.level if priority else None,
            "priority_reason": priority.reason if priority else None,
        }
        self._emit(session, event, "incident", iid, summary)
        if added:
            self._emit(
                session,
                EventType.EVIDENCE_GROUP_UPDATED,
                "incident",
                iid,
                {
                    "incident_id": str(iid),
                    "added_observations": [str(a) for a in added],
                },
            )
        if update.recommendation is not None:
            self._recommendation(session, update)

    def _set_recommendation_status(
        self, session: Session, rec: m.Recommendation, status: str, reason: str
    ) -> None:
        if rec.status == status:
            return
        session.add(
            m.RecommendationStatusHistory(
                mission_id=self.mission_id,
                recommendation_id=rec.id,
                previous=rec.status,
                status=status,
                reason=reason,
                sim_time_ms=self.ctx.now_ms,
            )
        )
        rec.status = status

    def _recommendation(self, session: Session, update: IncidentUpdate) -> None:
        rec = update.recommendation
        assert rec is not None
        rid, iid = self.scope(rec.recommendation_id), self.scope(rec.incident_id)
        if session.get(m.Recommendation, rid) is not None:
            return
        earlier = list(
            session.scalars(select(m.Recommendation).where(m.Recommendation.incident_id == iid))
        )
        for old in earlier:
            if old.status == "pending":
                self._set_recommendation_status(
                    session, old, "superseded", f"superseded by revision {rec.incident_revision}"
                )
        session.add(
            m.Recommendation(
                id=rid,
                mission_id=self.mission_id,
                model2_id=rec.recommendation_id,
                incident_id=iid,
                incident_revision=rec.incident_revision,
                request=rec.request,
                evidence_ids=[str(e) for e in rec.evidence_ids],
                unknowns=list(rec.unknowns),
                expires_ms=rec.expires_ms,
                created_sim_ms=self.ctx.now_ms,
            )
        )
        session.flush()
        payload = {
            "recommendation_id": str(rid),
            "incident_id": str(iid),
            "version": rec.incident_revision,
            "request": rec.request,
            "expires_ms": rec.expires_ms,
        }
        self._emit(
            session,
            EventType.RECOMMENDATION_REVISED if earlier else EventType.RECOMMENDATION_CREATED,
            "recommendation",
            rid,
            payload,
        )
        self._emit(
            session,
            EventType.HUMAN_REVIEW_REQUESTED,
            "recommendation",
            rid,
            payload,
        )

    def _sync_transitions(self, session: Session) -> None:
        for t in list(self.ctx.command.lifecycle):
            key = (t.incident_id, t.revision, t.state, t.reference)
            if key in self.seen_transitions:
                continue
            self.seen_transitions.add(key)
            self.persist_transition(session, t)

    def persist_transition(self, session: Session, t: Transition) -> None:
        iid = self.scope(t.incident_id)
        if session.get(m.Incident, iid) is None:
            return
        session.add(
            m.IncidentTransition(
                mission_id=self.mission_id,
                incident_id=iid,
                revision=t.revision,
                previous=t.previous,
                state=t.state,
                actor=t.actor,
                reference=t.reference,
                sim_time_ms=t.time_ms,
            )
        )
        incident = session.get(m.Incident, iid)
        assert incident is not None
        incident.disposition = self.ctx.command.dispositions.get(t.incident_id, t.state)
        decided_revision = t.revision if t.state == "expired" else t.revision - 1
        rec = session.scalar(
            select(m.Recommendation).where(
                m.Recommendation.incident_id == iid,
                m.Recommendation.incident_revision == decided_revision,
            )
        )
        if rec is None or rec.status != "pending":
            return
        if t.state in APPROVAL_STATUS:
            status = APPROVAL_STATUS[t.state]
            self._set_recommendation_status(
                session, rec, status, f"operator decision {t.reference}"
            )
            self._emit(
                session,
                EventType.RECOMMENDATION_REJECTED
                if status == "rejected"
                else EventType.RECOMMENDATION_APPROVED,
                "recommendation",
                rec.id,
                {"recommendation_id": str(rec.id), "status": status, "decision": str(t.reference)},
            )
        elif t.state == "expired":
            self._set_recommendation_status(session, rec, "expired", "review deadline passed")
        elif t.state == "corrected":
            self._set_recommendation_status(
                session, rec, "revision_requested", f"operator correction {t.reference}"
            )

    # ----- human decisions -----------------------------------------------------------------
    def _resolve_decisions(self, session: Session, refs: dict[str, list[str]]) -> None:
        pending = session.scalars(
            select(m.HumanDecision).where(
                m.HumanDecision.mission_id == self.mission_id,
                m.HumanDecision.status == "submitted",
                m.HumanDecision.message_id.is_not(None),
            )
        )
        for decision in pending:
            kinds = refs.get(str(decision.message_id), [])
            accepted_kind = (
                f"operator_{decision.action}" if decision.kind == "override" else decision.action
            )
            if accepted_kind in kinds:
                status, reason = "accepted", "validated by Model 2"
            else:
                rejected = [
                    k
                    for k in kinds
                    if k.startswith("validation_")
                    or k in ("rejected_amendment", "invalid_override", "invalid_scope")
                ]
                if not rejected:
                    continue
                status, reason = "rejected", rejected[0]
            self.resolve(session, decision, status, reason)

    def resolve(
        self, session: Session, decision: m.HumanDecision, status: str, reason: str
    ) -> None:
        from datetime import UTC, datetime

        decision.status, decision.outcome_reason = status, reason
        decision.resolved_at = datetime.now(UTC)
        payload = {
            "decision_id": str(decision.id),
            "kind": decision.kind,
            "action": decision.action,
            "status": status,
            "reason": reason,
            "incident_id": str(decision.incident_id) if decision.incident_id else None,
            "recommendation_id": str(decision.recommendation_id)
            if decision.recommendation_id
            else None,
        }
        self._emit(
            session, EventType.HUMAN_DECISION_RESOLVED, "human_decision", decision.id, payload
        )
        if decision.kind == "override" and status == "accepted":
            self._emit(
                session, EventType.HUMAN_OVERRIDE_RECORDED, "human_decision", decision.id, payload
            )

    # ----- operator alerts -----------------------------------------------------------------
    def _sync_alerts(self, session: Session) -> None:
        outbox = self.ctx.network.history["operator"]
        for msg in outbox[self.operator_cursor :]:
            p = msg.payload
            if not isinstance(p, CommandAlert):
                continue
            inc = p.update.incident
            if session.get(m.Incident, self.scope(inc.incident_id)) is None:
                self.persist_update(session, p.update)
            aid = self.scope(msg.message_id)
            if session.get(m.Alert, aid) is not None:
                continue
            session.add(
                m.Alert(
                    id=aid,
                    mission_id=self.mission_id,
                    message_id=msg.message_id,
                    incident_id=self.scope(inc.incident_id),
                    incident_revision=inc.revision,
                    priority=p.priority,
                    priority_reason=p.priority_reason,
                    review_state=p.review_state,
                    supporting_evidence=[str(e) for e in p.supporting_evidence],
                    sent_sim_ms=msg.sent_ms,
                )
            )
            self._emit(
                session,
                EventType.ALERT_RAISED,
                "alert",
                aid,
                {
                    "alert_id": str(aid),
                    "incident_id": str(self.scope(inc.incident_id)),
                    "revision": inc.revision,
                    "priority": p.priority,
                    "priority_reason": p.priority_reason,
                    "review_state": p.review_state,
                },
            )
        self.operator_cursor = len(outbox)

    # ----- Phase 5 coordination ------------------------------------------------------------
    def _sync_tasks(self, session: Session) -> None:
        fixture = self.ctx.fleet.assignments
        reported = {tid: status for tid, (_, _, status) in self.ctx.command.tasks.items()}
        if fixture is None:
            return
        for task in fixture.tasks.values():
            status = reported.get(task.task_id)
            # Only this adapter writes task rows and histories only grow, so a stored task with
            # no new history or report needs no query. Both caches roll back with a failed tick.
            if len(task.history) == self.task_history.get(task.task_id) and (
                not status or self.task_reported.get(task.task_id) == status
            ):
                continue
            tid = self.scope(task.task_id)
            row = session.get(m.Task, tid)
            last = task.history[-1]
            if row is None:
                row = m.Task(
                    id=tid,
                    mission_id=self.mission_id,
                    model2_id=task.task_id,
                    member=task.member,
                    target_x=task.target.x,
                    target_y=task.target.y,
                    category=task.category,
                    coordinator_state=last.state,
                    created_ms=task.created_ms,
                    expires_ms=task.expires_ms,
                    updated_ms=last.time_ms,
                )
                session.add(row)
                session.flush()
            seen = self.task_history.get(task.task_id, 0)
            changed = seen < len(task.history)
            for ordinal, event in enumerate(task.history[seen:], start=seen):
                session.add(
                    m.TaskEvent(
                        mission_id=self.mission_id,
                        task_id=tid,
                        ordinal=ordinal,
                        sim_time_ms=event.time_ms,
                        state=event.state,
                        reason=event.reason,
                        source="coordinator",
                    )
                )
            self.task_history[task.task_id] = len(task.history)
            row.coordinator_state, row.updated_ms = last.state, last.time_ms
            if status and self.task_reported.get(task.task_id) != status:
                self.task_reported[task.task_id] = status
                row.reported_status, row.reported_ms = status, self.ctx.now_ms
                changed = True
            if changed:
                self._emit(
                    session,
                    EventType.TASK_UPDATED,
                    "task",
                    tid,
                    {
                        "task_id": str(tid),
                        "member": task.member,
                        "coordinator_state": last.state,
                        "reported_status": row.reported_status,
                        "target": [task.target.x, task.target.y],
                    },
                )

    # ----- runtime health ------------------------------------------------------------------
    def communication_snapshot(self) -> dict[str, Any]:
        router = self.ctx.network.router
        endpoints = {n: e.state.value for n, e in router.endpoints.items()}
        disconnected = sorted(n for n, s in endpoints.items() if s != "connected")
        return {"endpoints": endpoints, "disconnected": disconnected}

    def _sync_runtime(self, session: Session) -> None:
        runtime = session.get(m.MissionRuntime, self.mission_id)
        assert runtime is not None
        runtime.last_sim_ms = self.ctx.now_ms
        comm = self.communication_snapshot()
        for key, pk in self.agents.items():
            agent = session.get(m.Agent, pk)
            if agent is not None:
                agent.communication = (
                    "connected" if self.ctx.network.connected(key) else "disconnected"
                )
        fixture = self.ctx.fleet.assignments
        if fixture is not None:
            for key, availability in fixture.availability.items():
                agent = self._agent(session, key)
                if agent is not None:
                    agent.availability = availability
        state = self.ctx.command.state
        model2 = (
            "available" if state == "active" else "ended" if state == "ended" else "unavailable"
        )
        if model2 != self.model2_state:
            if model2 == "unavailable":
                self._emit(
                    session,
                    EventType.MODEL_2_UNAVAILABLE,
                    "mission",
                    self.mission_id,
                    {"state": state},
                )
            elif model2 == "available" and self.model2_state == "unavailable":
                self._emit(
                    session,
                    EventType.MODEL_2_RECOVERED,
                    "mission",
                    self.mission_id,
                    {"state": state},
                )
            self.model2_state = model2
        runtime.model2_state = model2
        communication = "degraded" if comm["disconnected"] else "nominal"
        if communication != self.communication_state:
            if communication == "degraded":
                self._emit(
                    session, EventType.COMMUNICATION_DEGRADED, "mission", self.mission_id, comm
                )
            elif self.communication_state == "degraded":
                self._emit(
                    session, EventType.COMMUNICATION_RESTORED, "mission", self.mission_id, comm
                )
            self.communication_state = communication
        runtime.communication_state = communication
        if self.ticks % 10 == 0 or self.ctx.finished:
            self._emit(
                session,
                EventType.METRICS_UPDATED,
                "mission",
                self.mission_id,
                self.operational_metrics(),
            )

    def operational_metrics(self) -> dict[str, Any]:
        """Command-visible metrics only. No simulator ground truth."""
        router = self.ctx.network.router.metrics()
        fixture = self.ctx.fleet.assignments
        return {
            "sim_time_ms": self.ctx.now_ms,
            "model2_counts": dict(self.ctx.command.counts),
            "incidents": len(self.ctx.command.incidents),
            "admitted_findings": len(self.ctx.command.findings),
            "communication": {
                k: router[k]
                for k in (
                    "generated",
                    "delivered",
                    "dropped",
                    "expired",
                    "pending",
                    "delivery_ratio",
                )
                if k in router
            },
            "tasks_issued": fixture.issued if fixture else 0,
            "reported_cells": len(fixture.reported) if fixture else 0,
        }

    # ----- persistent Model 2 memory -------------------------------------------------------
    def checkpoint(self, session: Session) -> m.MissionSnapshot | None:
        """Store a Model 2 checkpoint (replay journal) and its read model, with digests."""
        command = self.ctx.command
        with self.ctx.lock:
            read_model = command.snapshot()
            try:
                checkpoint = command.checkpoint().model_dump(mode="json")
                complete = True
            except ValueError:
                checkpoint, complete = {"error": "journal retention exceeded"}, False
        snapshot = None
        for kind, payload in (("model2_checkpoint", checkpoint), ("model2_read_model", read_model)):
            snapshot_row = m.MissionSnapshot(
                mission_id=self.mission_id,
                run_id=self.run_id,
                kind=kind,
                schema_version="1",
                sim_time_ms=self.ctx.now_ms,
                payload=json.loads(json.dumps(payload, default=str)),
                sha256=digest(payload),
                complete=complete,
            )
            session.add(snapshot_row)
            if kind == "model2_checkpoint":
                snapshot = snapshot_row
        if self.ctx.fleet.assignments is not None:
            coordination = self.ctx.fleet.assignments.command_snapshot()
            session.add(
                m.MissionSnapshot(
                    mission_id=self.mission_id,
                    run_id=self.run_id,
                    kind="coordination",
                    schema_version="1",
                    sim_time_ms=self.ctx.now_ms,
                    payload=coordination,
                    sha256=digest(coordination),
                )
            )
        return snapshot
