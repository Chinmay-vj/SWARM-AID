"""Phase 12I: statistics over recorded Phase 12H episodes and a bounded integration probe.

    python -m evaluation.marl_compare analyze       (reads existing records; runs no episode)
    python -m evaluation.marl_compare integration   (frozen policies, seeds 12960-12962)
"""

import argparse
import csv
import hashlib
import json
from collections import Counter
from itertools import product
from pathlib import Path
from random import Random
from statistics import mean, median, stdev
from typing import Any

import torch

from agents.command_agent.agent import CommandAgent
from agents.command_agent.agent import Settings as CommandSettings
from communication.messages import HumanOverride
from evaluation.marl_robustness import CONDITIONS, LEARNED, POLICIES, SCENARIOS, frozen
from simulation.adapters import marl_contract as contract
from simulation.adapters.marl import SearchEnv
from simulation.core.configuration import load

SOURCE = Path("D:/SWARM-AID-DATA/runs/phase12/phase12h/robustness_episodes.jsonl")
OUTPUT = Path("D:/SWARM-AID-DATA/runs/phase12/phase12i")
BASELINES = tuple(p for p in POLICIES if p not in LEARNED)
METRICS = ("coverage", "coverage_auc", "accessible_coverage", "reward_total", "network_bytes",
           "observations_reported", "policy_rejected_actions", "engine_invalid",
           "safety_interventions", "blocked_cell_agent_ticks", "shared_cell_agent_ticks")
FIELD = ("field_variation", "field_indistinct")


def describe(values: list[float]) -> dict[str, float | int]:
    return {"n": len(values), "mean": mean(values), "median": median(values),
            "sd": stdev(values) if len(values) > 1 else 0.0,
            "min": min(values), "max": max(values)}


def paired(differences: list[float]) -> dict[str, Any]:
    """Percentile bootstrap over evaluation episodes, conditional on the two fixed policies."""
    rng = Random("phase12i")
    means = sorted(mean(rng.choices(differences, k=len(differences))) for _ in range(4000))
    return describe(differences) | {
        "interval95_episodes_only": [means[99], means[3899]],
        "higher": sum(d > 1e-12 for d in differences),
        "tied": sum(abs(d) <= 1e-12 for d in differences),
        "lower": sum(d < -1e-12 for d in differences),
    }


