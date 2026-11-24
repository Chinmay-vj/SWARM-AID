from uuid import UUID

import pytest

from agents.drone_agent.agent import DroneAgent
from agents.drone_agent.components import Settings
from agents.shared.domain import Action, Cell, DroneState, Intent, LocalView, SensorFrame, TaskLease
from simulation.adapters.model1 import Fleet
from simulation.core.configuration import Scenario, load
from simulation.core.engine import Engine, Move


def engine(count: int = 1, **changes: object) -> Engine:
    return Engine(
        Scenario.model_validate(
            {**load("flood_basic").model_dump(), "agents": count, "horizon": 4, **changes}
        )
    )


@pytest.mark.parametrize("count", [1, 3, 6, 10])
def test_fleet(count: int) -> None:
    e = engine(count)
    fleet = Fleet(e)
    while e.reason == "running":
        fleet.advance(e)
    assert len(fleet.agents) == count
    for a, agent in fleet.agents.items():
        assert agent.life.state == DroneState.ENDED
        assert agent.health.provider_errors == 0
        assert all(f.observation.evidence[0].origin == a for f in agent.memory.items.values())
        assert agent.logs[-1]["outcome"] == "applied"
        assert any(m.payload.message_type == "heartbeat" for m in agent.mail.sent)


def test_replay_and_hidden_truth() -> None:
    def run(people: int) -> list[dict[str, object]]:
        e = engine(people=people, hidden_people=True)
        fleet = Fleet(e)
        while e.reason == "running":
            fleet.advance(e)
        return list(fleet.agents["d0"].logs)

    assert run(1) == run(4) == run(1)


def test_memory_scope_and_age() -> None:
    e = engine(2)
    fleet = Fleet(e)
    fleet.advance(e)
    a, b = fleet.agents.values()
    assert not a.world.at(Cell(x=11, y=9))
    saved = a.memory.snapshot()
    a.memory.expire(10000)
    assert not a.memory.items
    a.memory.restore(saved)
    assert a.memory.items
    with pytest.raises(ValueError):
        b.memory.restore(saved)


def test_provider_failure_and_input_rejection() -> None:
    class Broken:
        def perceive(self, frame: SensorFrame) -> tuple[()]:
            raise RuntimeError("fixture")

    e = engine(2)
    a = DroneAgent("d0", e.mission_id, Settings(), (12, 10), perception=Broken())
    assert a.cycle(e.views["d0"], 0, True) == Move.HOLD
    assert a.health.provider_errors == 1 and a.life.state == DroneState.HOLD
    assert a.mail.sent[-1].payload.message_type == "error_report"
    assert a.cycle(e.views["d1"], 0, True) == Move.HOLD
    assert a.cycle(e.views["d0"], 5000, True) == Move.HOLD
    assert a.health.invalid_inputs == 2
    with pytest.raises(ValueError):
        a.life.change(DroneState.REGISTERING, 1, "bad transition")


def test_movement_authority() -> None:
    class East:
        def plan(self, view: LocalView, intent: Intent, lease: TaskLease | None) -> Action:
            return Action(intent=Intent.SURVEY, target=Cell(x=1, y=0))

    e = engine()
    a = DroneAgent(
        "d0",
        e.mission_id,
        Settings(movement=True),
        (12, 10),
        frozenset({Cell(x=1, y=0)}),
        planning=East(),
    )
    packet = e.views["d0"]
    assert a.cycle(packet, 0, True) == Move.HOLD
    a.lease = TaskLease(
        task_id=UUID(int=8),
        action=Action(intent=Intent.SURVEY, target=Cell(x=1, y=0)),
        expires_ms=100,
    )
    assert a.cycle(packet, 0, True) == Move.HOLD
    a.restricted = frozenset()
    assert a.cycle(packet, 0, True) == Move.EAST
    a.override = "pause"
    assert a.cycle(packet, 0, True) == Move.HOLD


def test_missing_and_conflict() -> None:
    e = engine(dropout=1)
    fleet = Fleet(e)
    fleet.advance(e)
    a = fleet.agents["d0"]
    assert a.health.status == "degraded" and a.logs[-1]["action"] == "HOLD"
    e = engine()
    pkt = e.views["d0"]
    rows = list(pkt.readings)
    idx = next(i for i, r in enumerate(rows) if r.evidence.modality == "thermal")
    rows[idx] = rows[idx].model_copy(update={"value": "fire"})
    a = Fleet(e).agents["d0"]
    assert a.cycle(pkt.model_copy(update={"readings": tuple(rows)}), 0, True) == Move.REQUEST
    assert a.logs[-1]["category"] == "conflicting_evidence"


def test_control_binding_and_expiry() -> None:
    from communication.messages import Envelope

    e = engine()
    a = Fleet(e).agents["d0"]
    data = a.mail.sent[0].model_dump()
    data.update(
        source="operator",
        destination="d0",
        expires_ms=50,
        payload={"message_type": "human_override", "action": "pause", "reason": "fixture"},
    )
    message = Envelope.model_validate(data)
    with pytest.raises(ValueError):
        a.receive(message, "operator", 0)
    with pytest.raises(ValueError):
        a.receive(message, "peer", 0, expected_revision=0)
    with pytest.raises(ValueError):
        a.receive(message, "operator", 50, expected_revision=0)
    a.receive(message, "operator", 0, expected_revision=0)
    assert a.cycle(e.views["d0"], 0, True) == Move.HOLD and a.revision == 1
    assert len(a.instructions) == 1
