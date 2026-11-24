import json
from pathlib import Path

import pytest

from evaluation.results import export, metrics
from simulation.core.configuration import Scenario, load
from simulation.core.engine import Engine


def scenario(**changes: object) -> Scenario:
    return Scenario.model_validate({**load("flood_basic").model_dump(), **changes})


@pytest.mark.parametrize(
    "name",
    [
        "flood_basic",
        "flood_multiple",
        "flood_noise",
        "flood_outage",
        "flood_unavailable",
        "wildfire_basic",
        "earthquake_basic",
    ],
)
def test_episode(name: str, tmp_path: Path) -> None:
    engine = Engine(load(name))
    start = engine.snapshot()
    assert len(engine.active) == engine.config.agents - len(engine.config.unavailable)
    while engine.reason == "running":
        engine.step({})
    assert engine.t == engine.config.horizon
    assert engine.world.tiles[7, 6] == engine.config.events[0].terrain
    result = metrics(engine)
    assert json.loads(export(engine, tmp_path).read_text())["metrics"] == result
    engine.reset(engine.seed)
    assert engine.snapshot() == start
    while engine.reason == "running":
        engine.step({})
    assert metrics(engine) == result


def test_visibility() -> None:
    e = Engine(scenario(agents=1, people=0, dropout=1))
    assert not e.views["d0"].readings
    a = Engine(scenario(people=5, hidden_people=True))
    b = Engine(scenario(people=0))
    assert a.views == b.views
    noisy = Engine(scenario(people=0, false_positive=1))
    assert noisy.false > 0
    for agent, pkt in noisy.views.items():
        x, y = noisy.drones[agent].position
        assert all(abs(r.cell.x - x) + abs(r.cell.y - y) <= 2 for r in pkt.readings if r.cell)
        assert pkt.frame.agent_id == agent


def test_actions() -> None:
    e = Engine(scenario(agents=1, latency=1))
    assert not e.views["d0"].readings
    e.step({"d0": 4})
    assert e.invalid == 1 and e.views["d0"].readings
    e.step({"d0": 2})
    assert e.drones["d0"].position == (1, 0)
    e.step({"d0": 9})
    assert e.reason == "inactive"


def test_parallel() -> None:
    pytest.importorskip("pettingzoo")
    from pettingzoo.test import parallel_api_test  # type: ignore[import-untyped]

    from simulation.adapters.parallel import RescueEnv

    env = RescueEnv(load("flood_basic"))
    parallel_api_test(env, num_cycles=35)
    first, _ = env.reset(seed=7)
    again, _ = env.reset(seed=7)
    for a in first:
        assert env.observation_space(a).contains(first[a])
        assert (first[a] == again[a]).all()


def test_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("pygame")
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    from simulation.visualization.renderer import Renderer

    r = Renderer()
    e = Engine(load("flood_basic"))
    r.draw(e, None)
    r.draw(e, "d0")
    r.close()


def test_link_delay_expiry_and_loss() -> None:
    from uuid import UUID

    from communication.messages import Envelope

    uid = str(UUID(int=3))
    raw = {
        "schema_version": "1.0",
        "mission_id": uid,
        "session_id": uid,
        "source": "d0",
        "destination": "command",
        "message_id": uid,
        "correlation_id": uid,
        "sent_ms": 0,
        "timestamp": "2000-01-01T00:00:00Z",
        "sequence": 0,
        "priority": "routine",
        "payload": {"message_type": "heartbeat", "state": "active"},
    }
    msg = Envelope.model_validate(raw)
    engine = Engine(scenario())
    assert engine.send(msg) and not engine.receive("command")
    engine.step({})
    assert engine.receive("command") == (msg,)
    assert not Engine(scenario(loss=1)).send(msg)
    engine = Engine(scenario())
    assert engine.send(Envelope.model_validate({**raw, "expires_ms": 100}))
    engine.step({})
    assert not engine.receive("command")
    assert not Engine(scenario(outage_steps=[0])).send(msg)


def test_swap_boundary_and_restriction() -> None:
    e = Engine(scenario(agents=2))
    start = [d.position for d in e.drones.values()]
    e.step({"d0": 3, "d1": 1})
    assert [d.position for d in e.drones.values()] == start
    e = Engine(scenario(agents=1, terrain={"restricted": [{"x": 1, "y": 0}]}))
    e.step({"d0": 2})
    assert e.invalid == 1 and e.drones["d0"].position == (0, 0)