def analyze() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    raw = SOURCE.read_bytes()
    rows = [json.loads(x) for x in raw.decode().splitlines()]
    index = {(r["condition"], r["scenario"], r["seed"], r["policy"]): r for r in rows}
    seeds = sorted({r["seed"] for r in rows})
    expected = len(CONDITIONS) * len(SCENARIOS) * len(seeds) * len(POLICIES)
    if len(index) != len(rows) or len(rows) != expected:
        raise ValueError("recorded episodes are not a complete matched design")
    summary: dict[str, Any] = {}
    statistics: dict[str, Any] = {}
    wide: list[dict[str, Any]] = []
    for condition in CONDITIONS:
        cells = list(product(SCENARIOS, seeds))
        group = {p: [index[condition, s, n, p] for s, n in cells] for p in POLICIES}
        summary[condition] = {
            p: {k: describe([r[k] for r in g]) for k in METRICS} | {
                "episodes": len(g),
                "termination": dict(Counter(r["reason"] for r in g)),
                "distinct_coverage_traces": len({tuple(r["coverage_by_tick"]) for r in g}),
                "weak_comparator": p == "independent",
            } for p, g in group.items()
        }
        comparisons = [("ippo", "mappo"), *product(LEARNED, BASELINES)]
        statistics[condition] = {
            f"{a}_minus_{b}": {
                f"{metric}_points": paired(
                    [100 * (x[metric] - y[metric])
                     for x, y in zip(group[a], group[b], strict=True)])
                for metric in ("coverage", "coverage_auc")
            } for a, b in comparisons
        }
        statistics[condition]["both_learned_at_full_coverage"] = sum(
            x["coverage"] == y["coverage"] == 1.0
            for x, y in zip(group["ippo"], group["mappo"], strict=True))
        for i, (scenario, seed) in enumerate(cells):
            row: dict[str, Any] = {"condition": condition, "scenario": scenario, "seed": seed,
                                   "reward_version": "reward-2", "agents": 6, "horizon": 30}
            for p in POLICIES:
                for k in (*METRICS, "reason"):
                    row[f"{p}_{k}"] = group[p][i][k]
            wide.append(row)
    sensitivity = {
        condition: {
            p: mean(index[condition, s, n, p]["coverage"]
                    for s, n in product(("flood", "wildfire"), seeds)) for p in POLICIES
        } for condition in FIELD
    }
    provenance = {"source": str(SOURCE), "sha256": hashlib.sha256(raw).hexdigest(),
                  "episodes": len(rows), "new_episodes_run": 0, "seeds": seeds}
    (OUTPUT / "matched_baseline_results.json").write_text(json.dumps({
        "provenance": provenance, "reward_version": "reward-2",
        "note": "independent is a weak comparator; heuristic and learned reward and rejection "
                "counts use different action paths and are not like-for-like",
        "summary": summary}, indent=2), encoding="utf8")
    (OUTPUT / "statistical_analysis.json").write_text(json.dumps({
        "provenance": provenance, "unit": "one matched scenario-seed episode",
        "scope": "conditional on one trained run per algorithm; intervals say nothing about "
                 "retraining. No hypothesis test, superiority or equivalence claim. Intervals "
                 "are unadjusted for the many comparisons.",
        "auc": "mean coverage over ticks 1-30, from recorded coverage_by_tick",
        "auc_unavailable_for": "Phase 12G training and validation (no tick traces recorded)",
        "nominal": statistics["nominal"],
        "robustness": {k: v for k, v in statistics.items() if k != "nominal"},
        "post_hoc_field_coverage_without_earthquake": sensitivity,
    }, indent=2), encoding="utf8")
    with (OUTPUT / "comparative_episode_metrics.csv").open("w", newline="", encoding="utf8") as f:
        writer = csv.DictWriter(f, fieldnames=list(wide[0]))
        writer.writeheader()
        writer.writerows(wide)
    figure(index, seeds)
    tables(summary, statistics)
    for condition, s in statistics.items():
        shown = []
        for name in ("ippo_minus_mappo", "ippo_minus_shared_information",
                     "mappo_minus_shared_information"):
            e = s[name]["coverage_auc_points"]
            low, high = e["interval95_episodes_only"]
            shown.append(f"{e['mean']:+.1f}[{low:+.1f},{high:+.1f}]")
        print(condition, "auc", *shown, "full", s["both_learned_at_full_coverage"],
              "traces", {p: summary[condition][p]["distinct_coverage_traces"] for p in LEARNED})
    print(json.dumps(sensitivity))


def tables(summary: dict[str, Any], statistics: dict[str, Any]) -> None:
    lines = ["# Matched development comparison (reward-2, 15 episodes per cell)", "",
             "Coverage AUC (mean coverage over ticks 1-30), percent. Independent is weak.", "",
             "| Condition | " + " | ".join(POLICIES) + " |",
             "|---|" + "---:|" * len(POLICIES)]
    for condition, group in summary.items():
        lines.append(f"| {condition} | " + " | ".join(
            f"{100 * group[p]['coverage_auc']['mean']:.1f}" for p in POLICIES) + " |")
    lines += ["", "Paired AUC difference in points; brackets resample episodes only.", "",
              "| Condition | IPPO - MAPPO | IPPO - shared | MAPPO - shared |",
              "|---|---:|---:|---:|"]
    for condition, s in statistics.items():
        row = [condition]
        for name in ("ippo_minus_mappo", "ippo_minus_shared_information",
                     "mappo_minus_shared_information"):
            e = s[name]["coverage_auc_points"]
            low, high = e["interval95_episodes_only"]
            row.append(f"{e['mean']:+.1f} [{low:+.1f}, {high:+.1f}]")
        lines.append("| " + " | ".join(row) + " |")
    (OUTPUT / "comparison_tables.md").write_text("\n".join(lines) + "\n", encoding="utf8")


