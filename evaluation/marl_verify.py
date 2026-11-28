"""Write Phase 12E-12F verification and profile records from actual bounded runs."""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch

from evaluation import marl_baselines, marl_train
from simulation.adapters import marl_contract as contract

OUTPUT = marl_baselines.OUTPUT
CHECKPOINTS = Path("D:/SWARM-AID-DATA/checkpoints/phase12")
ALGORITHMS: tuple[Any, ...] = ("ippo", "mappo")


def rows(folder: Path) -> dict[tuple[str, str, int], dict[str, Any]]:
    lines = (folder / "baseline_episodes.jsonl").read_text(encoding="utf8").splitlines()
    return {marl_baselines.key(r): r for r in map(json.loads, lines)}


def rewards() -> dict[str, Any]:
    """reward-2 on the same deterministic baseline episodes; original records untouched."""
    folder = OUTPUT / "reward2"
    marl_baselines.baseline(folder, contract.RewardConfig(version="reward-2"))
    old, new = rows(OUTPUT), rows(folder)
    ignored = {"identity", "wall_seconds"}
    changed = sorted({k for key in old for k in old[key]
                      if k not in ignored and not k.startswith("reward_")
                      and old[key][k] != new[key][k]})
    summary = {}
    for policy in marl_baselines.POLICIES:
        keys = [k for k in old if k[1] == policy]
        summary[policy] = {
            f"{label}_{name}": sum(data[k][name] for k in keys) / len(keys)
            for label, data in (("reward1", old), ("reward2", new))
            for name in ("reward_total", "reward_redundant")}
    return {
        "episodes_compared": len(old), "non_reward_metrics_changed": changed,
        "mean_by_policy": summary,
        "comparability": "reward-1 and reward-2 totals are different quantities",
        "redundancy_cause": "radius-2 sensing overlaps the previous footprint on every step, "
                            "so the covered fraction is near 1 even on a straight new path",
        "revision": "reward-2 penalizes only a move back into a cell the agent occupied",
        "known_gap": "holding is not penalized; revisits that are necessary transit are",
        "uncertainty_cause": "indistinct readings require a field profile with noise > 0; "
                             "the basic scenarios have neither",
        "uncertainty_gap": "contradictions between clear labels are not rewarded or penalized",
        "verified_by": "tests/integration/test_phase12ef.py",
    }


def runs() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    base = CHECKPOINTS / "verification"
    if base.exists():
        shutil.rmtree(base)
    smoke_config = marl_train.load_config(marl_train.DEFAULT_CONFIG, True)
    # Full-size updates on smoke seeds, for timing only.
    timing = marl_train.load_config(marl_train.DEFAULT_CONFIG, False) | {"validate_every": 10**6,
                                                                       "validation_episodes": 1}
    devices = ["cpu", "cuda"] if torch.cuda.is_available() else ["cpu"]
    smoke, profile = [], []
    for algorithm in ALGORITHMS:
        for device in devices:
            result = marl_train.train(
                algorithm, smoke_config, base / f"smoke-{algorithm}-{device}", steps=40, seed=1,
                device_name=device, resume=False, deadline=None, smoke=True)
            smoke.append(result)
            profile.append(marl_train.train(
                algorithm, timing, base / f"profile-{algorithm}-{device}", steps=1440, seed=1,
                device_name=device, resume=False, deadline=None, smoke=True))
    return smoke, profile


def resume_check() -> dict[str, Any]:
    base = CHECKPOINTS / "verification"
    config = marl_train.load_config(marl_train.DEFAULT_CONFIG, True)
    report: dict[str, Any] = {}
    for algorithm in ALGORITHMS:
        for name in ("whole", "split"):  # only this check's own scratch runs
            shutil.rmtree(base / f"{algorithm}-{name}", ignore_errors=True)
    for algorithm in ALGORITHMS:
        common: dict[str, Any] = {"steps": 40, "seed": 5, "device_name": "cpu",
                                  "deadline": None, "smoke": True}
        marl_train.train(algorithm, config, base / f"{algorithm}-whole", resume=False, **common)
        marl_train.train(algorithm, config, base / f"{algorithm}-split", resume=False,
                         stop_after_updates=1, **common)
        marl_train.train(algorithm, config, base / f"{algorithm}-split", resume=True, **common)
        a, b = (torch.load(base / f"{algorithm}-{name}/latest.pt", weights_only=True)
                for name in ("whole", "split"))
        report[algorithm] = {
            "identical_weights": all(torch.equal(a["model"][k], b["model"][k])
                                     for k in a["model"]),
            "identical_sampling_state": torch.equal(a["generator"], b["generator"]),
        }
    report["scope"] = ("CPU, FP32, one thread, same sources; resume is at update boundaries "
                       "where no episode is in progress. GPU exactness not verified.")
    return report


def main() -> None:
    reward = rewards()
    smoke, profile = runs()
    resumed = resume_check()
    write = marl_baselines.write
    write("reward_verification.json", reward)
    write("smoke_test_results.json", {
        "note": "plumbing only; rewards are not evidence of learning", "runs": smoke})
    write("training_profile.json", {
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "update_shape": "16 episodes x 30 steps x 6 agents; 4 epochs; minibatch 512",
        "runs": profile})
    write("checkpoint_resume_verification.json", resumed)
    budget = {}
    for r in profile:
        rate = r["env_steps_per_second"]
        budget[f"{r['algorithm']}-{r['device']}"] = {
            "env_steps_per_second": rate, "hours_per_300k_steps": 300_000 / rate / 3600,
            "hours_per_1M_steps": 1_000_000 / rate / 3600}
    write("phase12g_training_budget.json", {
        "measured": budget, "proposal": "300k steps per algorithm per learner seed, 3 seeds",
        "caveat": "short measurement excluding validation (9 episodes every 10 updates)"})
    config = marl_train.load_config(marl_train.DEFAULT_CONFIG, False)
    write("training_configuration.json", {
        "default": config, "rtx2060": "same file, --device cpu recommended; card untested"})
    write("algorithm_specifications.json", {
        "common": "shared compact tanh MLPs, masked categorical policy, GAE, clipped PPO, "
                  "FP32; bootstrap on truncation, none on termination",
        "ippo": {"actor": "shared parameters, local observation",
                 "critic": "shared parameters, local observation"},
        "mappo": {"actor": "identical to IPPO", "critic": "training only: own + mean + max "
                  "of all agents' local observations; no simulator truth"},
        "execution": "ActorCritic.policy uses only the agent's observation and mask",
        "sample_unit": "agent transition; per-agent reward",
        "not_included": ["value clipping", "value normalization", "recurrence",
                         "parallel environments", "mixed precision"]})
    write("contract_resolution.json", {
        "movement_lease": "policy lease through safety.authorize in symbolic simulation only; "
                          "owner approval PENDING (--authorize-start records it); does not "
                          "verify command-lease enforcement or physical control",
        "reward": "reward-2 for training; reward-1 and its baseline preserved",
        "independent_baseline": "kept as stationary floor; recommend adding a no-communication "
                                "nearest-unsearched-cell heuristic from local memory as a "
                                "separate new baseline",
        "seeds": "42-45 recorded as executed; 42-46 retired from unseen evaluation; "
                 "900000-900099 protected and never executed",
        "test_guard": "tests/conftest.py skips the two tests that execute 43-45",
        "generated": datetime.now(UTC).isoformat()})


if __name__ == "__main__":
    main()
