"""Configuration-driven integration experiment matrix (Phase 9 smoke and extended profiles).

A plan is a list of blocks; each block is a small cartesian product of scenarios, agent counts,
seeds, coordination baselines and Model 2 modes. Every combination is reported as completed,
failed or unsupported; nothing is silently dropped. Determinism is checked by re-running the
first seed of each (block, scenario, agents) cell and comparing operational fingerprints.

These are untrained-system baselines for infrastructure verification, not research results.
Phase 5 (evaluation.experiment_runner) and Phase 6 (evaluation.command_agent_experiments)
runners remain the matched-sample research runners; `python -m orchestration experiment`
dispatches to them.
"""

import csv
import json
import statistics
from collections import Counter, defaultdict
from itertools import product
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, ValidationError, model_validator

from backend.integrations.simulation_adapter import MissionConfig
from orchestration.headless import run_mission
from orchestration.manifest import manifest
from simulation.adapters.coordination import PolicyName

CommandMode = Literal["direct", "rules", "fusion"]


class Block(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=64)
    scenarios: tuple[str, ...] = Field(min_length=1)
    agents: tuple[PositiveInt, ...] = Field(min_length=1)
    seeds: tuple[int, ...] = Field(min_length=1)
    coordination: tuple[PolicyName, ...] = ("shared_information",)
    command_modes: tuple[CommandMode, ...] = ("fusion",)

    @model_validator(mode="after")
    def distinct(self) -> "Block":
        for field in ("scenarios", "agents", "seeds", "coordination", "command_modes"):
            values = getattr(self, field)
            if len(set(values)) != len(values):
                raise ValueError(f"duplicate {field} levels would repeat matched samples")
        return self

    def size(self) -> int:
        return (
            len(self.scenarios)
            * len(self.agents)
            * len(self.seeds)
            * len(self.coordination)
            * len(self.command_modes)
        )


class MatrixPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    profile: Literal["smoke", "extended"]
    description: str = ""
    blocks: tuple[Block, ...] = Field(min_length=1)
    check_determinism: bool = True
    max_runs: PositiveInt = 400

    @model_validator(mode="after")
    def bounded(self) -> "MatrixPlan":
        total = sum(b.size() for b in self.blocks)
        if total > self.max_runs:
            raise ValueError(f"plan has {total} runs, above max_runs {self.max_runs}")
        if len({b.name for b in self.blocks}) != len(self.blocks):
            raise ValueError("block names must be unique")
        return self


FLAT_FIELDS = (
    "block",
    "scenario",
    "agents",
    "seed",
    "coordination",
    "command_mode",
    "status",
    "reason",
    "end_reason",
    "ticks",
    "sim_time_ms",
    "wall_clock_ms",
    "step_ms_mean",
    "step_ms_p95",
    "step_ms_p99",
    "router_pending_max",
    "delivery_ratio",
    "messages_generated",
    "messages_dropped",
    "model2_admitted_findings",
    "model2_incidents",
    "tasks_issued",
    "agent_reported_cells",
    "evaluator_coverage",
    "evaluator_people_observed",
    "fingerprint",
)


def _flat(block: str, run: dict[str, Any]) -> dict[str, Any]:
    c = run["configuration"]
    row: dict[str, Any] = {
        "block": block,
        "scenario": c["scenario_id"],
        "agents": c["agents"],
        "seed": c["seed"],
        "coordination": c["coordination"],
        "command_mode": c["command_mode"],
        "status": run["status"],
        "reason": run.get("reason"),
    }
    if run["status"] != "completed":
        return row
    perf, op, ev = run["performance"], run["operational"], run["evaluator_only"]["metrics"]
    row.update(
        end_reason=run["end_reason"],
        ticks=run["ticks"],
        sim_time_ms=run["sim_time_ms"],
        wall_clock_ms=perf["wall_clock_ms"],
        step_ms_mean=perf["step_ms"]["mean"],
        step_ms_p95=perf["step_ms"]["p95"],
        step_ms_p99=perf["step_ms"]["p99"],
        router_pending_max=perf["router_pending"]["max"],
        delivery_ratio=op["communication"].get("delivery_ratio"),
        messages_generated=op["communication"].get("generated"),
        messages_dropped=op["communication"].get("dropped"),
        model2_admitted_findings=op["model2_admitted_findings"],
        model2_incidents=op["model2_incidents"],
        tasks_issued=op["tasks_issued"],
        agent_reported_cells=op["agent_reported_cells"],
        evaluator_coverage=ev["coverage"],
        evaluator_people_observed=ev["people_observed"],
        fingerprint=run["fingerprint"],
    )
    return row


