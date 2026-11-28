"""Phase 12H frozen-policy development evaluation and diagnostics. No training.

    python -u -m evaluation.marl_robustness run --pilot   (one seed per cell)
    python -u -m evaluation.marl_robustness run           (resumable)
    python -u -m evaluation.marl_robustness analyze
    python -u -m evaluation.marl_robustness diagnostics
"""

import argparse
import csv
import hashlib
import json
import time
from itertools import product
from pathlib import Path
from random import Random
from statistics import mean, stdev
from typing import Any

import torch

from evaluation import marl_train as launcher
from evaluation.marl_ppo import ActorCritic
from simulation.adapters import marl_contract as contract
from simulation.adapters.marl import SearchEnv
from simulation.core.configuration import Scenario, load
from simulation.core.engine import Engine
from simulation.environments.base import BLOCKED

DATA = Path("D:/SWARM-AID-DATA")
OUTPUT = DATA / "runs/phase12/phase12h"
CHECKPOINTS = DATA / "checkpoints/phase12"
LEARNED = ("ippo", "mappo")
POLICIES = (*LEARNED, "independent", "fixed_sector", "shared_information", "random_masked")
SCENARIOS = ("flood", "wildfire", "earthquake")
SEEDS = range(13100, 13105)  # validation namespace; not used for checkpoint selection
AGENTS, HORIZON = 6, 30
# condition -> (scenario suffix, overrides). Every override is an existing Scenario field.
CONDITIONS: dict[str, tuple[str, dict[str, Any]]] = {
    "nominal": ("basic", {}),
    "missing_observations": ("basic", {"dropout": 0.2}),
    "noisy_detections": ("basic", {"noise": 0.3, "false_positive": 0.1}),
    "message_loss": ("basic", {"loss": 0.35}),
    "message_delay": ("basic", {"delay": 3, "network": {"jitter": 2}}),
    "radio_outage_partition": ("basic", {"outage_steps": [3, 4, 5], "partition": True}),
    "agent_disconnected": ("basic", {"network": {"endpoint_down": {"d1": [4, 5, 6]}}}),
    "agent_unavailable": ("basic", {"unavailable": [1]}),
    "field_variation": ("field", {}),
    "field_indistinct": ("field", {"noise": 0.3, "false_positive": 0.1}),
}


def configuration(condition: str, scenario: str) -> Scenario:
    suffix, changes = CONDITIONS[condition]
    base = load(f"{scenario}_{suffix}").model_dump()
    return Scenario.model_validate(base | {"agents": AGENTS, "horizon": HORIZON} | changes)


