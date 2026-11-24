"""Matched-scenario CPU evaluation. Episode artifacts include configuration and policy."""

import argparse
import csv
import json
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from itertools import product
from pathlib import Path
from statistics import mean, median, stdev
from uuid import uuid4

from pydantic import Field, PositiveInt, field_validator

from agents.shared.domain import Record
from communication.messages import PossibleHumanDetection
from evaluation.results import DEFINITIONS, metrics
from simulation.adapters.coordination import PolicyName
from simulation.adapters.model1 import Fleet
from simulation.core.configuration import Scenario, load
from simulation.core.engine import Engine


class Experiment(Record):
    scenarios: tuple[str, ...] = Field(min_length=1)
    agents: tuple[PositiveInt, ...] = Field(min_length=1)
    seeds: tuple[int, ...] = Field(min_length=1)
    policies: tuple[PolicyName, ...] = Field(min_length=1)

    @field_validator("scenarios", "agents", "seeds", "policies")
    @classmethod
    def distinct_levels(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        if len(set(values)) != len(values):
            raise ValueError("duplicate experiment levels would repeat matched samples")
        return values


def episode(config: Scenario, policy: PolicyName) -> dict[str, object]:
    engine = Engine(config)
    fleet = Fleet(engine, coordination=policy)
    assert fleet.network and fleet.assignments
    coverage = [len(engine.covered)]
    while engine.reason == "running":
        fleet.advance(engine)
        coverage.append(len(engine.covered))
    fleet.assignments.expire(engine.t * config.tick_ms)
    states = Counter(t.history[-1].state for t in fleet.assignments.tasks.values())
    return {
        "task_final_states": dict(states),
        "task_completion_rate": (
            states["completed"] / fleet.assignments.issued if fleet.assignments.issued else None
        ),
        "first_reported_sighting_ms": min(
            (
                m.payload.observation.observed_ms
                for m in fleet.network.history["command"]
                if isinstance(m.payload, PossibleHumanDetection)
            ),
            default=None,
        ),
        "task_workload": dict(Counter(t.member for t in fleet.assignments.tasks.values())),
        "safety_interventions": sum(a.health.invalid_actions for a in fleet.agents.values()),
        "availability_history": fleet.assignments.availability_history,
        "repeated_reports": fleet.assignments.repeated_reports,
        "observations_reported": len(fleet.assignments.observations),
        "mission_history": fleet.assignments.transitions,
        "task_history": {
            str(key): [
                asdict(event) | {"evidence": str(event.evidence) if event.evidence else None}
                for event in task.history
            ]
            for key, task in fleet.assignments.tasks.items()
        },
        "coordination_conflicts": [
            (now, str(mid), reason) for now, mid, reason in fleet.assignments.conflicts
        ],
        "first_person_capture_ms": engine.first_seen_ms,
        "cross_agent_duplicate_cells": sum(map(len, engine.covered_by_agent.values()))
        - len(engine.covered),
        "unobserved_cells": len(engine.world.tiles) - len(engine.covered),
        "policy": policy,
        "policy_version": "1",
        "scenario": config.model_dump(mode="json"),
        "settings": next(iter(fleet.agents.values())).settings.model_dump(mode="json"),
        "metrics": metrics(engine),
        "coverage_cells_by_tick": coverage,
        "tasks_issued": fleet.assignments.issued,
        "network": fleet.network.router.metrics(),
    }


def run(plan: Experiment, folder: Path) -> Path:
    output = folder / uuid4().hex
    output.mkdir(parents=True)
    rows = []
    for i, (name, agents, seed, policy) in enumerate(
        product(plan.scenarios, plan.agents, plan.seeds, plan.policies)
    ):
        config = Scenario.model_validate(load(name).model_dump() | {"agents": agents, "seed": seed})
        result = episode(config, policy)
        result.update(
            experiment_id=output.name,
            timestamp=datetime.now(UTC).isoformat(),
            simulator_version="0.2",
            definitions=DEFINITIONS,
        )
        (output / f"episode-{i}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        series = result["coverage_cells_by_tick"]
        assert isinstance(series, list)
        rows.append(
            (
                name,
                agents,
                seed,
                policy,
                series[-1] / (config.width * config.height),
                result["tasks_issued"],
            )
        )
    with (output / "comparison.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("scenario", "agents", "seed", "policy", "coverage", "tasks_issued"))
        writer.writerows(rows)
    summaries = []
    for name, agents, policy in product(plan.scenarios, plan.agents, plan.policies):
        values = [row[4] for row in rows if (row[0], row[1], row[3]) == (name, agents, policy)]
        summaries.append(
            {
                "scenario": name,
                "agents": agents,
                "policy": policy,
                "samples": len(values),
                "mean_coverage": mean(values),
                "median_coverage": median(values),
                "sample_sd": stdev(values) if len(values) > 1 else None,
            }
        )
    (output / "summary.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("runs/phase5"))
    args = parser.parse_args()
    print(run(Experiment.model_validate_json(args.config.read_bytes()), args.output))
