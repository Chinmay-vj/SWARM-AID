from uuid import UUID

import pytest
from pydantic import ValidationError

from agents.command_agent.agent import Checkpoint, CommandAgent, Settings
from agents.drone_agent.reporting import Mailbox
from agents.shared.domain import Cell, Evidence, Observation
from communication.messages import (
    Envelope,
    ForwardedReport,
    HumanApproval,
    HumanIncidentReview,
    IncidentUpdate,
    PossibleHumanDetection,
)
from evaluation.command_agent_experiments import episode
from simulation.core.configuration import Scenario, load

MISSION = UUID(int=901)


def report(owner: str, n: int, at: int = 5) -> Envelope:
    obs = Observation(
        observation_id=UUID(int=n),
        cell=Cell(x=1, y=2),
        observed_ms=at,
        confidence=0.4,
        evidence=(
            Evidence(
                evidence_id=UUID(int=n + 100),
                origin=owner,
                captured_ms=at,
                modality="thermal",
                artifact_key="synthetic-test",
            ),
        ),
    )
    box = Mailbox(owner, MISSION, 8)
    box.sequence["command"] = n
    box.publish(
        PossibleHumanDetection(message_type="possible_human_detection", observation=obs), at
    )
    return box.sent[-1]


def test_fusion_scope_versions_and_replay() -> None:
    members = frozenset(("d0", "d1"))
    agent = CommandAgent(MISSION, members, Settings())
    first = report("d0", 1)
    assert agent.consume(first, "other", 5) is None
    a = agent.consume(first, "d0", 5)
    assert isinstance(a, IncidentUpdate) and a.recommendation
    assert agent.consume(first, "d0", 5) is None
    b = agent.consume(report("d1", 2), "d1", 6)
    assert isinstance(b, IncidentUpdate) and b.recommendation
    assert b.incident.incident_id == a.incident.incident_id and b.incident.revision == 2
    assert len(b.recommendation.evidence_ids) == 2
    operator = Mailbox("operator", MISSION, 8)
    for revision in (a, b):
        rec = revision.recommendation
        assert rec
        operator.publish(
            HumanApproval(
                message_type="human_approval",
                incident_id=rec.incident_id,
                recommendation_id=rec.recommendation_id,
                revision=rec.incident_revision,
                decision="confirm_rescue_need",
                reason="synthetic operator decision",
            ),
            10,
            expires_ms=50,
        )
        agent.consume(operator.sent[-1], "operator", 10)
    assert agent.counts["rejected_decision"] == 1 and agent.counts["confirm_rescue_need"] == 1
    update = agent.incidents[b.incident.incident_id]
    assert update.incident.confirmation_id == operator.sent[-1].message_id
    for action in ("resolve", "close"):
        operator.publish(
            HumanIncidentReview.model_validate(
                {
                    "message_type": "human_incident_review",
                    "incident_id": update.incident.incident_id,
                    "revision": update.incident.revision,
                    "action": action,
                    "reason": "scripted report",
                }
            ),
            12,
            expires_ms=50,
        )
        result = agent.consume(operator.sent[-1], "operator", 12)
        assert isinstance(result, IncidentUpdate)
        update = result
    assert agent.dispositions[update.incident.incident_id] == "closed"
    checkpoint = Checkpoint.model_validate_json(agent.checkpoint().model_dump_json())
    assert CommandAgent.restore(checkpoint, MISSION, members).snapshot() == agent.snapshot()
    with pytest.raises(ValueError, match="scope"):
        CommandAgent.restore(checkpoint, UUID(int=3), members)


def test_corroboration_keeps_pending_revision_decidable() -> None:
    agent = CommandAgent(MISSION, frozenset(("d0",)), Settings())
    first = agent.consume(report("d0", 1), "d0", 5)
    assert isinstance(first, IncidentUpdate) and first.recommendation
    held = report("d0", 2, at=6)
    assert agent.consume(held, "d0", 6) is None
    assert agent.counts["corroborated"] == 1
    assert agent.incidents[first.incident.incident_id].incident.revision == 1
    rec = first.recommendation
    operator = Mailbox("operator", MISSION, 8)
    operator.publish(
        HumanApproval(
            message_type="human_approval",
            incident_id=rec.incident_id,
            recommendation_id=rec.recommendation_id,
            revision=rec.incident_revision,
            decision="approve_review",
            reason="synthetic operator decision",
        ),
        10,
        expires_ms=50,
    )
    assert isinstance(agent.consume(operator.sent[-1], "operator", 10), IncidentUpdate)
    assert agent.counts["approve_review"] == 1 and agent.counts["rejected_decision"] == 0
    third = report("d0", 3, at=12)
    folded = agent.consume(third, "d0", 12)
    assert isinstance(folded, IncidentUpdate) and folded.incident.revision == 3
    assert held.message_id in folded.incident.reports
    assert third.message_id in folded.incident.reports
    assert not agent.held


