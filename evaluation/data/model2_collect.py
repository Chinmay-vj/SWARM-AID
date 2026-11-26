"""Capture fixed-time command examples at the existing consume boundary."""

from collections import defaultdict, deque
from typing import Any
from uuid import UUID, uuid5

from agents.command_agent.agent import CommandAgent, Settings
from agents.shared.domain import Category, Finding, Record, ReportedFinding
from communication.messages import (
    Envelope,
    EnvironmentalObservation,
    ForwardedReport,
    HazardDetection,
    IncidentUpdate,
    PossibleHumanDetection,
)
from evaluation.data.contracts import Modality, Split
from evaluation.data.model2_records import Input, Receipt, Target, Variant, relation
from simulation.adapters.model1 import Fleet
from simulation.core.configuration import Difficulty, Scenario, load
from simulation.core.engine import Engine
from simulation.sensors.mock import Reading


class Episode(Record):
    scenario: str
    seed: int
    agents: int
    split: Split
    difficulty: Difficulty | None = None


class LocalReport(Record):
    episode_id: UUID
    mission_id: UUID
    scenario_id: str
    seed: int
    sender: str
    report: ReportedFinding
    readings: tuple[Reading, ...]
    provider: str = "mock-symbolic/1"


def presentation_pattern(s: Input) -> tuple[object, ...]:
    """An ID-free comparison retaining relative timing, content and ordered context."""

    def signature(r: Receipt) -> tuple[object, ...]:
        f = r.report.finding
        o = f.observation
        return (
            f.kind,
            f.label,
            o.cell,
            o.confidence,
            tuple(e.modality for e in o.evidence),
            s.receipt.received_ms - o.observed_ms,
            r.received_ms - r.sent_ms,
        )

    return tuple(signature(r) for r in (*s.context, s.receipt))


