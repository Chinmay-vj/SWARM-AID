import json
from uuid import UUID, uuid5

import pytest

from agents.drone_agent.reporting import Mailbox
from agents.shared.domain import Action, Category, Incident, Intent, Recommendation
from communication.messages import (
    AgentHealth,
    HumanApproval,
    HumanOverride,
    IncidentUpdate,
    MissionInstruction,
)
from communication.network import Conditions, Router, State
from simulation.adapters.model1 import Fleet
from simulation.core.configuration import Scenario, load
from simulation.core.engine import Engine

UID = UUID(int=1)


def setup(**changes: object) -> tuple[Router, Mailbox]:
    r = Router(UID, Conditions.model_validate(changes), 3, 10, 0)
    for name, role in [
        ("a", "drone"),
        ("b", "drone"),
        ("command", "command"),
        ("operator", "human"),
    ]:
        r.register(name, role, uuid5(UID, name))
    return r, Mailbox("a", UID, 20)


def raw(box: Mailbox, dest: str = "b") -> bytes:
    box.publish(
        AgentHealth(message_type="agent_health", battery_fraction=0.8, degraded_sensors=()), 0, dest
    )
    return box.sent[-1].model_dump_json().encode()


def test_validation() -> None:
    r, b = setup()
    data = raw(b)
    assert not r.submit("b", data)
    assert not r.submit("unknown", data)
    for field, value in [
        ("mission_id", str(UUID(int=8))),
        ("schema_version", "9"),
        ("destination", "absent"),
        ("source", None),
        ("payload", {"message_type": "bad"}),
    ]:
        assert not r.submit("a", json.dumps({**json.loads(data), field: value}).encode())
    assert not r.submit("a", b"x" * 66000)
    assert not r.submit("a", b"{")
    with pytest.raises(ValueError):
        r.register("a", "drone", UID)
    assert r.submit("a", data)
    r.deregister("b")
    r.advance(11)
    assert r.metrics()["dropped"] == 1


def test_queue_dedup_expiry_and_recovery() -> None:
    r, b = setup(duplicate=1, capacity=2, retention_ms=35)
    data = raw(b, "peers")
    assert r.submit("a", data)
    r.submit("a", raw(b))
    assert r.metrics()["overflow"] == 1
    r.availability("b", False)
    r.advance(10)
    assert not r.drain("b")
    r.availability("b", True)
    r.advance(20)
    messages = r.drain("b")
    assert len(messages) == 1 and messages[0].destination == "peers"
    assert r.metrics()["duplicate"] == 1
    r.submit("a", data)
    r.advance(21)
    assert not r.drain("b")
    r.availability("b", False)
    r.submit("a", raw(b))
    r.advance(40)
    assert r.metrics()["expired"] == 2


def test_heartbeat_stale() -> None:
    r, _ = setup(heartbeat_ms=12)
    r.advance(12)
    assert r.endpoints["a"].state == State.DEGRADED
    assert r.endpoints["command"].state == State.CONNECTED


@pytest.mark.parametrize("count", [2, 6])
def test_peer_delivery_and_mock_server(count: int) -> None:
    e = Engine(Scenario.model_validate({**load("flood_basic").model_dump(), "agents": count}))
    f = Fleet(e, communication=True)
    for _ in range(4):
        f.advance(e)
    assert f.network
    reports = f.network.history["command"]
    assert {m.source for m in reports if m.payload.message_type == "registration"} == set(f.agents)
    for a, agent in f.agents.items():
        assert any(
            ev.origin != a
            for finding in agent.memory.items.values()
            for ev in finding.observation.evidence
        )
    assert f.network.router.acks


def test_control_and_review() -> None:
    e = Engine(load("flood_basic"))
    f = Fleet(e, communication=True)
    n = f.network
    assert n
    override = HumanOverride(message_type="human_override", action="pause", reason="fixture")
    n.mail["d0"].publish(override, 0, "d1", expires_ms=300)
    assert n.router.metrics()["rejected"] == 1
    n.issue("operator", override, "d1", 300, revision=0)
    inc = Incident(
        incident_id=UID, revision=1, category=Category.POSSIBLE, reports=(UID,), uncertainties=()
    )
    rec = Recommendation(
        recommendation_id=UID,
        incident_id=UID,
        incident_revision=1,
        request="inspect_evidence",
        evidence_ids=(UID,),
        unknowns=(),
        expires_ms=400,
    )
    n.issue(
        "command",
        IncidentUpdate(message_type="incident_update", incident=inc, recommendation=rec),
        "operator",
        300,
    )
    for decision in ("approve_review", "reject"):
        n.issue(
            "operator",
            HumanApproval.model_validate(
                {
                    "message_type": "human_approval",
                    "incident_id": UID,
                    "revision": 1,
                    "recommendation_id": UID,
                    "decision": decision,
                    "reason": "fixture",
                }
            ),
            "command",
            300,
        )
    n.issue(
        "command",
        MissionInstruction(
            message_type="mission_instruction", task_id=UID, action=Action(intent=Intent.HOLD)
        ),
        "d0",
        400,
    )
    f.advance(e)
    f.advance(e)
    assert f.agents["d1"].override == "pause"
    assert f.agents["d0"].lease
    assert any(m.payload.message_type == "incident_update" for m in n.history["operator"])
    assert sum(m.payload.message_type == "human_approval" for m in n.history["command"]) == 2


