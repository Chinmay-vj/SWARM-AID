"""Deterministic command-side review of authenticated synthetic reports."""

from collections import Counter, deque
from collections.abc import MutableMapping
from typing import Literal, Protocol
from uuid import UUID, uuid5

from pydantic import PositiveInt

from agents.command_agent.validation import validate_decision
from agents.shared.domain import (
    Category,
    Cell,
    Evidence,
    Finding,
    Incident,
    Recommendation,
    Record,
    ReportedFinding,
)
from communication.messages import (
    AgentHealth,
    Envelope,
    EnvironmentalObservation,
    EvidenceReference,
    ForwardedReport,
    HazardDetection,
    Heartbeat,
    HumanApproval,
    HumanIncidentReview,
    IncidentUpdate,
    PossibleHumanDetection,
    TaskStatus,
)
from interfaces.providers import IncidentAssessmentProvider, RescueRecommendationProvider

Mode = Literal["direct", "rules", "fusion"]


class Settings(Record):
    mode: Mode = "fusion"
    freshness_ms: PositiveInt = 1500
    review_ms: PositiveInt = 1200
    capacity: PositiveInt = 4096
    source_threshold: PositiveInt = 2


class Transition(Record):
    incident_id: UUID
    revision: int
    previous: str
    state: Literal[
        "human_review_pending",
        "acknowledged",
        "confirmed",
        "rejected",
        "expired",
        "corrected",
        "prioritized",
        "resolution_reported",
        "closed",
    ]
    time_ms: int
    actor: str
    reference: UUID


class Entry(Record):
    received_ms: int
    principal: str
    envelope: Envelope


class Checkpoint(Record):
    version: Literal["1"] = "1"
    mission: UUID
    members: tuple[str, ...]
    settings: Settings
    entries: tuple[Entry, ...]
    state: str
    last_tick: int
    transitions: tuple[Transition, ...]
    dispositions: dict[UUID, str]
    counts: dict[str, int]
    events: tuple[tuple[int, str, str], ...]


class Priority(Record):
    level: Literal["review_required", "elevated", "potentially_urgent"]
    reason: str
    evidence: tuple[UUID, ...]


class UrgencyAssessmentProvider(Protocol):
    def assess_priority(self, report: Finding, context: tuple[Finding, ...]) -> Priority: ...


class ContextPriority:
    def assess_priority(self, report: Finding, context: tuple[Finding, ...]) -> Priority:
        hazards = [f for f in context if f.kind == "hazard"]
        human = any(f.kind == "possible_human" for f in context)
        return Priority(
            level="potentially_urgent"
            if hazards and human
            else "elevated"
            if human
            else "review_required",
            reason="Recent sighting and hazard reported at the same cell"
            if hazards and human
            else "Possible human presence requires verification"
            if human
            else "Environmental hazard requires review",
            evidence=tuple(
                dict.fromkeys(
                    e.evidence_id for f in (report, *hazards) for e in f.observation.evidence
                )
            ),
        )


class Rules:
    def __init__(self, mission: UUID, settings: Settings):
        self.mission = mission
        self.settings = settings

    def assess(self, previous: Incident | None, reports: tuple[ReportedFinding, ...]) -> Incident:
        first = reports[0].finding
        origins = {e.origin for r in reports for e in r.finding.observation.evidence}
        category = Category.HAZARD if first.kind == "hazard" else Category.POSSIBLE
        if first.kind == "possible_human" and len(origins) >= self.settings.source_threshold:
            category = Category.UNCERTAIN
        return Incident(
            incident_id=previous.incident_id
            if previous
            else uuid5(self.mission, str(first.observation.observation_id)),
            revision=previous.revision + 1 if previous else 1,
            category=category,
            reports=tuple(r.message_id for r in reports),
            uncertainties=("synthetic report; human verification required",),
        )


class Review:
    def __init__(self, settings: Settings):
        self.settings = settings

    def recommend(self, incident: Incident, reports: tuple[ReportedFinding, ...]) -> Recommendation:
        refs = tuple(
            dict.fromkeys(e.evidence_id for r in reports for e in r.finding.observation.evidence)
        )
        return Recommendation(
            recommendation_id=uuid5(incident.incident_id, str(incident.revision)),
            incident_id=incident.incident_id,
            incident_revision=incident.revision,
            request="review_rescue_need"
            if incident.category == Category.UNCERTAIN
            else "inspect_evidence",
            evidence_ids=refs,
            unknowns=incident.uncertainties,
            expires_ms=max(r.finding.observation.observed_ms for r in reports)
            + self.settings.review_ms,
        )