class Capture(CommandAgent):
    def __init__(self, engine: Engine, plan: Episode):
        super().__init__(engine.mission_id, frozenset(engine.drones), Settings())
        self.plan = plan
        self.episode = uuid5(self.mission, f"{plan.seed}/{plan.agents}/fusion")
        self.receipts: list[Receipt] = []
        self.examples: list[tuple[Input, Target]] = []
        self.admitted: dict[UUID, Receipt] = {}
        self.disabled: tuple[Modality, ...] = tuple(
            m for m in load("flood_basic").modalities if m not in engine.config.modalities
        )

    def consume(
        self, msg: Envelope, principal: str, now: int
    ) -> IncidentUpdate | ForwardedReport | None:
        update = super().consume(msg, principal, now)
        p = msg.payload
        if not isinstance(p, (EnvironmentalObservation, HazardDetection, PossibleHumanDetection)):
            return update
        if not self.journal or self.journal[-1].envelope != msg:
            return update
        f = Finding(
            observation=p.observation,
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
        receipt = Receipt(
            report=ReportedFinding(message_id=msg.message_id, finding=f),
            sender=principal,
            session_id=msg.session_id,
            sent_ms=msg.sent_ms,
            received_ms=now,
        )
        self.receipts.append(receipt)
        context = tuple(
            r
            for r in self.admitted.values()
            if r.report.finding.observation.cell == f.observation.cell
            and f.observation.cell is not None
            and now - r.report.finding.observation.observed_ms < self.settings.freshness_ms
        )
        accepted = self.findings.get(f.observation.observation_id)
        if accepted and accepted.message_id == msg.message_id:
            self.admitted.setdefault(msg.message_id, receipt)
        sample = Input(
            sample_id=uuid5(self.episode, f"{msg.message_id}/native"),
            episode_id=self.episode,
            mission_id=self.mission,
            scenario_id=self.plan.scenario,
            seed=self.plan.seed,
            agents=self.plan.agents,
            split=self.plan.split,
            receipt=receipt,
            context=context,
            disabled_modalities=self.disabled,
            communication="command_received",
        )
        rel = relation(receipt, context)
        target = Target(sample_id=sample.sample_id, provenance="rule_derived", relationship=rel)
        if isinstance(update, IncidentUpdate):
            priority = self.priorities[update.incident.incident_id]
            refs = tuple(
                dict.fromkeys(
                    (
                        *priority.evidence,
                        *(update.recommendation.evidence_ids if update.recommendation else ()),
                    )
                )
            )
            target = Target(
                sample_id=sample.sample_id,
                provenance="rule_derived",
                relationship=rel,
                assessment=update.incident.category,
                baseline_incident=update.incident,
                urgency=priority.level,
                recommendation=update.recommendation,
                supporting=refs,
                uncertainty=update.incident.uncertainties,
                review_required=True,
            )
        elif f.kind == "environment" and accepted and rel != "conflicting":
            target = target.model_copy(update={"assessment": Category.ROUTINE})
        self.examples.append((sample, target))
        return update


def collect(plan: Episode, cap: int) -> tuple[list[tuple[Input, Target]], dict[str, Any]]:
    base = load(plan.scenario)
    cfg = Scenario.model_validate(base.model_dump() | {"agents": plan.agents, "seed": plan.seed})
    if cfg.field_profile:
        if plan.seed in range(42, 47):
            raise ValueError("reserved evaluation seed cannot enter expansion")
        if plan.difficulty:
            cfg = cfg.model_copy(
                update={
                    "field_profile": cfg.field_profile.model_copy(
                        update={"difficulty": plan.difficulty}
                    )
                }
            )
    elif plan.difficulty:
        raise ValueError("difficulty requires a field scenario")
    engine = Engine(cfg)
    fleet = Fleet(engine, coordination="shared_information", command=Settings())
    command = Capture(engine, plan)
    fleet.command = command
    local: dict[UUID, Reading] = {}
    while engine.reason == "running":
        fleet.advance(engine)
        if cfg.field_profile:
            for agent in fleet.agents.values():
                local.update((uid, item.reading) for uid, item in agent.inputs.current.items())
    bins: dict[tuple[str, ...], deque[tuple[Input, Target]]] = defaultdict(deque)
    patterns: set[tuple[object, ...]] = set()
    for s, t in command.examples:
        if cfg.field_profile:
            pattern = presentation_pattern(s)
            if pattern in patterns:
                continue
            patterns.add(pattern)
        key: tuple[str, ...] = (
            s.receipt.report.finding.kind,
            str(t.assessment),
            str(t.relationship),
            str(t.urgency),
            str(s.age_ms >= command.settings.freshness_ms),
        )
        bins[key].append((s, t))
    selected: list[tuple[Input, Target]] = []
    seen: set[UUID] = set()
    while bins and len(selected) < cap:
        for key in sorted(bins):
            item = bins[key].popleft()
            if item[0].sample_id not in seen:
                selected.append(item)
                seen.add(item[0].sample_id)
            if not bins[key]:
                del bins[key]
            if len(selected) == cap:
                break
    assert command.journal_complete
    extra: dict[str, Any] = {}
    if cfg.field_profile:
        extra["model1"] = [
            LocalReport(
                episode_id=command.episode,
                mission_id=engine.mission_id,
                scenario_id=cfg.scenario_id,
                seed=cfg.seed,
                sender=r.sender,
                report=r.report,
                readings=tuple(local[e.evidence_id] for e in r.report.finding.observation.evidence),
            ).model_dump(mode="json")
            for r in command.receipts
        ]
        extra["event_trace"] = [
            {
                "tick": event.step,
                "time_ms": event.step * cfg.tick_ms,
                "cell": event.cell.model_dump(),
                "terrain": event.terrain,
                "source": "scenario.events",
            }
            for event in cfg.events
            if event.step <= engine.t
        ]
        extra["observation_windows"] = [w.model_dump() for w in cfg.field_profile.windows]
        if fleet.network:
            extra["transport_counts"] = fleet.network.router.metrics()
    return selected, {
        **extra,
        "episode_id": str(command.episode),
        "configuration": cfg.model_dump(mode="json", exclude_none=True),
        "plan": plan.model_dump(exclude_none=True),
        "settings": command.settings.model_dump(),
        "command_counts": dict(command.counts),
        "source": [r.model_dump(mode="json") for r in command.receipts],
        "journal": [
            j.model_dump(mode="json")
            for j in command.journal
            if isinstance(
                j.envelope.payload,
                (EnvironmentalObservation, HazardDetection, PossibleHumanDetection),
            )
        ],
        "providers": {
            k: type(getattr(fleet.agents["d0"], k)).__qualname__
            for k in ("perception", "fusion", "reasoning", "planning")
        },
    }


def challenge(base: Input, kind: Variant) -> tuple[Input, Target]:
    """Counterfactual presentation, never submitted through an authenticated endpoint."""
    r = base.receipt
    report = r.report
    f = report.finding
    ctx: tuple[Receipt, ...] = (r,)
    if kind == "repeat":
        modified = r
    elif kind == "relay":
        modified = r.model_copy(
            update={
                "sender": "controlled-relay",
                "session_id": uuid5(base.sample_id, "relay-session"),
                "report": report.model_copy(update={"message_id": uuid5(base.sample_id, kind)}),
            }
        )
    elif kind == "stale":
        ctx = ()
        modified = r.model_copy(
            update={
                "received_ms": max(
                    r.received_ms, f.observation.observed_ms + Settings().freshness_ms
                )
            }
        )
    elif kind in ("conflict", "spurious"):
        if f.kind != "environment":
            raise ValueError("challenge requires environmental parent")
        changed = Finding(
            kind="hazard" if kind == "conflict" else "possible_human",
            label="controlled_hazard" if kind == "conflict" else None,
            observation=f.observation,
        )
        modified = r.model_copy(
            update={
                "report": ReportedFinding(message_id=uuid5(base.sample_id, kind), finding=changed)
            }
        )
        if kind == "spurious":
            if base.scenario_id != "command_routine":
                raise ValueError("false-alarm reference needs the zero-person fixture")
            ctx = ()
    else:
        raise ValueError("unsupported transformation")
    row = Input.model_validate(
        {
            **base.model_dump(),
            "variant": kind,
            "sample_id": uuid5(base.episode_id, f"{base.sample_id}/{kind}"),
            "parent_id": base.sample_id,
            "context": ctx,
            "receipt": modified,
            "communication": "controlled",
        }
    )
    rel = relation(modified, ctx)
    return row, Target(
        sample_id=row.sample_id,
        provenance="unresolved" if kind in ("stale", "spurious") else "rule_derived",
        relationship=rel,
        conflicting=tuple(e.evidence_id for e in f.observation.evidence)
        if kind == "conflict"
        else (),
        uncertainty=("independent human review pending",),
    )
