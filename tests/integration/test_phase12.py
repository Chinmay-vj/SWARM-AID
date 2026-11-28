"""Phase 12B-12D contracts. Development seeds only; no policy is trained."""

import json
import subprocess
import sys
from pathlib import Path
from random import Random
from typing import Any

import numpy as np
import pytest

pytest.importorskip("pettingzoo")

from evaluation import marl_baselines
from simulation.adapters import marl_contract as contract
from simulation.adapters.marl import SearchEnv
from simulation.core.configuration import Scenario, load
from simulation.core.engine import Move

SEED = 12500


def config(agents: int = 3, **changes: Any) -> Scenario:
    return Scenario.model_validate(
        load("flood_basic").model_dump() | {"agents": agents, "horizon": 8} | changes)


def rollout(env: SearchEnv, seed: int = SEED) -> list[Any]:
    observations, infos = env.reset(seed=seed)
    chooser = Random(seed)
    trace: list[Any] = [{a: v.tobytes() for a, v in observations.items()}]
    while env.agents:
        actions = {a: chooser.choice(np.flatnonzero(infos[a]["action_mask"]).tolist())
                   for a in env.agents}
        observations, rewards, term, trunc, infos = env.step(actions)
        trace.append(({a: v.tobytes() for a, v in observations.items()}, rewards, term, trunc))
    return trace


def test_shapes_types_and_determinism() -> None:
    env = SearchEnv(config())
    observations, infos = env.reset(seed=SEED)
    assert list(observations) == ["d0", "d1", "d2"]
    for agent, value in observations.items():
        assert value.dtype == np.float32 and value.shape == (contract.SIZE,)
        assert env.observation_space(agent).contains(value)
        assert infos[agent]["action_mask"].shape == (5,)
        assert infos[agent]["evidence_kind"] == "symbolic"
    assert len(contract.FIELDS) == contract.SIZE
    assert rollout(SearchEnv(config())) == rollout(SearchEnv(config()))


def test_reset_leaks_nothing_between_episodes() -> None:
    used = SearchEnv(config())
    rollout(used, SEED + 1)
    assert rollout(used) == rollout(SearchEnv(config()))


def test_agents_hold_independent_state() -> None:
    env = SearchEnv(config())
    env.reset(seed=SEED)
    env.step({})
    memories = [env.fleet.agents[a].memory for a in env.agents]
    assert len({id(m) for m in memories}) == 3
    assert len({id(env.searched[a]) for a in env.agents}) == 3
    env.fleet.agents["d0"].memory.items.clear()
    assert env.fleet.agents["d1"].memory.items


def test_hidden_truth_does_not_reach_observations_or_masks() -> None:
    env = SearchEnv(config(radius=1))
    env.reset(seed=SEED)
    env.step({})

    def view() -> tuple[bytes, ...]:
        env.searched = {a: set() for a in env.possible_agents}
        return tuple(v.tobytes() for v in env._observe(env.agents).values()) + tuple(
            env._info(a)["action_mask"].tobytes() for a in env.agents)

    before = view()
    env.engine.people = {}
    env.engine.hazards = {}
    env.engine.world.tiles = dict.fromkeys(env.engine.world.tiles, "fire")
    env.engine.covered.clear()
    assert view() == before


def test_missing_observations_are_flagged_and_not_zero_confidence_evidence() -> None:
    env = SearchEnv(config(dropout=1.0))
    observations, infos = env.reset(seed=SEED)
    value = observations["d0"]
    fields = dict(zip(contract.FIELDS, value, strict=True))
    assert (fields["x"], fields["position_known"], fields["has_readings"]) == (-1, 0, 0)
    assert all(fields[f"missing_{s}"] == 1 for s in contract.SENSORS)
    assert not value[len(contract.SELF_FIELDS) + len(contract.SENSORS) :].any()
    assert infos["d0"]["action_mask"].tolist() == [1, 0, 0, 0, 0]


def test_communication_outage_masks_movement() -> None:
    env = SearchEnv(config(outage_steps=tuple(range(8))))
    env.reset(seed=SEED)
    start = {a: d.position for a, d in env.engine.drones.items()}
    while env.agents:
        env.step(dict.fromkeys(env.agents, int(Move.EAST)))
    assert {a: d.position for a, d in env.engine.drones.items()} == start
    assert env.episode_metrics()["policy_rejected_actions"] > 0