class CommandAgent:
    def __init__(
        self,
        mission: UUID,
        members: frozenset[str],
        settings: Settings,
        assessment: IncidentAssessmentProvider | None = None,
        review: RescueRecommendationProvider | None = None,
        urgency: UrgencyAssessmentProvider | None = None,
        memory: MutableMapping[UUID, ReportedFinding] | None = None,
    ):
        self.mission, self.members, self.settings = mission, members, settings
        self.assessment = assessment or Rules(mission, settings)
        self.review = review or Review(settings)
        if memory:
            raise ValueError("restore existing memory from a mission-scoped checkpoint")
        self.findings: MutableMapping[UUID, ReportedFinding] = memory if memory is not None else {}
        self.tasks: dict[UUID, tuple[int, str, str]] = {}
        self.evidence_refs: dict[UUID, Evidence] = {}
        self.source_status: dict[str, tuple[int, str]] = {}
        self.incidents: dict[UUID, IncidentUpdate] = {}
        self.groups: dict[tuple[object, ...], UUID] = {}
        self.decisions: dict[UUID, HumanApproval] = {}
        self.dispositions: dict[UUID, str] = {}
        self.lifecycle: deque[Transition] = deque(maxlen=settings.capacity)
        self.operator_priorities: dict[UUID, str] = {}
        self.history: deque[IncidentUpdate] = deque(maxlen=settings.capacity)
        self.events: deque[tuple[int, str, str]] = deque(maxlen=settings.capacity)
        self.health: dict[str, int] = {}
        self.counts: Counter[str] = Counter()
        self.urgency = urgency or ContextPriority()
        self.priorities: dict[UUID, Priority] = {}
        self.world: dict[Cell, dict[str, tuple[int, str]]] = {}
        self.conflicts: deque[ReportedFinding] = deque(maxlen=settings.capacity)
        # Corroborating reports held back so a pending review keeps a stable revision.
        self.held: dict[UUID, tuple[ReportedFinding, ...]] = {}
        self.last_tick = 0
        self.state = "active"
        self.journal: deque[Entry] = deque(maxlen=settings.capacity)
        self.journal_complete = True

    def event(self, now: int, kind: str, ref: UUID | None = None) -> None:
        self.counts[kind] += 1
        self.events.append((now, kind, str(ref) if ref else ""))

    def record_transition(
        self,
        update: IncidentUpdate,
        state: Literal[
            "human_review_pending",
            "acknowledged",
            "confirmed",
            "rejected",
            "expired",
            "corrected",
            "prioritized",
            "resolution_reported",
            "closed",
        ],
        now: int,
        actor: str,
        reference: UUID,
    ) -> None:
        iid = update.incident.incident_id
        previous = self.dispositions.get(iid, "reported")
        if (
            state in {"acknowledged", "confirmed", "rejected", "expired"}
            and previous != "human_review_pending"
        ):
            raise ValueError("invalid incident transition")
        self.dispositions[iid] = state
        self.lifecycle.append(
            Transition(
                incident_id=iid,
                revision=update.incident.revision,
                previous=previous,
                state=state,
                time_ms=now,
                actor=actor,
                reference=reference,
            )
        )

    def expire(self, now: int) -> None:
        for iid, update in self.incidents.items():
            rec = update.recommendation
            if rec and self.dispositions[iid] == "human_review_pending" and now >= rec.expires_ms:
                self.record_transition(update, "expired", now, "command", rec.recommendation_id)
                self.event(now, "expired", rec.recommendation_id)

    def consume(
        self, msg: Envelope, principal: str, now: int
    ) -> IncidentUpdate | ForwardedReport | None:
        if now < self.last_tick:
            self.event(self.last_tick, "clock_reversal", msg.message_id)
            return None
        self.last_tick = now
        p = msg.payload
        if (
            msg.source != principal
            or msg.mission_id != self.mission
            or msg.destination != "command"
            or msg.sent_ms > now
            or (msg.expires_ms is not None and now >= msg.expires_ms)
        ):
            self.event(now, "invalid_scope", msg.message_id)
            return None
        if isinstance(
            p,
            (
                HumanApproval,
                HumanIncidentReview,
                AgentHealth,
                EvidenceReference,
                TaskStatus,
                Heartbeat,
                EnvironmentalObservation,
                HazardDetection,
                PossibleHumanDetection,
            ),
        ):
            if len(self.journal) == self.settings.capacity:
                self.journal_complete = False
            self.journal.append(Entry(received_ms=now, principal=principal, envelope=msg))
        if isinstance(p, HumanIncidentReview):
            current = self.incidents.get(p.incident_id)
            if (
                principal != "operator"
                or not current
                or current.incident.revision != p.revision
                or self.dispositions[p.incident_id] == "closed"
                or (
                    p.action == "close"
                    and self.dispositions[p.incident_id] != "resolution_reported"
                )
            ):
                self.event(now, "rejected_amendment", msg.message_id)
                return None
            revised = current.incident.model_copy(
                update={
                    "revision": p.revision + 1,
                    "uncertainties": (*current.incident.uncertainties, p.reason),
                }
            )
            update = IncidentUpdate(message_type="incident_update", incident=revised)
            self.record_transition(
                update,
                "corrected"
                if p.action == "correct"
                else "prioritized"
                if p.action == "prioritize"
                else "resolution_reported"
                if p.action == "resolve"
                else "closed",
                now,
                principal,
                msg.message_id,
            )
            self.incidents[p.incident_id] = update
            self.history.append(update)
            if p.action == "prioritize":
                self.operator_priorities[p.incident_id] = p.reason
            self.event(now, p.action, msg.message_id)
            return update
        if isinstance(p, HumanApproval):
            current = self.incidents.get(p.incident_id)
            rec = current.recommendation if current else None
            outcome = validate_decision(
                principal, p, current, now, p.recommendation_id in self.decisions
            )
            if outcome != "approved" or current is None or rec is None:
                self.event(now, "validation_" + outcome, msg.message_id)
                self.event(now, "rejected_decision", msg.message_id)
                return None
            self.decisions[rec.recommendation_id] = p
            incident = current.incident.model_copy(update={"revision": p.revision + 1})
            if p.decision == "confirm_rescue_need":
                incident = incident.model_copy(
                    update={"category": Category.CONFIRMED, "confirmation_id": msg.message_id}
                )
            update = IncidentUpdate(message_type="incident_update", incident=incident)
            self.incidents[p.incident_id] = update
            self.record_transition(
                update,
                "rejected"
                if p.decision == "reject"
                else "confirmed"
                if p.decision == "confirm_rescue_need"
                else "acknowledged",
                now,
                principal,
                msg.message_id,
            )
            self.history.append(update)
            self.event(now, p.decision, msg.message_id)
            return update
        if principal not in self.members:
            self.event(now, "unauthorized", msg.message_id)
            return None
        if isinstance(p, TaskStatus) and (
            p.task_id in self.tasks or len(self.tasks) < self.settings.capacity
        ):
            old = self.tasks.get(p.task_id)
            if old is None or (old[1] == principal and old[0] <= msg.sent_ms):
                self.tasks[p.task_id] = (msg.sent_ms, principal, p.status)
            else:
                self.event(now, "task_conflict", msg.message_id)
        if isinstance(p, EvidenceReference) and len(self.evidence_refs) < self.settings.capacity:
            self.evidence_refs.setdefault(p.evidence.evidence_id, p.evidence)
        if (
            isinstance(p, Heartbeat)
            and msg.sent_ms >= self.source_status.get(principal, (-1, ""))[0]
        ):
            self.source_status[principal] = (msg.sent_ms, p.state)
        if isinstance(p, AgentHealth):
            self.health[principal] = max(self.health.get(principal, -1), msg.sent_ms)
        if not isinstance(p, (EnvironmentalObservation, HazardDetection, PossibleHumanDetection)):
            return None
        obs = p.observation
        finding = Finding(
            observation=obs,
            kind="environment"
            if isinstance(p, EnvironmentalObservation)
            else "hazard"
            if isinstance(p, HazardDetection)
            else "possible_human",
            label=p.feature
            if isinstance(p, EnvironmentalObservation)
            else p.hazard
            if isinstance(p, HazardDetection)
            else None,
        )
        prior = self.findings.get(obs.observation_id)
        if prior:
            if prior.finding != finding:
                self.conflicts.append(ReportedFinding(message_id=msg.message_id, finding=finding))
            self.event(now, "duplicate" if prior.finding == finding else "conflict", msg.message_id)
            return None
        if obs.observed_ms > now or now - obs.observed_ms >= self.settings.freshness_ms:
            self.event(now, "stale", msg.message_id)
            return None
        if len(self.findings) >= self.settings.capacity:
            self.event(now, "capacity", msg.message_id)
            return None
        report = ReportedFinding(message_id=msg.message_id, finding=finding)
        self.findings[obs.observation_id] = report
        self.event(now, "admitted", msg.message_id)
        if obs.cell is not None:
            layer = self.world.setdefault(obs.cell, {})
            label = finding.label or finding.kind
            earlier = layer.get(finding.kind)
            if earlier and earlier[0] == obs.observed_ms and earlier[1] != label:
                self.event(now, "conflict", msg.message_id)
                self.conflicts.append(report)
            elif earlier is None or earlier[0] <= obs.observed_ms:
                layer[finding.kind] = (obs.observed_ms, label)
        if self.settings.mode == "direct":
            self.event(now, "forwarded", msg.message_id)
            return ForwardedReport(
                message_type="forwarded_report", reporter=principal, report=report
            )
        if finding.kind == "environment":
            return None
        key: tuple[object, ...] = (
            finding.kind,
            finding.label,
            obs.cell if obs.cell is not None else obs.observation_id,
        )
        if self.settings.mode != "fusion":
            key += (obs.observation_id,)
        previous = self.incidents.get(self.groups[key]) if key in self.groups else None
        by_id = {r.message_id: r for r in self.findings.values()}
        held = self.held.get(previous.incident.incident_id, ()) if previous else ()
        reports = (
            tuple(
                r
                for r in (*(by_id[i] for i in previous.incident.reports), *held)
                if now - r.finding.observation.observed_ms < self.settings.freshness_ms
            )
            if previous
            else ()
        )
        if previous and self.dispositions[previous.incident.incident_id] == "closed":
            self.held.pop(previous.incident.incident_id, None)
            previous = None
            reports = ()
        if not reports:
            if previous:
                self.held.pop(previous.incident.incident_id, None)
            previous = None
        reports += (report,)
        try:
            incident = self.assessment.assess(previous.incident if previous else None, reports)
            if (
                incident.category == Category.CONFIRMED
                or incident.reports != tuple(r.message_id for r in reports)
                or (previous and incident.incident_id != previous.incident.incident_id)
                or incident.revision != (previous.incident.revision + 1 if previous else 1)
                or (not previous and incident.incident_id in self.incidents)
            ):
                raise ValueError("unsupported incident")
            if previous and previous.incident.category == Category.CONFIRMED:
                incident = incident.model_copy(
                    update={
                        "category": Category.CONFIRMED,
                        "confirmation_id": previous.incident.confirmation_id,
                    }
                )
            rec = self.review.recommend(incident, reports)
            supported = {e.evidence_id for r in reports for e in r.finding.observation.evidence}
            if not isinstance(rec, Recommendation) or (
                rec.incident_id != incident.incident_id
                or rec.incident_revision != incident.revision
                or not set(rec.evidence_ids) <= supported
                or rec.expires_ms > now + self.settings.review_ms
                or rec.expires_ms <= now
            ):
                raise ValueError("unsupported recommendation")
            context = tuple(
                r.finding
                for r in self.findings.values()
                if obs.cell is not None
                and r.finding.observation.cell == obs.cell
                and now - r.finding.observation.observed_ms < self.settings.freshness_ms
            )
            priority = self.urgency.assess_priority(finding, context or (finding,))
            if not priority.evidence or not set(priority.evidence) <= {
                e.evidence_id for f in (finding, *context) for e in f.observation.evidence
            }:
                raise ValueError("unsupported urgency")
            update = IncidentUpdate(
                message_type="incident_update", incident=incident, recommendation=rec
            )
        except Exception:  # noqa: BLE001 - isolate injected provider failures
            self.event(now, "assessment_rejected", msg.message_id)
            return None
        pending = previous.recommendation if previous else None
        if (
            previous
            and pending
            and self.dispositions[previous.incident.incident_id] == "human_review_pending"
            and now < pending.expires_ms
            and incident.category == previous.incident.category
            and priority.level == self.priorities[previous.incident.incident_id].level
        ):
            # Corroboration only: keep the revision under review so the operator's
            # decision is not superseded in flight. Fold in after decision or expiry.
            self.held[incident.incident_id] = (*held, report)
            self.event(now, "corroborated", msg.message_id)
            return None
        self.held.pop(incident.incident_id, None)
        self.priorities[incident.incident_id] = priority
        self.groups[key] = incident.incident_id
        self.incidents[incident.incident_id] = update
        self.record_transition(update, "human_review_pending", now, "command", msg.message_id)
        self.history.append(update)
        self.event(now, "revised" if previous else "incident_opened", incident.incident_id)
        return update

    def checkpoint(self) -> Checkpoint:
        if not self.journal_complete:
            raise ValueError("journal retention exceeded; full restore unavailable")
        return Checkpoint(
            mission=self.mission,
            members=tuple(sorted(self.members)),
            settings=self.settings,
            entries=tuple(self.journal),
            last_tick=self.last_tick,
            transitions=tuple(self.lifecycle),
            dispositions=dict(self.dispositions),
            state=self.state,
            counts=dict(self.counts),
            events=tuple(self.events),
        )

    @classmethod
    def restore(
        cls,
        checkpoint: Checkpoint,
        mission: UUID,
        members: frozenset[str],
        *,
        assessment: IncidentAssessmentProvider | None = None,
        review: RescueRecommendationProvider | None = None,
        urgency: UrgencyAssessmentProvider | None = None,
    ) -> "CommandAgent":
        if checkpoint.mission != mission or frozenset(checkpoint.members) != members:
            raise ValueError("checkpoint scope mismatch")
        agent = cls(mission, members, checkpoint.settings, assessment, review, urgency)
        for entry in checkpoint.entries:
            agent.consume(entry.envelope, entry.principal, entry.received_ms)
        agent.lifecycle = deque(checkpoint.transitions, maxlen=agent.settings.capacity)
        agent.dispositions = dict(checkpoint.dispositions)
        agent.last_tick = checkpoint.last_tick
        agent.state = checkpoint.state
        agent.counts = Counter(checkpoint.counts)
        agent.events = deque(checkpoint.events, maxlen=agent.settings.capacity)
        return agent

    def snapshot(self) -> dict[str, object]:
        return {
            "schema_version": "1",
            "mission": str(self.mission),
            "last_message_ms": self.last_tick,
            "review_queue": [
                {
                    "incident_id": str(iid),
                    "revision": update.incident.revision,
                    "priority": self.priorities[iid].model_dump(mode="json"),
                    "state": self.dispositions[iid],
                    "recommendation": update.recommendation.model_dump(mode="json"),
                }
                for iid, update in self.incidents.items()
                if update.recommendation
                and self.dispositions[iid] == "human_review_pending"
                and update.recommendation.expires_ms > self.last_tick
            ],
            "state": self.state,
            "world": [
                {"cell": c.model_dump(), "observations": dict(layer)}
                for c, layer in self.world.items()
            ],
            "operator_priorities": {
                str(k): reason for k, reason in self.operator_priorities.items()
            },
            "priorities": {str(k): v.model_dump(mode="json") for k, v in self.priorities.items()},
            "conflicting_reports": [r.model_dump(mode="json") for r in self.conflicts],
            "held_reports": {str(k): [str(r.message_id) for r in v] for k, v in self.held.items()},
            "lifecycle": [t.model_dump(mode="json") for t in self.lifecycle],
            "dispositions": {str(k): v for k, v in self.dispositions.items()},
            "counts": dict(self.counts),
            "health_ms": dict(self.health),
            "agent_status": dict(self.source_status),
            "task_reports": {str(k): v for k, v in self.tasks.items()},
            "evidence_references": [e.model_dump(mode="json") for e in self.evidence_refs.values()],
            "reports": [r.model_dump(mode="json") for r in self.findings.values()],
            "incidents": [u.model_dump(mode="json") for u in self.incidents.values()],
            "revisions": [u.model_dump(mode="json") for u in self.history],
            "decisions": [d.model_dump(mode="json") for d in self.decisions.values()],
            "events": list(self.events),
        }
