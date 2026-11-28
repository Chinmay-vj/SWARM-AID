"""Phase 12A-12D records, development baseline pilot and environment profile. No training.

    python -u -m evaluation.marl_baselines smoke
    python -u -m evaluation.marl_baselines baseline     (resumable)
    python -u -m evaluation.marl_baselines profile
    python -u -m evaluation.marl_baselines contracts
"""

import argparse
import csv
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from itertools import product
from pathlib import Path
from random import Random
from statistics import mean, stdev
from typing import Any

from evaluation.experiment_runner import episode
from evaluation.process_memory import peak_rss_mib
from evaluation.results import DEFINITIONS
from simulation.adapters import marl_contract as contract
from simulation.adapters.coordination import PolicyName
from simulation.adapters.marl import SearchEnv
from simulation.core.configuration import Scenario, load

OUTPUT = Path("D:/SWARM-AID-DATA/runs/phase12")
SCENARIOS = ("flood_basic", "wildfire_basic", "earthquake_basic")
SEEDS = (12000, 12001, 12002)
BASELINES: tuple[PolicyName, ...] = ("independent", "fixed_sector", "shared_information")
# random_masked is an adapter sanity reference for the action path, not an existing baseline.
POLICIES = (*BASELINES, "random_masked")
AGENTS = 6


def write(name: str, value: Any) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / name).write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf8")


def revision() -> dict[str, Any]:
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], capture_output=True, text=True,
                              check=False).stdout.strip()

    return {"commit": git("rev-parse", "HEAD"), "uncommitted": bool(git("status", "--porcelain"))}


def scenario(name: str, agents: int = AGENTS, **changes: Any) -> Scenario:
    return Scenario.model_validate(load(name).model_dump() | {"agents": agents} | changes)


def run_episode(
    config: Scenario, policy: str, seed: int, reward: contract.RewardConfig | None = None
) -> dict[str, Any]:
    coordination: Any = None if policy == "random_masked" else policy
    env = SearchEnv(config, coordination=coordination, reward=reward)
    started = time.perf_counter()
    _, infos = env.reset(seed=seed)
    coverage = [len(env.engine.covered)]
    chooser = Random(f"policy/{seed}")
    while env.agents:
        actions = {}
        if policy == "random_masked":
            for a in env.agents:
                allowed = [i for i, ok in enumerate(infos[a]["action_mask"]) if ok and i]
                actions[a] = chooser.choice(allowed) if allowed else 0
        _, _, _, _, infos = env.step(actions)
        coverage.append(len(env.engine.covered))
    return {**env.episode_metrics(), "coverage_cells_by_tick": coverage,
            "wall_seconds": time.perf_counter() - started}


def parity(config: Scenario, policy: PolicyName, seed: int) -> list[str]:
    """Differences between the adapter and the original runner on the same configuration."""
    original: Any = episode(Scenario.model_validate(config.model_dump() | {"seed": seed}), policy)
    adapted = run_episode(config, policy, seed)
    pairs = {
        "coverage_by_tick": (original["coverage_cells_by_tick"],
                             adapted["coverage_cells_by_tick"]),
        "steps": (original["metrics"]["steps"], adapted["steps"]),
        "invalid": (original["metrics"]["invalid"], adapted["engine_invalid"]),
        "observations": (original["metrics"]["observations"], adapted["observations_captured"]),
        "battery": (original["metrics"]["battery_used"], adapted["battery_used"]),
        "bytes": (original["network"]["bytes"], adapted["network_bytes"]),
        "safety": (original["safety_interventions"], adapted["safety_interventions"]),
    }
    return [name for name, (a, b) in pairs.items() if a != b]


def smoke() -> None:
    config = scenario("flood_basic", 2, horizon=5)
    for policy in POLICIES:
        row = run_episode(config, policy, 12999)
        print(f"[smoke] policy={policy} steps={row['steps']} coverage={row['coverage']:.3f} "
              f"reward={row['reward_total']:.3f} seconds={row['wall_seconds']:.2f}", flush=True)


def key(row: dict[str, Any]) -> tuple[str, str, int]:
    return row["scenario"], row["policy"], row["seed"]