STYLE = {"ippo": ("#2a78d6", "", "IPPO"), "mappo": ("#eb6834", "", "MAPPO"),
         "shared_information": ("#1baf7a", "", "Shared information"),
         "fixed_sector": ("#eda100", "7 4", "Fixed sector"),
         "random_masked": ("#52514e", "2 3", "Random"),
         "independent": ("#a3a29c", "", "Independent (weak)")}


def figure(index: dict[tuple[str, str, int, str], Any], seeds: list[int]) -> None:
    width, height, panel_w, panel_h = 1000, 1010, 400, 130
    title = ("Mean sensed coverage by tick, 15 matched episodes per condition "
             "(one trained run per algorithm)")
    root = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            'font-family="system-ui,sans-serif" font-size="12">')
    svg = [root, f'<rect width="{width}" height="{height}" fill="#fcfcfb"/>',
           f'<text x="50" y="24" font-size="16" fill="#0b0b0b">{title}</text>']
    for i, (color, dash, label) in enumerate(STYLE.values()):
        x = 50 + 150 * i
        svg.append(f'<line x1="{x}" x2="{x + 22}" y1="45" y2="45" stroke="{color}" '
                   f'stroke-width="2" stroke-dasharray="{dash}"/>'
                   f'<text x="{x + 28}" y="49" fill="#52514e">{label}</text>')
    for n, condition in enumerate(CONDITIONS):
        left, top = 50 + (n % 2) * 490, 90 + (n // 2) * 184
        svg.append(f'<text x="{left}" y="{top - 10}" fill="#0b0b0b">'
                   f'{condition.replace("_", " ")}</text>')
        for k in range(5):
            y = top + panel_h - panel_h * k / 4
            svg.append(f'<line x1="{left}" x2="{left + panel_w}" y1="{y}" y2="{y}" '
                       f'stroke="#e1e0d9"/><text x="{left - 6}" y="{y + 4}" text-anchor="end" '
                       f'fill="#52514e">{25 * k}%</text>')
        for tick in (0, 10, 20, 30):
            svg.append(f'<text x="{left + panel_w * tick / 30}" y="{top + panel_h + 16}" '
                       f'text-anchor="middle" fill="#52514e">{tick}</text>')
        for policy, (color, dash, _) in STYLE.items():
            traces = [index[condition, s, seed, policy]["coverage_by_tick"]
                      for s, seed in product(SCENARIOS, seeds)]
            points = " ".join(
                f"{left + panel_w * t / 30:.1f},{top + panel_h * (1 - mean(v)):.1f}"
                for t, v in enumerate(zip(*traces, strict=True)))
            svg.append(f'<polyline points="{points}" fill="none" stroke="{color}" '
                       f'stroke-width="2" stroke-dasharray="{dash}"/>')
    svg.append('<text x="500" y="1000" text-anchor="middle" fill="#52514e">tick</text></svg>')
    (OUTPUT / "coverage_by_tick.svg").write_text("\n".join(svg), encoding="utf8")


def episode(scenario: str, seed: int, algorithm: str, pause: bool) -> dict[str, Any]:
    """SearchEnv with the existing Model 2 attached. `pause` pauses every drone at tick 3."""
    model, _ = frozen(algorithm)
    env = SearchEnv(load(f"{scenario}_basic"),
                    reward=contract.RewardConfig(version="reward-2"))
    observations, infos = env.reset(seed=seed)
    engine, fleet = env.engine, env.fleet
    assert fleet.network is not None
    command = CommandAgent(engine.mission_id, frozenset(engine.drones), CommandSettings())
    fleet.command = command
    moves_after = 0
    while env.agents:
        if pause and engine.t == 3:
            override = HumanOverride(message_type="human_override", action="pause", reason="probe")
            for target in engine.drones:
                fleet.network.issue("operator", override, target,
                                    engine.config.horizon * engine.config.tick_ms, revision=0)
        local = torch.stack([torch.from_numpy(observations[a]) for a in env.agents])
        mask = torch.stack([torch.from_numpy(infos[a]["action_mask"]) for a in env.agents])
        with torch.no_grad():
            chosen = model.policy(local, mask.bool()).argmax(-1)
        before = {a: d.position for a, d in engine.drones.items()}
        observations, _, _, _, infos = env.step(
            {a: int(contract.ACTIONS[int(chosen[i])]) for i, a in enumerate(env.agents)})
        if engine.t > 8:  # well after delivery of a tick-3 instruction
            moves_after += sum(d.position != before[a] for a, d in engine.drones.items())
    supported = {e.evidence_id for r in command.findings.values()
                 for e in r.finding.observation.evidence}
    recommendations = [u.recommendation for u in command.incidents.values() if u.recommendation]
    return {
        "coverage": env.episode_metrics()["coverage"],
        "moves_after_tick_8": moves_after,
        "drone_overrides": sorted({a.override for a in fleet.agents.values()}),
        "findings": len(command.findings),
        "incidents": len(command.incidents),
        "categories": dict(Counter(str(u.incident.category.value)
                                   for u in command.incidents.values())),
        "dispositions": dict(Counter(command.dispositions.values())),
        "recommendations": len(recommendations),
        "recommendation_evidence_supported": all(
            set(r.evidence_ids) <= supported for r in recommendations),
        "finding_origins_are_agents": all(
            e.origin in engine.drones for r in command.findings.values()
            for e in r.finding.observation.evidence),
    }


def mission_pause_fixture(scenario: str, seed: int, algorithm: str) -> dict[str, Any]:
    """Same probe with Fleet built the way the backend builds it, so mission pause is accepted."""
    model, _ = frozen(algorithm)
    env = SearchEnv(load(f"{scenario}_basic"))
    observations, infos = env.reset(seed=seed)
    engine = env.engine
    env.fleet = fleet = type(env.fleet)(engine, communication=True, command=CommandSettings())
    assert fleet.network is not None and fleet.assignments is not None
    moves_after = 0
    while env.agents:
        if engine.t == 3:
            fleet.network.issue(
                "operator",
                HumanOverride(message_type="human_override", action="pause", reason="probe"),
                "command", engine.config.horizon * engine.config.tick_ms, revision=0)
        local = torch.stack([torch.from_numpy(observations[a]) for a in env.agents])
        mask = torch.stack([torch.from_numpy(infos[a]["action_mask"]) for a in env.agents])
        with torch.no_grad():
            chosen = model.policy(local, mask.bool()).argmax(-1)
        before = {a: d.position for a, d in engine.drones.items()}
        paused = any(state == "paused" for _, state in fleet.assignments.transitions)
        observations, _, _, _, infos = env.step(
            {a: int(contract.ACTIONS[int(chosen[i])]) for i, a in enumerate(env.agents)})
        if paused:
            moves_after += sum(d.position != before[a] for a, d in engine.drones.items())
    return {"mission_paused": any(s == "paused" for _, s in fleet.assignments.transitions),
            "moves_while_paused": moves_after,
            "drone_overrides": sorted({a.override for a in fleet.agents.values()})}


def integration() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if (OUTPUT / "integration_probe.json").exists():
        raise FileExistsError("the pre-fix Phase 12I probe is historical evidence; not overwritten")
    torch.set_num_threads(1)
    runs = []
    for (i, scenario), algorithm in product(enumerate(SCENARIOS), LEARNED):
        seed = 12960 + i
        contract.require_open_seed(seed)
        row = {"scenario": scenario, "seed": seed, "algorithm": algorithm,
               "no_pause": episode(scenario, seed, algorithm, False),
               "per_drone_pause": episode(scenario, seed, algorithm, True),
               "mission_pause": mission_pause_fixture(scenario, seed, algorithm)}
        runs.append(row)
        print(json.dumps(row), flush=True)
    (OUTPUT / "integration_probe.json").write_text(json.dumps(runs, indent=2), encoding="utf8")
    print("[done]")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("analyze", "integration"))
    {"analyze": analyze, "integration": integration}[parser.parse_args().command]()


if __name__ == "__main__":
    main()
