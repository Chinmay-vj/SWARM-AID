"""Phase 12E-12F algorithm, checkpoint and reward checks. Development seeds only."""

import json
from pathlib import Path
from typing import Any

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("pettingzoo")

from evaluation import marl_train
from evaluation.marl_ppo import (
    ActorCritic,
    critic_input,
    gae,
    masked_log_probabilities,
    run_episode,
)
from simulation.adapters import marl_contract as contract
from simulation.adapters.marl import SearchEnv
from simulation.core.configuration import Scenario, load
from simulation.core.engine import Move

SEED = 12900
ALGORITHMS: tuple[Any, ...] = ("ippo", "mappo")


def smoke_config(agents: int = 3) -> dict[str, Any]:
    return marl_train.load_config(marl_train.DEFAULT_CONFIG, True) | {"agents": agents}


def test_masked_actions_have_no_probability() -> None:
    mask = torch.tensor([[True, False, True, False, False]])
    probabilities = masked_log_probabilities(torch.zeros(1, 5), mask).exp()
    assert probabilities[~mask].max() == 0
    assert probabilities.sum() == pytest.approx(1)
    with pytest.raises(ValueError):
        masked_log_probabilities(torch.zeros(1, 5), torch.zeros(1, 5, dtype=torch.bool))


def test_gae_bootstraps_truncation_but_not_termination() -> None:
    def one(terminated: bool) -> float:
        return gae([1.0], [0.5], [2.0], [terminated], [True], 0.9, 0.95)[0]

    assert one(True) == pytest.approx(0.5)
    assert one(False) == pytest.approx(1 + 0.9 * 2 - 0.5)
    two = gae([0, 1], [0, 0], [0, 0], [False, True], [False, True], 0.5, 1.0)
    assert two == pytest.approx([0.5, 1.0])


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_execution_uses_only_the_agents_local_observation(algorithm: Any) -> None:
    torch.manual_seed(0)
    model = ActorCritic(algorithm, 32)
    local = torch.rand(3, contract.SIZE)
    mask = torch.ones(3, 5, dtype=torch.bool)
    alone = model.policy(local[:1], mask[:1])
    together = model.policy(torch.cat((local[:1], torch.rand(2, contract.SIZE))), mask)
    assert torch.allclose(alone[0], together[0])
    changed = torch.cat((local[:1], local[1:] + 1))
    first = model.value(critic_input(algorithm, local))[0]
    second = model.value(critic_input(algorithm, changed))[0]
    assert torch.allclose(first, second) == (algorithm == "ippo")
    for count in (1, 6, 10):
        assert len(critic_input(algorithm, torch.rand(count, contract.SIZE))) == count


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_sampled_actions_respect_masks(algorithm: Any) -> None:
    config = smoke_config()
    env = marl_train.make_env(config, "flood_basic")
    torch.manual_seed(0)
    rows, metrics = run_episode(env, ActorCritic(algorithm, 32), SEED,
                                torch.Generator().manual_seed(1), 0.99, 0.95,
                                torch.device("cpu"))
    assert rows and all(bool(row[2][row[3]]) for row in rows)
    assert all(torch.isfinite(torch.tensor(row[4:])).all() for row in rows)
    assert env.counts["invalid_ids"] == 0 and metrics["steps"] == 10


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_resume_matches_an_uninterrupted_run(algorithm: Any, tmp_path: Path) -> None:
    config = smoke_config()

    def go(folder: str, **extra: Any) -> dict[str, Any]:
        options: dict[str, Any] = {"steps": 40, "seed": 3, "device_name": "cpu",
                                   "resume": False, "deadline": None, "smoke": True} | extra
        return marl_train.train(algorithm, config, tmp_path / folder, **options)

    go("whole")
    first = go("split", stop_after_updates=1)
    assert first["reason"] == "requested_boundary" and first["updates"] == 1
    second = go("split", resume=True)
    assert second["updates"] == 2 and second["env_steps"] == 40
    a = torch.load(tmp_path / "whole/latest.pt", weights_only=True)
    b = torch.load(tmp_path / "split/latest.pt", weights_only=True)
    assert all(torch.equal(a["model"][k], b["model"][k]) for k in a["model"])
    assert torch.equal(a["generator"], b["generator"])
    with pytest.raises(FileExistsError):
        go("split")
    with pytest.raises(ValueError, match="incompatible"):
        go("split", resume=True, seed=4)


def test_deadline_stops_before_any_update(tmp_path: Path) -> None:
    result = marl_train.train("ippo", smoke_config(), tmp_path, steps=40, seed=1,
                              device_name="cpu", resume=False, deadline=0.0, smoke=True)
    assert result["reason"] == "deadline" and result["updates"] == 0


def test_training_requires_authorization(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["x", "--algo", "mappo", "--run-dir", "D:/unused"])
    with pytest.raises(SystemExit):
        marl_train.main()


def test_training_and_validation_seeds_stay_in_their_namespaces() -> None:
    train = {marl_train.TRAIN_BASE + (s * 97 + i) % marl_train.TRAIN_SPAN
             for s in range(5) for i in range(2000)}
    assert train <= set(contract.DEVELOPMENT_SEEDS) and not train & set(range(12900, 13000))
    config = json.loads(marl_train.DEFAULT_CONFIG.read_bytes())
    assert set(range(13000, 13000 + config["validation_episodes"])) <= set(
        contract.VALIDATION_SEEDS)


def walk(version: Any, moves: list[Move]) -> list[float]:
    """One agent on an open map; returns the redundancy component per step."""
    config = Scenario.model_validate(load("flood_basic").model_dump() | {
        "agents": 1, "horizon": len(moves), "hazards": 0, "people": 0, "terrain": {},
        "events": ()})
    env = SearchEnv(config, reward=contract.RewardConfig(version=version))
    env.reset(seed=SEED)
    env.engine.drones["d0"].position = (5, 5)
    env.visited["d0"] = {(5, 5)}
    env.engine.views.clear()
    env.engine.capture()
    values = []
    for move in moves:
        _, _, _, _, infos = env.step({"d0": int(move)})
        values.append(infos["d0"]["reward_components"]["redundant"])
    return values


def test_revised_redundancy_penalizes_only_avoidable_revisits() -> None:
    straight = [Move.EAST] * 3
    back_and_forth = [Move.EAST, Move.WEST, Move.EAST]
    hold = [Move.HOLD] * 3
    assert walk("reward-2", straight) == [0, 0, 0]
    assert walk("reward-2", hold) == [0, 0, 0]
    assert walk("reward-2", back_and_forth) == [0, -0.02, -0.02]
    # reward-1 is dominated by unavoidable sensor overlap even on a straight path.
    assert all(v < -0.01 for v in walk("reward-1", straight))


def uncertainty(**changes: Any) -> float:
    config = Scenario.model_validate(load("flood_field").model_dump() | {
        "agents": 3, "horizon": 20} | changes)
    env = SearchEnv(config)
    env.reset(seed=SEED)
    while env.agents:
        env.step({})
    return float(env.totals["resolved_uncertainty"])


def test_uncertainty_reward_needs_noisy_field_observations() -> None:
    assert uncertainty(noise=0.0) == 0
    assert uncertainty(noise=0.5) > 0
    assert uncertainty(noise=1.0) == 0  # never clear, so never resolved
    assert uncertainty(noise=0.5, dropout=1.0) == 0  # hiding evidence earns nothing
