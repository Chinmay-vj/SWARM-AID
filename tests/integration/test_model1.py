from uuid import UUID

import pytest

from agents.drone_agent.agent import DroneAgent
from agents.drone_agent.components import Settings
from agents.shared.domain import (
    Action,
    Cell,
    DroneState,
    Finding,
    Intent,
    LocalView,
    SensorFrame,
    TaskLease,
)
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


def test_injected_perception_providers_have_independent_agent_state() -> None:
    class AgentProvider:
        def __init__(self, owner: str) -> None:
            self.owner = owner
            self.calls = 0

        def perceive(self, frame: SensorFrame) -> tuple[Finding, ...]:
            assert frame.agent_id == self.owner
            self.calls += 1
            return ()

    created: dict[str, AgentProvider] = {}

    def factory(owner: str) -> AgentProvider:
        provider = AgentProvider(owner)
        created[owner] = provider
        return provider

    e = engine(3)
    fleet = Fleet(e, perception_factory=factory)
    assert len({id(provider) for provider in created.values()}) == 3
    fleet.advance(e)
    assert all(provider.calls == 1 for provider in created.values())
    assert all(fleet.agents[owner].perception is provider for owner, provider in created.items())

    shared = AgentProvider("d0")
    with pytest.raises(ValueError, match="independent per-agent"):
        Fleet(engine(2), perception_factory=lambda _owner: shared)


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


def test_same_tick_operator_priority() -> None:
    from agents.drone_agent.reporting import Mailbox
    from communication.messages import HumanOverride, MissionInstruction

    e = engine()
    a = Fleet(e).agents["d0"]
    cmd = Mailbox("command", e.mission_id, 8)
    op = Mailbox("operator", e.mission_id, 8)
    cmd.publish(
        MissionInstruction(
            message_type="mission_instruction",
            task_id=UUID(int=4),
            action=Action(intent=Intent.HOLD),
        ),
        0,
        "d0",
        expires_ms=100,
    )
    op.publish(
        HumanOverride(message_type="human_override", action="pause", reason="test"),
        0,
        "d0",
        expires_ms=100,
    )
    a.receive(cmd.sent[-1], "command", 0)
    a.receive(op.sent[-1], "operator", 0, expected_revision=0)
    assert a.override == "pause" and a.lease is None


def test_sensor_filter_and_snapshot_isolation() -> None:
    from agents.shared.domain import Finding

    class Inspect:
        received: SensorFrame | None = None

        def perceive(self, frame: SensorFrame) -> tuple[Finding, ...]:
            self.received = frame
            return ()

    e = engine()
    provider = Inspect()
    a = DroneAgent(
        "d0", e.mission_id, Settings(modalities=("text", "imu")), (12, 10), perception=provider
    )
    a.cycle(e.views["d0"], 0, True)
    assert provider.received and provider.received.cell is None
    assert all(i.reading.cell is None for i in a.inputs.current.values())
    events = a.snapshot()["events"]
    assert isinstance(events, list)
    events[-1]["action"] = "changed"
    assert a.logs[-1]["action"] != "changed"


def test_post_step_energy_guard() -> None:
    e = engine()
    a = DroneAgent("d0", e.mission_id, Settings(movement=True, reserve=0.5), (12, 10))
    a.lease = TaskLease(
        task_id=UUID(int=1),
        action=Action(intent=Intent.SURVEY, target=Cell(x=1, y=0)),
        expires_ms=100,
    )
    packet = e.views["d0"]

    def at(battery: float) -> Move:
        return a.cycle(
            packet.model_copy(
                update={"frame": packet.frame.model_copy(update={"battery_fraction": battery})}
            ),
            0,
            True,
        )

    assert at(0.51) == Move.HOLD
    assert at(0.52) == Move.EAST


def test_future_fusion_never_enters_memory() -> None:
    from agents.drone_agent.baselines import Fusion
    from agents.shared.domain import Finding

    class Future(Fusion):
        def fuse(self, frame: SensorFrame, reports: tuple[Finding, ...]) -> LocalView:
            view = super().fuse(frame, reports)
            f = view.observations[0]
            future = f.model_copy(
                update={"observation": f.observation.model_copy(update={"observed_ms": 1000})}
            )
            return view.model_copy(update={"observations": (future,)})

    e = engine()
    a = DroneAgent("d0", e.mission_id, Settings(), (12, 10), fusion=Future())
    assert a.cycle(e.views["d0"], 0, True) == Move.HOLD
    assert not a.memory.items and a.health.provider_errors == 1