def execute(config_values: dict[str, Any]) -> dict[str, Any]:
    """Run one combination; classify invalid configurations as unsupported."""
    try:
        config = MissionConfig(**config_values)
        config.validated()
    except (ValidationError, ValueError) as exc:
        reason = str(exc).splitlines()[0][:200]
        return {"configuration": config_values, "status": "unsupported", "reason": reason}
    try:
        result = run_mission(config)
    except Exception as exc:  # noqa: BLE001 - a failed run is a reported outcome
        return {
            "configuration": config.model_dump(mode="json"),
            "status": "failed",
            "reason": f"{type(exc).__name__}: {exc}"[:200],
        }
    return result | {"status": "completed", "reason": None}


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 4) if values else None


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (
            row["block"],
            row["scenario"],
            row["agents"],
            row["coordination"],
            row["command_mode"],
        )
        groups[key].append(row)
    out = []
    for (block, scenario, agents, coordination, mode), members in groups.items():
        done = [r for r in members if r["status"] == "completed"]

        def values(field: str, done: list[dict[str, Any]] = done) -> list[float]:
            return [float(r[field]) for r in done if r.get(field) is not None]

        out.append(
            {
                "block": block,
                "scenario": scenario,
                "agents": agents,
                "coordination": coordination,
                "command_mode": mode,
                "runs": len(members),
                "completed": len(done),
                "failed": sum(r["status"] == "failed" for r in members),
                "unsupported": sum(r["status"] == "unsupported" for r in members),
                "step_ms_mean": _mean(values("step_ms_mean")),
                "step_ms_p95_max": max(values("step_ms_p95"), default=None),
                "wall_clock_ms_mean": _mean(values("wall_clock_ms")),
                "delivery_ratio_mean": _mean(values("delivery_ratio")),
                "model2_incidents_mean": _mean(values("model2_incidents")),
                "evaluator_coverage_mean": _mean(values("evaluator_coverage")),
                "evaluator_coverage_sd": (
                    round(statistics.stdev(values("evaluator_coverage")), 4)
                    if len(values("evaluator_coverage")) > 1
                    else None
                ),
            }
        )
    return out


def run_matrix(plan: MatrixPlan, directory: Path) -> Path:
    folder = directory / uuid4().hex
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(
        json.dumps(manifest("phase9-matrix", plan.model_dump(mode="json")), indent=2),
        encoding="utf-8",
    )
    rows: list[dict[str, Any]] = []
    determinism: list[dict[str, Any]] = []
    with (folder / "runs.jsonl").open("w", encoding="utf-8") as stream:
        for block in plan.blocks:
            repeated: set[tuple[str, int]] = set()
            for scenario, agents, seed, coordination, mode in product(
                block.scenarios,
                block.agents,
                block.seeds,
                block.coordination,
                block.command_modes,
            ):
                values = {
                    "scenario_id": scenario,
                    "agents": agents,
                    "seed": seed,
                    "coordination": coordination,
                    "command_mode": mode,
                }
                run = execute(values)
                stream.write(json.dumps({"block": block.name} | run, default=str) + "\n")
                rows.append(_flat(block.name, run))
                if (
                    plan.check_determinism
                    and run["status"] == "completed"
                    and (scenario, agents) not in repeated
                ):
                    repeated.add((scenario, agents))
                    again = execute(values)
                    determinism.append(
                        {
                            "block": block.name,
                            "scenario": scenario,
                            "agents": agents,
                            "seed": seed,
                            "coordination": coordination,
                            "command_mode": mode,
                            "first": run["fingerprint"],
                            "repeat": again.get("fingerprint"),
                            "identical": again.get("fingerprint") == run["fingerprint"],
                        }
                    )
    with (folder / "runs.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FLAT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    summary = summarize(rows)
    with (folder / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
        if summary:
            writer = csv.DictWriter(stream, fieldnames=list(summary[0]))
            writer.writeheader()
            writer.writerows(summary)
    with (folder / "determinism.csv").open("w", newline="", encoding="utf-8") as stream:
        fields = [
            "block",
            "scenario",
            "agents",
            "seed",
            "coordination",
            "command_mode",
            "first",
            "repeat",
            "identical",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(determinism)
    statuses = Counter(r["status"] for r in rows)
    (folder / "summary.json").write_text(
        json.dumps(
            {
                "plan": plan.name,
                "profile": plan.profile,
                "runs": len(rows),
                "status_counts": dict(statuses),
                "determinism_checks": len(determinism),
                "determinism_identical": sum(d["identical"] for d in determinism),
                "groups": summary,
                "note": "Untrained-system integration baselines; not research results.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return folder