def test_forwarding_and_stale_data() -> None:
    agent = CommandAgent(MISSION, frozenset(("d0",)), Settings(mode="direct", freshness_ms=8))
    payload = agent.consume(report("d0", 1), "d0", 5)
    assert isinstance(payload, ForwardedReport)
    box = Mailbox("command", MISSION, 8)
    box.publish(payload, 6, "operator")
    assert Envelope.model_validate_json(box.sent[-1].model_dump_json()).schema_version == "1.2"
    with pytest.raises(ValidationError):
        Envelope.model_validate(box.sent[-1].model_dump() | {"schema_version": "1.0"})
    assert agent.consume(report("d0", 2), "d0", 13) is None
    assert agent.counts["stale"] == 1 and not agent.incidents


@pytest.mark.parametrize(
    "scenario",
    [
        "flood_basic",
        "flood_server_unavailable",
        "flood_network_partition",
        "flood_unavailable",
        "wildfire_basic",
        "earthquake_basic",
        "landslide_basic",
        "cyclone_basic",
    ],
)
def test_command_replay(scenario: str) -> None:
    cfg = Scenario.model_validate(load(scenario).model_dump() | {"horizon": 10})
    result = episode(cfg, "fusion", True)
    assert result == episode(cfg, "fusion", True)
    if scenario == "flood_server_unavailable":
        counts = result["counts"]
        assert isinstance(counts, dict) and counts["offline"] == counts["recovered"] == 1


def test_stale_lease_conflict_and_capacity() -> None:
    agent = CommandAgent(MISSION, frozenset(("d0",)), Settings(capacity=1))
    msg = report("d0", 1)
    first = agent.consume(msg, "d0", 5)
    assert isinstance(first, IncidentUpdate) and first.recommendation
    payload = msg.payload
    assert isinstance(payload, PossibleHumanDetection)
    different = payload.observation.model_copy(update={"confidence": 0.1})
    agent.consume(
        msg.model_copy(update={"payload": payload.model_copy(update={"observation": different})}),
        "d0",
        6,
    )
    assert (
        len(agent.conflicts) == 1
        and agent.findings[UUID(int=1)].finding.observation.confidence == 0.4
    )
    agent.consume(report("d0", 2), "d0", 7)
    assert agent.counts["capacity"] == 1
    agent.expire(first.recommendation.expires_ms)
    assert agent.dispositions[first.incident.incident_id] == "expired"
    with pytest.raises(ValueError, match="retention"):
        agent.checkpoint()


def test_operator_assignment_pause() -> None:
    from communication.messages import HumanOverride
    from simulation.adapters.model1 import Fleet
    from simulation.core.engine import Engine

    engine = Engine(load("flood_basic"))
    fleet = Fleet(engine, command=Settings(), coordination="fixed_sector")
    assert fleet.network and fleet.command and fleet.assignments
    for revision, action in ((0, "pause"), (0, "resume"), (1, "resume")):
        fleet.network.issue(
            "operator",
            HumanOverride.model_validate(
                {"message_type": "human_override", "action": action, "reason": "scripted"}
            ),
            "command",
            3000,
            revision,
        )
        for _ in range(2):
            fleet.advance(engine)
    assert (
        fleet.command.counts["operator_pause"]
        == fleet.command.counts["invalid_override"]
        == fleet.command.counts["operator_resume"]
        == 1
    )
    assert fleet.assignments.transitions[-1][1] == "active"


@pytest.mark.parametrize(
    "scenario",
    [
        "command_routine",
        "command_single",
        "command_conflict",
        "command_missing_modalities",
        "command_stale",
        "command_operator_offline",
    ],
)
def test_sensor_and_endpoint_fixtures(scenario: str) -> None:
    result = episode(load(scenario), "fusion", True)
    sim = result["simulator"]
    assert isinstance(sim, dict) and sim["reason"] == "horizon"
    if scenario in ("command_routine", "command_stale"):
        assert result["incidents"] == 0


def test_unverified_provider_cannot_confirm_or_publish() -> None:
    from agents.shared.domain import Category, Incident, ReportedFinding

    class InvalidAssessment:
        def assess(
            self, previous: Incident | None, reports: tuple[ReportedFinding, ...]
        ) -> Incident:
            return Incident(
                incident_id=UUID(int=400),
                revision=1,
                category=Category.CONFIRMED,
                confirmation_id=UUID(int=900),
                reports=(reports[0].message_id,),
                uncertainties=(),
            )

    agent = CommandAgent(MISSION, frozenset(("d0",)), Settings(), assessment=InvalidAssessment())
    assert agent.consume(report("d0", 1), "d0", 5) is None
    assert not agent.incidents and agent.counts["assessment_rejected"] == 1


def test_delivered_alert_has_evidence_and_version() -> None:
    from communication.messages import CommandAlert
    from simulation.adapters.model1 import Fleet
    from simulation.core.engine import Engine

    engine = Engine(load("flood_basic"))
    fleet = Fleet(engine, command=Settings())
    assert fleet.network
    for _ in range(5):
        fleet.advance(engine)
    msg = next(m for m in fleet.network.history["operator"] if isinstance(m.payload, CommandAlert))
    assert (
        isinstance(msg.payload, CommandAlert)
        and msg.payload.supporting_evidence
        and msg.payload.priority_reason
    )
    with pytest.raises(ValidationError):
        Envelope.model_validate(msg.model_dump() | {"schema_version": "1.1"})