def test_fault_replay() -> None:
    def run(name: str) -> list[dict[str, object]]:
        e = Engine(load(name))
        f = Fleet(e, communication=True)
        assert f.network
        for _ in range(10):
            f.advance(e)
        return f.network.router.events

    assert run("flood_network_loss") == run("flood_network_loss")
    assert any(e["event"] == "dropped" for e in run("flood_network_loss"))
    assert any(e["event"] == "connection_restored" for e in run("flood_server_unavailable"))


def test_versioned_status_and_async_port() -> None:
    import asyncio

    from pydantic import ValidationError

    from communication.messages import Envelope, MissionUpdate

    r, _ = setup()
    cmd = Mailbox("command", UID, 10)
    cmd.publish(
        MissionUpdate(
            message_type="mission_update", revision=1, status="active", summary="test mission"
        ),
        0,
        "operator",
    )
    message = cmd.sent[-1]
    with pytest.raises(ValidationError):
        Envelope.model_validate({**message.model_dump(), "schema_version": "1.0"})
    asyncio.run(r.port("command").send(message))
    r.advance(10)
    assert asyncio.run(r.port("operator").receive()) == message


def test_reordering_and_input_overflow() -> None:
    r, b = setup(jitter=30)
    for _ in range(10):
        r.submit("a", raw(b))
    r.advance(100)
    seqs = [m.sequence for m in r.drain("b")]
    assert len(seqs) == 10 and seqs != sorted(seqs)
    r, b = setup(capacity=1)
    r.submit("a", raw(b))
    r.advance(10)
    r.submit("a", raw(b))
    r.advance(20)
    assert r.metrics()["overflow"] == 1


def test_partition_and_outage_lease() -> None:
    e = Engine(load("flood_server_unavailable"))
    f = Fleet(e, communication=True)
    n = f.network
    assert n
    n.issue(
        "command",
        MissionInstruction(
            message_type="mission_instruction", task_id=UID, action=Action(intent=Intent.HOLD)
        ),
        "d0",
        3000,
    )
    for _ in range(5):
        f.advance(e)
    assert f.agents["d0"].lease is None and not f.agents["d0"].health.online
    r, b = setup()
    r.link = lambda a, b: False
    r.submit("a", raw(b))
    r.advance(20)
    assert not r.drain("b")
    r.link = lambda a, b: True
    r.advance(30)
    assert len(r.drain("b")) == 1


@pytest.mark.parametrize("api", ["async", "drain"])
def test_expiry_in_unread_inbox(api: str) -> None:
    import asyncio

    r, b = setup()
    data = json.dumps({**json.loads(raw(b)), "expires_ms": 15}).encode()
    assert r.submit("a", data)
    r.advance(10)
    r.advance(15)
    if api == "drain":
        assert r.drain("b") == ()
    else:
        with pytest.raises(asyncio.QueueEmpty):
            asyncio.run(r.port("b").receive())
    assert r.metrics()["expired"] == 1


@pytest.mark.parametrize("dest", ["peers", "b"])
def test_retry_does_not_rebind_to_new_session(dest: str) -> None:
    r, b = setup()
    data = raw(b, dest)
    assert r.submit("a", data)
    old = r.endpoints["b"]
    r.deregister("b")
    r.register("b", "drone", UUID(int=100))
    assert not r.submit("a", data)
    r.advance(10)
    assert not r.drain("b") and not old.inbox


def test_negative_and_repeated_ack_metrics() -> None:
    from communication.messages import Acknowledgement, Heartbeat

    r, b = setup()
    b.publish(Heartbeat(message_type="heartbeat", state="active"), 0, "command")
    assert r.submit("a", b.sent[-1].model_dump_json().encode())
    r.advance(10)
    (msg,) = r.drain("command")
    cmd = Mailbox("command", UID, 8)
    for outcome in ("rejected", "accepted", "duplicate"):
        cmd.publish(
            Acknowledgement.model_validate(
                {
                    "message_type": "acknowledgement",
                    "acknowledged_id": msg.message_id,
                    "outcome": outcome,
                }
            ),
            10,
            "a",
        )
        assert r.submit("command", cmd.sent[-1].model_dump_json().encode())
    r.advance(20)
    assert r.metrics()["acknowledged"] == 1


def test_delayed_heartbeat_remains_stale() -> None:
    from communication.messages import Heartbeat

    r, b = setup(heartbeat_ms=20)
    b.publish(Heartbeat(message_type="heartbeat", state="active"), 0, "command")
    r.submit("a", b.sent[-1].model_dump_json().encode())
    r.advance(25)
    assert r.endpoints["a"].state == State.DEGRADED


def test_deregister_discards_and_accounts_for_unread() -> None:
    r, b = setup()
    r.submit("a", raw(b))
    r.advance(10)
    endpoint = r.endpoints["b"]
    r.deregister("b")
    assert not endpoint.inbox and r.events[-2]["reason"] == "closed unread inbox"


def test_backlogged_lease_requires_post_recovery_assignment() -> None:
    e = Engine(load("flood_server_unavailable"))
    f = Fleet(e, communication=True)
    n = f.network
    assert n
    for _ in range(5):
        f.advance(e)
    instruction = MissionInstruction(
        message_type="mission_instruction", task_id=UID, action=Action(intent=Intent.HOLD)
    )
    n.issue("command", instruction, "d1", 3000)
    for _ in range(3):
        f.advance(e)
    assert f.agents["d1"].lease is None
    assert any(
        ev["event"] == "application_rejected" and ev["recipient"] == "d1" for ev in n.router.events
    )
    n.issue("command", instruction, "d1", 3000)
    f.advance(e)
    assert f.agents["d1"].lease is not None