def baseline(folder: Path, reward: contract.RewardConfig | None = None) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    log = folder / "baseline_episodes.jsonl"
    identity = {"observation": contract.OBSERVATION_VERSION, "action": contract.ACTION_VERSION,
                "reward": (reward or contract.RewardConfig()).model_dump(), "agents": AGENTS}
    rows = []
    if log.is_file():
        for line in log.read_text(encoding="utf8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue  # a partially written final line is rerun
            if row.get("identity") == identity:
                rows.append(row)
    done = {key(r) for r in rows}
    plan = [p for p in product(SCENARIOS, POLICIES, SEEDS) if p not in done]
    total = len(SCENARIOS) * len(POLICIES) * len(SEEDS)
    started = time.perf_counter()
    for index, (name, policy, seed) in enumerate(plan, start=1):
        contract.require_open_seed(seed)
        row = run_episode(scenario(name), policy, seed, reward) | {
            "scenario": name, "policy": policy, "seed": seed, "identity": identity,
            "split": "development"}
        rows.append(row)
        with log.open("a", encoding="utf8") as stream:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
            stream.flush()
        elapsed = time.perf_counter() - started
        print(f"[baseline] {len(done) + index}/{total} policy={policy} scenario={name} "
              f"seed={seed} coverage={row['coverage']:.3f} "
              f"redundant={row['redundant_footprint_fraction']:.3f} "
              f"reward={row['reward_total']:.2f} elapsed_s={elapsed:.1f} "
              f"eta_s={elapsed / index * (len(plan) - index):.1f}", flush=True)
    rows.sort(key=key)
    columns = sorted(k for k in rows[0] if k not in ("identity", "coverage_cells_by_tick"))
    with (folder / "baseline_episode_metrics.csv").open("w", newline="", encoding="utf8") as out:
        writer = csv.DictWriter(out, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    numeric = [c for c in columns if c != "seed" and isinstance(rows[0][c], (int, float))]
    summary = {}
    for policy in POLICIES:
        group = [r for r in rows if r["policy"] == policy]
        summary[policy] = {"episodes": len(group), "reasons": sorted({r["reason"] for r in group})}
        for column in numeric:
            values = [r[column] for r in group if r[column] is not None]
            if values:
                summary[policy][column] = {
                    "mean": mean(values),
                    "sd": stdev(values) if len(values) > 1 else None}
    differences = {
        f"{name}/{policy}/{seed}": parity(scenario(name), policy, seed)
        for name, policy, seed in product(SCENARIOS, BASELINES, SEEDS[:1])
    }
    print(f"[parity] checked={len(differences)} "
          f"mismatched={sum(bool(v) for v in differences.values())}", flush=True)
    (folder / "baseline_results.json").write_text(json.dumps({
        "label": "development baseline measurements, not final research evaluation",
        "generated": datetime.now(UTC).isoformat(), "revision": revision(),
        "identity": identity, "scenarios": SCENARIOS, "seeds": SEEDS,
        "definitions": DEFINITIONS, "summary": summary, "parity_mismatches": differences,
        "notes": ["independent issues no movement assignments, so its agents stay put",
                  "standard deviation pools three scenarios and is not seed-only variance",
                  "random_masked is an adapter sanity reference"],
    }, indent=2), encoding="utf8")


def profile() -> None:
    rows = []
    for agents in (1, 3, 6, 10, 20):
        env = SearchEnv(scenario("flood_basic", agents))
        resets, steps, episodes = [], [], []
        chooser = Random(f"profile/{agents}")
        cpu, wall = time.process_time(), time.perf_counter()
        for seed in range(12900, 12903):
            tick = time.perf_counter()
            env.reset(seed=seed)
            resets.append(time.perf_counter() - tick)
            started = time.perf_counter()
            while env.agents:
                actions = {a: chooser.randrange(5) for a in env.agents}
                tick = time.perf_counter()
                env.step(actions)
                steps.append(time.perf_counter() - tick)
            episodes.append(time.perf_counter() - started)
        rows.append({
            "agents": agents, "reset_ms": mean(resets) * 1000, "step_ms": mean(steps) * 1000,
            "env_steps_per_second": len(steps) / sum(steps),
            "agent_steps_per_second": agents * len(steps) / sum(steps),
            "episode_seconds": mean(episodes),
            "cpu_to_wall": (time.process_time() - cpu) / (time.perf_counter() - wall),
        })
        print(f"[profile] {rows[-1]}", flush=True)
    write("environment_profile.json", {
        "generated": datetime.now(UTC).isoformat(), "revision": revision(), "runs": rows,
        "peak_rss_MiB": peak_rss_mib(), "torch_imported": "torch" in sys.modules,
        "bound": "CPU, single-threaded Python; no GPU code path",
        "rtx2060": "not measured; the environment needs no GPU or BF16",
    })
    print(f"[profile] peak_rss_MiB={peak_rss_mib():.0f} torch_imported={'torch' in sys.modules}",
          flush=True)


def contracts() -> None:
    reward = contract.RewardConfig()
    write("observation_spec.json", {
        "version": contract.OBSERVATION_VERSION, "dtype": "float32", "range": [-1, 1],
        "size": contract.SIZE, "fields": contract.FIELDS,
        "missing": "position -1 and position_known 0; per-sensor missing flags; zero patch",
        "policy_visible": ["own packet", "own and delivered peer findings in bounded memory",
                           "own search history", "public geometry", "battery", "link state"],
        "evaluator_only": ["tiles", "people", "hazards", "true coverage", "future views"],
        "critic_note": "no global ground-truth state is provided for a centralized critic",
    })
    write("action_spec.json", {
        "version": contract.ACTION_VERSION,
        "actions": {int(m): m.name for m in contract.ACTIONS},
        "validity": "info['action_mask'] uses public bounds, restricted cells, reserve, link",
        "invalid": "unknown id keeps the agent's own behaviour and is penalized; masked or "
                   "vetoed movement becomes HOLD and is penalized",
        "not_available": ["OBSERVE/REQUEST/REPORT (chosen by the agent)", "RETURN", "INACTIVE"],
        "safety": "agents.drone_agent.safety.authorize then simulator constraints",
    })
    write("reward_spec.json", {
        **reward.model_dump(),
        "scope": "per agent; no team mixing",
        "uses_evaluator_state": "true coverage, for the training signal only",
        "termination": "terminated when a drone retires; truncated at the horizon; no bonus",
        "never_rewarded": ["person detection or confirmation", "report volume", "hiding evidence"],
        "risks": ["coverage may dominate evidence quality",
                  "holding avoids penalties and still earns corroboration from sensor chance",
                  "redundancy penalty also hits necessary transit and revisits",
                  "weights are untuned; tune only on development seeds"],
    })
    write("environment_contract.json", {
        "class": "simulation.adapters.marl.SearchEnv", "api": "PettingZoo ParallelEnv",
        "reset": "reset(seed=...) required; builds a new Engine and Fleet",
        "step": "returns observations, rewards, terminations, truncations, infos",
        "configurable": ["scenario", "agents", "horizon", "coordination", "reward"],
        "observations": "symbolic; no perception network runs",
        "observation_version": contract.OBSERVATION_VERSION,
        "action_version": contract.ACTION_VERSION, "reward_version": reward.version,
        "revision": revision(),
    })
    write("seed_protocol.json", {
        "version": contract.SEED_PROTOCOL_VERSION,
        "development": [contract.DEVELOPMENT_SEEDS.start, contract.DEVELOPMENT_SEEDS.stop - 1],
        "validation": [contract.VALIDATION_SEEDS.start, contract.VALIDATION_SEEDS.stop - 1],
        "proposed_final": [contract.PROPOSED_FINAL_SEEDS.start,
                           contract.PROPOSED_FINAL_SEEDS.stop - 1],
        "final_status": "PROPOSED; never executed; separate owner approval required",
        "enforcement": "SearchEnv rejects every seed outside development and validation",
        "profile_and_smoke_seeds": "12900-12999 development",
        "other_recorded_allocations": {"model2 pilot": "101-106, 201-202, test 42-46",
                                       "research development": "1801-1802",
                                       "phase11h": "3000-3079", "phase11j": "3500"},
        "legacy_reserved_exposure": {
            "42": "EXPOSED: default scenario seed; existing tests; Phase 11J test and profile",
            "43": "recorded use in tests/integration/test_field_scenarios.py",
            "44": "recorded use in tests/integration/test_system_integration.py",
            "45": "recorded use in tests/integration/test_system_integration.py",
            "46": "listed in the model2 pilot test split",
            "evidence_limit": "source search and reports only; not exhaustive. None of 42-46 "
                              "should be described as strictly unseen without owner review. "
                              "Earlier full-suite runs, including Phase 11J, executed these tests."},
        "historical_protocols_modified": False,
    })
    write("readiness_audit.json", {
        "reset": "Engine.reset(seed) rebuilds world state; SearchEnv builds a new Engine and Fleet",
        "stepping": "Fleet.advance: network, assignments, agent cycles, Engine.step",
        "actions": "Move 0-9; policy subset 0-4",
        "observations": "Packet per agent from sense(); latency and dropout supported",
        "memory": "per-agent bounded Memory with TTL",
        "coordination": list(BASELINES),
        "communication": "SimulationNetwork over Router: delay, loss, outage, partition",
        "termination": "retirement at battery <= 20 or horizon",
        "seeds": "named Random streams from the episode seed",
        "metrics": "evaluation/results.py and router.metrics()",
        "scenarios": "configs/scenarios/*.json",
        "safety": "agents/drone_agent/safety.py and Engine.step vetoes",
        "reused": ["Engine", "Fleet", "SimulationNetwork", "coordination baselines",
                   "experiment_runner.episode", "authorize"],
        "pre_existing_env": "simulation/adapters/parallel.RescueEnv: 4-value observation, "
                            "bypasses agents, memory and network; left unchanged",
        "limits": ["movement is disabled by default and is enabled only inside SearchEnv",
                   "independent baseline never moves",
                   "horizon 30 at 12x10 limits coverage",
                   "one peer finding per agent tick; peers share no positions",
                   "single-threaded Python; vectorization would need processes"],
        "revision": revision(),
    })
    print("[contracts] written", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("smoke", "baseline", "profile", "contracts"))
    command = parser.parse_args().command
    if command == "baseline":
        baseline(OUTPUT)
    else:
        {"smoke": smoke, "profile": profile, "contracts": contracts}[command]()


if __name__ == "__main__":
    main()
