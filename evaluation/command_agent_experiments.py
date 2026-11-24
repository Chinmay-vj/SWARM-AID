"""Matched CPU experiments for synthetic command-side review."""

import argparse
import csv
import json
from itertools import product
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import Field, PositiveInt

from agents.command_agent.agent import Mode, Settings
from agents.shared.domain import Record
from communication.messages import CommandAlert, ForwardedReport, HumanApproval, IncidentUpdate
from evaluation.results import metrics
from simulation.adapters.model1 import Fleet
from simulation.core.configuration import Scenario, load
from simulation.core.engine import Engine


class Experiment(Record):
    scenarios: tuple[str, ...] = Field(min_length=1)
    seeds: tuple[int, ...] = Field(min_length=1)
    agents: tuple[PositiveInt, ...] = Field(min_length=1)
    modes: tuple[Mode, ...] = ("direct", "rules", "fusion")
    scripted_review: bool = False


def episode(config: Scenario, mode: Mode, scripted_review: bool = False) -> dict[str, object]:
    engine = Engine(config)
    fleet = Fleet(engine, coordination="shared_information", command=Settings(mode=mode))
    assert fleet.network and fleet.command
    cursor = 0
    decisions = 0
    offered = set()
    truth: dict[int, dict[tuple[int, int], str]] = {}
    human_alerts = unmatched = 0
    associations: dict[UUID, set[str]] = {}
    insight_ids: set[UUID] = set()
    matched: set[str] = set()
    first_alert_ms: int | None = None
    evaluated = set()
    while engine.reason == "running":
        truth[engine.t * config.tick_ms] = {
            cell: person.entity_id for cell, person in engine.people.items() if person.visible
        }
        fleet.advance(engine)
        inbox = fleet.network.history["operator"]
        for msg in inbox[cursor:]:
            p = msg.payload.update if isinstance(msg.payload, CommandAlert) else msg.payload
            evidence_ids: tuple[UUID, ...] = ()
            if isinstance(p, ForwardedReport):
                evidence_ids = (p.report.message_id,)
            elif isinstance(p, IncidentUpdate):
                evidence_ids = p.incident.reports
            if isinstance(p, IncidentUpdate):
                insight_ids.add(p.incident.incident_id)
            for mid in evidence_ids:
                if mid in evaluated:
                    continue
                evaluated.add(mid)
                finding = next(
                    (r.finding for r in fleet.command.findings.values() if r.message_id == mid),
                    None,
                )
                if finding is None or finding.kind != "possible_human":
                    continue
                obs = finding.observation
                person = (
                    truth.get(obs.observed_ms, {}).get((obs.cell.x, obs.cell.y))
                    if obs.cell
                    else None
                )
                human_alerts += 1
                if first_alert_ms is None:
                    first_alert_ms = fleet.network.router.now
                if person is None:
                    unmatched += 1
                else:
                    matched.add(person)
                    if isinstance(p, IncidentUpdate):
                        associations.setdefault(p.incident.incident_id, set()).add(person)
            if not scripted_review or not isinstance(p, IncidentUpdate) or not p.recommendation:
                continue
            rec = p.recommendation
            if rec.incident_id in offered or rec.expires_ms <= fleet.network.router.now:
                continue
            offered.add(rec.incident_id)
            fleet.network.issue(
                "operator",
                HumanApproval(
                    message_type="human_approval",
                    incident_id=rec.incident_id,
                    recommendation_id=rec.recommendation_id,
                    revision=rec.incident_revision,
                    decision="approve_review" if decisions % 2 == 0 else "reject",
                    reason="scripted synthetic review",
                ),
                "command",
                rec.expires_ms,
            )
            decisions += 1
        cursor = len(inbox)
    return {
        "mode": mode,
        "mixed_identity_incidents": sum(len(people) > 1 for people in associations.values()),
        "incidents_delivered": len(insight_ids),
        "repeat_reports_of_people": human_alerts - unmatched - len(matched),
        "first_operator_sighting_ms": first_alert_ms,
        "false_sighting_fraction": unmatched / human_alerts if human_alerts else None,
        "missed_people_fraction": (config.people - len(matched)) / config.people
        if config.people
        else None,
        "delivered_sighting_reports": human_alerts,
        "scenario": config.model_dump(mode="json"),
        "settings": fleet.command.settings.model_dump(mode="json"),
        "scripted_review": scripted_review,
        "counts": dict(fleet.command.counts),
        "incidents": len(fleet.command.incidents),
        "observations": len(fleet.command.findings),
        "decisions_sent": decisions,
        "operator_updates": sum(
            isinstance(m.payload, (CommandAlert, IncidentUpdate, ForwardedReport))
            for m in fleet.network.history["operator"]
        ),
        "simulator": metrics(engine),
        "network": fleet.network.router.metrics(),
    }


def run(plan: Experiment, directory: Path) -> Path:
    folder = directory / uuid4().hex
    folder.mkdir(parents=True)
    rows = []
    for index, (name, size, seed, mode) in enumerate(
        product(plan.scenarios, plan.agents, plan.seeds, plan.modes)
    ):
        config = Scenario.model_validate(load(name).model_dump() | {"agents": size, "seed": seed})
        result = episode(config, mode, plan.scripted_review)
        (folder / f"episode-{index}.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
        rows.append(
            (
                name,
                size,
                seed,
                mode,
                result["observations"],
                result["incidents"],
                result["operator_updates"],
                result["decisions_sent"],
            )
        )
    with (folder / "comparison.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            (
                "scenario",
                "agents",
                "seed",
                "mode",
                "observations",
                "incidents",
                "operator_updates",
                "decisions_sent",
            )
        )
        writer.writerows(rows)
    return folder


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("runs/phase6-experiments"))
    args = parser.parse_args()
    print(run(Experiment.model_validate_json(args.config.read_bytes()), args.output))