def test_invalid_actions_are_contained_and_penalized() -> None:
    env = SearchEnv(config())
    env.reset(seed=SEED)
    start = {a: d.position for a, d in env.engine.drones.items()}
    _, _, _, _, infos = env.step({"d0": 99, "d1": int(Move.INACTIVE), "d2": 0})
    assert env.counts["invalid_ids"] == 2
    assert env.agents == ["d0", "d1", "d2"]
    assert {a: d.position for a, d in env.engine.drones.items()} == start
    assert infos["d0"]["rejected"] and not infos["d2"]["rejected"]
    assert infos["d0"]["reward_components"]["rejected_action"] == -0.1


def test_restricted_cells_and_collisions_cannot_be_overridden() -> None:
    env = SearchEnv(config(6, horizon=20))
    env.reset(seed=SEED)
    restricted = {(c.x, c.y) for c in env.restricted}
    chooser = Random(1)
    while env.agents:
        env.step({a: chooser.randrange(5) for a in env.agents})
        positions = [d.position for d in env.engine.drones.values() if d.active]
        assert len(set(positions)) == len(positions)
        assert not restricted & set(positions)


def test_reward_accounting_matches_components() -> None:
    env = SearchEnv(config())
    env.reset(seed=SEED)
    total = 0.0
    chooser = Random(2)
    while env.agents:
        _, rewards, _, _, infos = env.step({a: chooser.randrange(5) for a in env.agents})
        for agent, value in rewards.items():
            assert value == pytest.approx(sum(infos[agent]["reward_components"].values()))
            total += value
    metrics = env.episode_metrics()
    assert metrics["reward_total"] == pytest.approx(total)
    assert not any("person" in k or "people" in k for k in contract.RewardConfig.model_fields)


def test_termination_and_truncation_are_distinct() -> None:
    env = SearchEnv(config(horizon=2))
    env.reset(seed=SEED)
    env.engine.drones["d0"].battery = 21
    _, _, term, trunc, _ = env.step({})
    assert term == {"d0": True, "d1": False, "d2": False} and not any(trunc.values())
    assert env.agents == ["d1", "d2"]
    _, _, term, trunc, _ = env.step({})
    assert trunc == {"d1": True, "d2": True} and not any(term.values())
    assert env.agents == [] and env.step({}) == ({}, {}, {}, {}, {})


@pytest.mark.parametrize("seed", [*range(42, 47), 101, 900000, 900099, 0])
def test_closed_seeds_are_rejected(seed: int) -> None:
    with pytest.raises(ValueError, match="not an open"):
        SearchEnv(config()).reset(seed=seed)


def test_seed_is_mandatory_and_namespaces_are_disjoint() -> None:
    with pytest.raises(ValueError, match="explicit"):
        SearchEnv(config()).reset()
    spaces = [contract.DEVELOPMENT_SEEDS, contract.VALIDATION_SEEDS,
              contract.PROPOSED_FINAL_SEEDS, contract.LEGACY_RESERVED_SEEDS]
    assert sum(map(len, spaces)) == len(set().union(*spaces))
    assert contract.require_open_seed(13000) == "validation"


@pytest.mark.parametrize("policy", marl_baselines.BASELINES)
def test_adapter_matches_the_original_runner(policy: Any) -> None:
    assert marl_baselines.parity(config(6, horizon=14), policy, SEED) == []


def test_pilot_resumes_without_repeating_episodes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(marl_baselines, "SCENARIOS", ("flood_basic",))
    monkeypatch.setattr(marl_baselines, "SEEDS", (SEED,))
    marl_baselines.baseline(tmp_path)
    capsys.readouterr()
    with (tmp_path / "baseline_episodes.jsonl").open("a") as stream:
        stream.write('{"partial')
    marl_baselines.baseline(tmp_path)
    assert "[baseline]" not in capsys.readouterr().out
    assert set(json.loads((tmp_path / "baseline_results.json").read_bytes())["summary"]) == set(
        marl_baselines.POLICIES)


def test_environment_loads_no_perception_stack() -> None:
    code = ("import sys; import simulation.adapters.marl; "
            "sys.exit(int('torch' in sys.modules))")
    assert subprocess.run([sys.executable, "-c", code], check=False).returncode == 0
