"""Phase 12I regression fixtures for the learned-policy path (development seeds only)."""

from typing import Any

import pytest

pytest.importorskip("pettingzoo")

from agents.command_agent.agent import Settings as CommandSettings
from communication.messages import HumanOverride
from simulation.adapters.marl import SearchEnv
from simulation.adapters.model1 import Fleet
from simulation.core.configuration import Scenario, load

SEED = 12970
EAST = 2


def make(**changes: Any) -> SearchEnv:
    base: dict[str, Any] = {"scenario_id": "fixture", "disaster": "flood", "width": 12,
                            "height": 3, "agents": 1, "people": 1, "hazards": 0, "horizon": 12,
                            "miss": 0}
    return SearchEnv(Scenario.model_validate(base | changes))


def travel(env: SearchEnv, start: int = 0) -> tuple[int, int]:
    """Moves and gate rejections while always asking to go east, counted from tick `start`."""
    moved = rejected = 0
    while env.agents:
        count = env.engine.t >= start
        before = env.engine.drones["d0"].position
        _, _, _, _, infos = env.step({"d0": EAST})
        if count:
            moved += env.engine.drones["d0"].position != before
            rejected += infos["d0"]["rejected"]
    return moved, rejected


def test_delayed_frames_are_refused_by_the_existing_safety_gate() -> None:
    env = make()
    env.reset(seed=SEED)
    assert travel(env)[0] > 0
    late = make(latency=2)
    late.reset(seed=SEED)
    moved, rejected = travel(late)
    assert moved == 0 and rejected > 0


def operated(enable: bool = True) -> SearchEnv:
    env = make()
    env.reset(seed=SEED)
    env.fleet = Fleet(env.engine, communication=True, command=CommandSettings())
    env.fleet.allow_external_policy = enable
    return env


def control(env: SearchEnv, action: str, target: str, revision: int = 0) -> None:
    assert env.fleet.network is not None
    env.fleet.network.issue(
        "operator",
        HumanOverride.model_validate(
            {"message_type": "human_override", "action": action, "reason": "test"}),
        target, 100_000, revision=revision)


def status(env: SearchEnv) -> str:
    assert env.fleet.assignments is not None
    return env.fleet.assignments.transitions[-1][1]


def step_east(env: SearchEnv) -> bool:
    before = env.engine.drones["d0"].position
    env.step({"d0": EAST})
    return env.engine.drones["d0"].position != before


@pytest.mark.parametrize("action", ["pause", "end"])
def test_no_movement_once_a_mission_control_takes_effect(action: str) -> None:
    env = operated()
    assert any([step_east(env), step_east(env), step_east(env)])  # moving beforehand
    control(env, action, "command")
    effective = []
    while env.agents:
        moved = step_east(env)
        if status(env) != "active":
            effective.append(moved)
    assert len(effective) >= 5 and not any(effective)
    assert env.fleet.assignments is not None
    states = [state for _, state in env.fleet.assignments.transitions]
    stop = states.index("paused" if action == "pause" else "aborted")
    assert "active" not in states[stop:]  # nothing resumed the mission


def test_individual_pause_remains_effective() -> None:
    env = operated()
    control(env, "pause", "d0")
    assert travel(env, start=3)[0] == 0


def test_only_the_operator_with_a_checked_revision_resumes() -> None:
    env = operated()
    control(env, "pause", "command")
    for _ in range(3):
        step_east(env)
    control(env, "resume", "command", revision=0)  # stale revision
    assert not any([step_east(env), step_east(env), step_east(env)])
    assert status(env) == "paused"
    control(env, "resume", "command", revision=1)
    resumed = [step_east(env) for _ in range(5)]
    assert status(env) == "active" and any(resumed)


def test_heuristic_leases_do_not_outlast_a_mission_pause() -> None:
    env = SearchEnv(load("flood_basic"))
    env.reset(seed=SEED)
    fleet = Fleet(env.engine, communication=True, coordination="fixed_sector",
                  command=CommandSettings())
    env.fleet = fleet
    engine, moved_before, moved_paused = env.engine, 0, 0
    while engine.reason == "running":
        if engine.t == 3:
            control(env, "pause", "command")
        before = {a: d.position for a, d in engine.drones.items()}
        fleet.advance(engine)
        moved = sum(d.position != before[a] for a, d in engine.drones.items())
        if status(env) == "paused":
            moved_paused += moved
        else:
            moved_before += moved
    assert moved_before > 0 and moved_paused == 0


def test_missing_mission_authorization_prevents_movement() -> None:
    env = operated()
    env.fleet.assignments = None
    assert travel(env)[0] == 0


def test_learned_policy_is_disabled_on_operator_facing_fleets_by_default() -> None:
    env = operated(enable=False)
    assert Fleet(env.engine, command=CommandSettings()).allow_external_policy is False
    assert travel(env)[0] == 0


def test_missing_sensors_are_explicit_and_block_movement() -> None:
    env = make(dropout=1.0)
    observations, infos = env.reset(seed=SEED)
    values = observations["d0"]
    assert values[2] == 0 and values[6] == 0  # position unknown, no readings
    assert infos["d0"]["action_mask"].tolist() == [1, 0, 0, 0, 0]
    assert travel(env)[0] == 0
