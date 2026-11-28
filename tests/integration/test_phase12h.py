"""Coverage and reward accounting fixtures for Phase 12H (development seeds only)."""

from typing import Any

import numpy as np
import pytest

pytest.importorskip("pettingzoo")

from agents.shared.domain import Cell
from simulation.adapters.marl import SearchEnv
from simulation.adapters.marl_contract import RewardConfig
from simulation.core.configuration import Scenario

SEED = 12950


def make(**changes: Any) -> SearchEnv:
    base: dict[str, Any] = {"scenario_id": "fixture", "disaster": "flood", "width": 9,
                            "height": 3, "agents": 2, "people": 1, "hazards": 0,
                            "horizon": 4, "miss": 0}
    return SearchEnv(Scenario.model_validate(base | changes),
                     reward=RewardConfig(version="reward-2"))


def drive(env: SearchEnv, move: int = 2, seed: int = SEED) -> list[dict[str, float]]:
    env.reset(seed=seed)
    rewards = []
    while env.agents:
        rewards.append(env.step(dict.fromkeys(env.agents, move))[1])
    return rewards


def test_coverage_is_the_cumulative_union_over_all_grid_cells() -> None:
    env = make(terrain={"building": [Cell(x=8, y=2)]})
    env.reset(seed=SEED)
    engine = env.engine
    expected = {p for p in engine.world.tiles for d in engine.drones.values()
                if abs(p[0] - d.position[0]) + abs(p[1] - d.position[1]) <= 2}
    assert engine.covered == expected  # overlapping footprints counted once
    assert env.episode_metrics()["coverage"] == len(expected) / 27  # unrounded, all cells
    before = len(engine.covered)
    env.step(dict.fromkeys(env.agents, 0))
    assert len(env.engine.covered) == before  # repeated observation adds nothing


def test_inaccessible_cells_are_counted_in_the_denominator_and_numerator() -> None:
    env = make(width=3, height=1, agents=1, terrain={"building": [Cell(x=2, y=0)]})
    env.reset(seed=SEED)
    assert env.episode_metrics()["coverage"] == 1.0
    assert (2, 0) in env.engine.covered


def test_horizon_truncates_and_state_resets_between_episodes() -> None:
    env = make()
    drive(env)
    first = env.episode_metrics()
    assert first["reason"] == "horizon" and first["steps"] == 4
    drive(env, seed=SEED + 1)
    drive(env)
    assert env.episode_metrics() == first == (drive(fresh := make()), fresh.episode_metrics())[1]


def test_hidden_truth_outside_sensor_range_does_not_reach_observations() -> None:
    a, b = make(), make(terrain={"building": [Cell(x=8, y=2)]})
    left, right = a.reset(seed=SEED)[0], b.reset(seed=SEED)[0]
    assert all(np.array_equal(left[k], right[k]) for k in left)


def test_new_cell_reward_is_not_duplicated_and_components_sum() -> None:
    env = make()
    env.reset(seed=SEED)
    initial = len(env.engine.covered)
    total = 0.0
    while env.agents:
        _, rewards, _, _, infos = env.step(dict.fromkeys(env.agents, 2))
        for agent, value in rewards.items():
            assert value == pytest.approx(sum(infos[agent]["reward_components"].values()))
            total += infos[agent]["reward_components"]["new_cell"]
    assert total == pytest.approx(0.1 * (len(env.engine.covered) - initial))


def test_missing_observations_earn_nothing() -> None:
    env = make(dropout=1.0)
    rewards = drive(env, move=0)
    metrics = env.episode_metrics()
    assert metrics["coverage"] == 0 and metrics["reward_total"] == 0
    assert all(v == 0 for step in rewards for v in step.values())


def test_corroboration_term_is_co_sensing_by_one_agent_not_independent_agreement() -> None:
    env = make(agents=1)
    env.reset(seed=SEED)
    # every covered cell is "corroborated" at once by image/thermal/environment of one packet
    assert env.corroborated == env.engine.covered


def test_no_reward_term_depends_on_people() -> None:
    totals = []
    for people in (0, 5):
        env = make(people=people, hidden_people=False)
        drive(env)
        totals.append(env.episode_metrics()["reward_total"])
    assert totals[0] == pytest.approx(totals[1])