def frozen(algorithm: str) -> tuple[ActorCritic, str]:
    path = CHECKPOINTS / f"{algorithm}-s1" / "latest.pt"
    saved = torch.load(path, map_location="cpu", weights_only=True)
    name: Any = algorithm
    current = launcher.identity(name, saved["identity"]["config"], saved["identity"]["seed"])
    if saved["identity"] != current | {"smoke": False}:
        raise ValueError(f"{algorithm}: checkpoint identity differs from current sources")
    model = ActorCritic(name, saved["identity"]["config"]["hidden"])
    model.load_state_dict(saved["model"], strict=True)
    model.eval()
    return model, hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate(config: Scenario, policy: str, seed: int, model: ActorCritic | None) -> dict[str, Any]:
    coordination: Any = None if policy in (*LEARNED, "random_masked") else policy
    env = SearchEnv(config, coordination=coordination,
                    reward=contract.RewardConfig(version="reward-2"))
    observations, infos = env.reset(seed=seed)
    engine = env.engine
    cells = len(engine.world.tiles)
    curve = [len(engine.covered) / cells]
    chooser = Random(f"policy/{seed}")
    shared_cell_ticks = blocked_ticks = 0
    while env.agents:
        actions: dict[str, int] = {}
        if model is not None:
            local = torch.stack([torch.from_numpy(observations[a]) for a in env.agents])
            mask = torch.stack([torch.from_numpy(infos[a]["action_mask"]) for a in env.agents])
            with torch.no_grad():
                chosen = model.policy(local, mask.bool()).argmax(-1)
            actions = {a: int(contract.ACTIONS[int(chosen[i])]) for i, a in enumerate(env.agents)}
        elif policy == "random_masked":
            for a in env.agents:
                allowed = [i for i, ok in enumerate(infos[a]["action_mask"]) if ok and i]
                actions[a] = chooser.choice(allowed) if allowed else 0
        observations, _, _, _, infos = env.step(actions)
        curve.append(len(engine.covered) / cells)
        positions = [d.position for d in engine.drones.values()]
        shared_cell_ticks += len(positions) - len(set(positions))
        blocked_ticks += sum(engine.world.tiles[p] in BLOCKED for p in positions)
    metrics = env.episode_metrics()
    free = {p for p, tile in engine.world.tiles.items() if tile not in BLOCKED}

    def first(threshold: float) -> int | None:
        return next((t for t, value in enumerate(curve) if value >= threshold), None)

    return metrics | {
        "accessible_coverage": len(engine.covered & free) / len(free),
        "coverage_auc": mean(curve[1:]),
        "initial_coverage": curve[0],
        "coverage_at_tick_5": curve[min(5, len(curve) - 1)],
        "coverage_at_tick_10": curve[min(10, len(curve) - 1)],
        "ticks_to_90": first(0.9),
        "ticks_to_99": first(0.99),
        "indistinct_cells": len(env.unclear),
        "resolved_cells": len(env.resolved),
        "corroborated_cells": len(env.corroborated),
        "shared_cell_agent_ticks": shared_cell_ticks,
        "blocked_cell_agent_ticks": blocked_ticks,
        "coverage_by_tick": curve,
    }


def run(pilot: bool) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(1)
    log = OUTPUT / "robustness_episodes.jsonl"
    models = {name: frozen(name) for name in LEARNED}
    source = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    done = set()
    if log.is_file():
        for line in log.read_text("utf8").splitlines():
            row = json.loads(line)
            done.add((row["condition"], row["scenario"], row["policy"], row["seed"]))
    seeds = SEEDS[:1] if pilot else SEEDS
    plan = [p for p in product(CONDITIONS, SCENARIOS, POLICIES, seeds) if p not in done]
    started = time.perf_counter()
    for index, (condition, scenario, policy, seed) in enumerate(plan, start=1):
        contract.require_open_seed(seed)
        model, checkpoint = models.get(policy, (None, None))
        row = {
            "condition": condition, "scenario": scenario, "policy": policy, "seed": seed,
            "checkpoint_sha256": checkpoint, "evaluator_sha256": source,
        } | evaluate(configuration(condition, scenario), policy, seed, model)
        with log.open("a", encoding="utf8") as stream:
            stream.write(json.dumps(row) + "\n")
        elapsed = time.perf_counter() - started
        print(f"[eval] {index}/{len(plan)} condition={condition} scenario={scenario} "
              f"policy={policy} seed={seed} coverage={row['coverage']:.3f} "
              f"reward={row['reward_total']:.2f} invalid={row['engine_invalid']} "
              f"elapsed_s={elapsed:.0f} eta_s={elapsed / index * (len(plan) - index):.0f}",
              flush=True)
    print(f"[done] new_episodes={len(plan)} seconds={time.perf_counter() - started:.0f}")


def describe(values: list[float]) -> dict[str, float | int]:
    return {"n": len(values), "mean": mean(values),
            "sd": stdev(values) if len(values) > 1 else 0.0,
            "min": min(values), "max": max(values)}


def analyze() -> None:
    rows = [json.loads(x) for x in
            (OUTPUT / "robustness_episodes.jsonl").read_text("utf8").splitlines()]
    columns = [k for k in rows[0] if k != "coverage_by_tick"]
    with (OUTPUT / "robustness_episode_metrics.csv").open("w", newline="", encoding="utf8") as out:
        writer = csv.DictWriter(out, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    numeric = [k for k in columns
               if k != "seed" and any(isinstance(r[k], (int, float)) for r in rows)]
    summary: dict[str, Any] = {}
    for condition, policy in product(CONDITIONS, POLICIES):
        group = [r for r in rows if r["condition"] == condition and r["policy"] == policy]
        entry: dict[str, Any] = {
            "episodes": len(group),
            "termination": sorted({r["reason"] for r in group}),
            "reached_99": sum(r["ticks_to_99"] is not None for r in group),
        }
        for k in numeric:
            values = [r[k] for r in group if r[k] is not None]
            if values:
                entry[k] = describe(values)
        summary.setdefault(condition, {})[policy] = entry
    paired: dict[str, Any] = {}
    index = {(r["condition"], r["scenario"], r["seed"], r["policy"]): r for r in rows}
    for condition in CONDITIONS:
        cells = sorted({(r["scenario"], r["seed"]) for r in rows if r["condition"] == condition})
        paired[condition] = {
            k: describe([index[condition, s, n, "ippo"][k] - index[condition, s, n, "mappo"][k]
                         for s, n in cells])
            for k in ("coverage", "coverage_auc", "reward_total", "engine_invalid")
        }
    (OUTPUT / "robustness_results.json").write_text(json.dumps({
        "label": "exploratory development findings; one learner seed per algorithm",
        "variation": "sd and range are across scenario/seed episodes, not learner runs",
        "agents": AGENTS, "horizon": HORIZON, "reward_version": "reward-2",
        "seeds": sorted({r["seed"] for r in rows}), "episodes": len(rows),
        "conditions": {k: {"scenario_set": v[0], "overrides": v[1]}
                       for k, v in CONDITIONS.items()},
        "unsupported": ["contradictory evidence as a controlled, separately injected condition",
                        "distress confirmation or rescue outcome metrics",
                        "moving or failing hardware, physical flight"],
        "action_path": "learned and random use the policy-lease gate; heuristics use Fleet",
        "checkpoints": {n: frozen(n)[1] for n in LEARNED},
        "summary": summary, "paired_ippo_minus_mappo": paired,
    }, indent=2), encoding="utf8")
    for condition, group in summary.items():
        print(condition)
        for policy, e in group.items():
            print(f"  {policy:19s} n={e['episodes']} cov={e['coverage']['mean']:.3f}"
                  f"±{e['coverage']['sd']:.3f} auc={e['coverage_auc']['mean']:.3f} "
                  f"t99={e['ticks_to_99']['mean'] if 'ticks_to_99' in e else float('nan'):.1f}"
                  f"({e['reached_99']}) rew={e['reward_total']['mean']:.2f} "
                  f"inv={e['engine_invalid']['mean']:.1f} "
                  f"rej={e['policy_rejected_actions']['mean']:.1f} "
                  f"KB={e['network_bytes']['mean'] / 1000:.0f} "
                  f"unc={e['indistinct_cells']['mean']:.0f}/{e['resolved_cells']['mean']:.0f} "
                  f"blocked={e['blocked_cell_agent_ticks']['max']}")


def diagnostics() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    config = launcher.load_config(launcher.DEFAULT_CONFIG, False)
    names = config["scenarios"]

    def layout(name: str, seed: int) -> tuple[Any, ...]:
        e = Engine(Scenario.model_validate(load(name).model_dump() | {
            "agents": config["agents"], "horizon": config["horizon"], "seed": seed}))
        starts = tuple(d.position for d in e.drones.values())
        blocked = tuple(sorted(p for p, v in e.world.tiles.items() if v in BLOCKED))
        return (name, starts, blocked, tuple(sorted(e.people)), tuple(sorted(e.hazards)))

    train = {(launcher.TRAIN_BASE + (97 + i) % launcher.TRAIN_SPAN, names[i % 3])
             for i in range(10000)}
    training = [layout(n, s) for s, n in sorted(train)]
    validation = [layout(names[i % 3], launcher.VALIDATION_BASE + i) for i in range(9)]
    diversity = {
        "distinct_seed_scenario_pairs": len(train),
        "intended_pairs": launcher.TRAIN_SPAN * len(names),
        "cause": "seed cycle length 900 is divisible by the 3-scenario cycle",
        "pairing_depends_on_learner_seed": "scenario index = (seed offset - learner seed) mod 3",
        "distinct_training_layouts": len(set(training)),
        "per_scenario": {
            n: {
                "pairs": sum(r[0] == n for r in training),
                "distinct_start_sets": len({r[1] for r in training if r[0] == n}),
                "distinct_blocked_maps": len({r[2] for r in training if r[0] == n}),
                "distinct_start_and_blocked": len({r[1:3] for r in training if r[0] == n}),
                "distinct_people_sets": len({r[3] for r in training if r[0] == n}),
                "distinct_hazard_sets": len({r[4] for r in training if r[0] == n}),
            } for n in names
        },
        "authored_terrain_identical_across_scenarios":
            len({json.dumps(load(n).model_dump(mode="json")["terrain"], sort_keys=True)
                 for n in names}) == 1,
        "distinct_start_sets_overall": len({r[1] for r in training}),
        "validation_episodes": len(validation),
        "validation_full_layouts_also_in_training": sum(v in set(training) for v in validation),
        "validation_start_and_blocked_also_in_training":
            sum(v[:3] in {t[:3] for t in training} for v in validation),
        "train_validation_seed_overlap": 0,
        "smoke_training_seed_overlap": 0,
    }
    (OUTPUT / "scenario_diversity_analysis.json").write_text(
        json.dumps(diversity, indent=2), encoding="utf8")
    selection = {}
    for algo in LEARNED:
        records = [json.loads(x) for x in
                   (CHECKPOINTS / f"{algo}-s1" / "metrics.jsonl").read_text("utf8").splitlines()]
        points = [r for r in records if "validation" in r]
        best = max(p["validation"]["coverage"] for p in points)
        tied = [p for p in points if p["validation"]["coverage"] == best]
        chosen = tied[0]
        selection[algo] = {
            "rule": "strictly greater mean validation coverage; first occurrence is kept",
            "validation_points": len(points), "best_coverage": best,
            "selected_update": chosen["update"], "points_tied_at_best": len(tied),
            "tied_later_with_higher_reward": sum(
                p["validation"]["reward_total"] > chosen["validation"]["reward_total"]
                for p in tied[1:]),
            "tied_later_with_fewer_invalid": sum(
                p["validation"]["engine_invalid"] < chosen["validation"]["engine_invalid"]
                for p in tied[1:]),
            "selected": chosen["validation"], "latest": points[-1]["validation"],
        }
        saved = torch.load(CHECKPOINTS / f"{algo}-s1" / "latest.pt",
                           map_location="cpu", weights_only=True)
        (OUTPUT / f"reconstructed_config_{algo}.json").write_text(json.dumps({
            "provenance": "reconstructed from the saved latest.pt identity; not an original file",
            "identity": saved["identity"],
        }, indent=2), encoding="utf8")
    (OUTPUT / "checkpoint_selection_analysis.json").write_text(json.dumps({
        "runs": selection,
        "provisional_candidate": "latest.pt (chosen after seeing 12G results; exploratory)",
        "historical_checkpoints_changed": False,
        "proposed_future_rule": [
            "fix the rule before training",
            "reject candidates with any blocked-cell occupancy",
            "primary: coverage AUC on selection seeds (does not saturate at the horizon)",
            "ties within a pre-set tolerance: fewer rejected moves, then higher reward, then later",
            "report on separate seeds from selection; always keep and report latest as well",
        ],
    }, indent=2), encoding="utf8")
    print(json.dumps(diversity, indent=1))
    print(json.dumps(selection))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "analyze", "diagnostics"))
    parser.add_argument("--pilot", action="store_true", help="first seed only")
    args = parser.parse_args()
    if args.command == "run":
        run(args.pilot)
    else:
        {"analyze": analyze, "diagnostics": diagnostics}[args.command]()


if __name__ == "__main__":
    main()
