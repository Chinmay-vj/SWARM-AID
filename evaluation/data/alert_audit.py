"""Matched development replay. Per-report citations and evaluator references stay offline."""

import argparse
import json
from collections import Counter
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from agents.command_agent.agent import Mode, Settings
from communication.messages import CommandAlert, IncidentUpdate
from evaluation.command_agent_experiments import Experiment
from evaluation.data.model2 import digest, write_json
from simulation.adapters.model1 import Fleet
from simulation.core.configuration import Scenario, load
from simulation.core.engine import Engine


def trace(config: Scenario, mode: Mode) -> tuple[dict[str, dict[str, Any]], int]:
    if config.seed in range(42, 47):
        raise ValueError("protected evaluation seed")
    engine = Engine(config)
    fleet = Fleet(engine, coordination="shared_information", command=Settings(mode=mode))
    assert fleet.command and fleet.network
    truth = {}
    cited: dict[str, list[int]] = {}
    urgent: set[str] = set()
    explicit: dict[str, int] = {}
    events: dict[str, set[str]] = {}
    cursor = updates = 0
    while engine.reason == "running":
        truth[engine.t * config.tick_ms] = {p for p, v in engine.people.items() if v.visible}
        fleet.advance(engine)
        for _, kind, ref in fleet.command.events:
            if ref:
                events.setdefault(ref, set()).add(kind)
        inbox = fleet.network.history["operator"]
        for message in inbox[cursor:]:
            p = message.payload
            update = p.update if isinstance(p, CommandAlert) else p
            if isinstance(update, IncidentUpdate):
                updates += 1
                for cited_id in update.incident.reports:
                    cited.setdefault(str(cited_id), []).append(fleet.network.router.now)
                direct = set(p.supporting_evidence) if isinstance(p, CommandAlert) else set()
                if update.recommendation:
                    direct.update(update.recommendation.evidence_ids)
                for eid in direct:
                    explicit.setdefault(str(eid), fleet.network.router.now)
                if isinstance(p, CommandAlert) and p.priority == "potentially_urgent":
                    urgent.update(str(e) for e in p.supporting_evidence)
        cursor = len(inbox)
    result = {}
    for report in fleet.command.findings.values():
        obs = report.finding.observation
        mid = str(report.message_id)
        evidence = sorted(str(e.evidence_id) for e in obs.evidence)
        times = cited.get(mid, [])
        result[mid] = {
            "observation": str(obs.observation_id),
            "evidence": evidence,
            "captured_ms": obs.observed_ms,
            "kind": report.finding.kind,
            "colocated": bool(
                obs.cell and (obs.cell.x, obs.cell.y) in truth.get(obs.observed_ms, set())
            )
            if report.finding.kind == "possible_human"
            else None,
            "first_ms": min(times) if times else None,
            "citations": len(times),
            "explicit_evidence_ms": {e: explicit[e] for e in evidence if e in explicit},
            "source_events": sorted(events.get(mid, set())),
            "urgent_evidence": sorted(set(evidence) & urgent),
        }
    if set(cited) - result.keys():
        raise ValueError("operator cited unknown source")
    return result, updates


def run(plan_file: Path, dest: Path) -> None:
    plan = Experiment.model_validate_json(plan_file.read_bytes())
    if dest.exists():
        raise FileExistsError(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=dest.parent) as tmp:
        out = Path(tmp) / dest.name
        out.mkdir()
        totals: Counter[str] = Counter()
        all_evidence: dict[str, set[str]] = {}
        with (out / "matched.jsonl").open("x", encoding="utf8") as rows:
            for name, n, seed in product(plan.scenarios, plan.agents, plan.seeds):
                cfg = load(name).model_copy(update={"agents": n, "seed": seed})
                rules, individual_updates = trace(cfg, "rules")
                fusion, fused_updates = trace(cfg, "fusion")
                totals.update(rules_updates=individual_updates, fusion_updates=fused_updates)
                if rules.keys() != fusion.keys():
                    raise ValueError("unmatched command observations")
                for mid, r in rules.items():
                    f = fusion[mid]
                    if any(
                        r[k] != f[k]
                        for k in ("observation", "evidence", "captured_ms", "kind", "colocated")
                    ):
                        raise ValueError("mismatched observation lineage")
                    left, right = r["first_ms"], f["first_ms"]
                    status = (
                        ("both" if right is not None else "rules_only")
                        if left is not None
                        else ("fusion_only" if right is not None else "neither")
                    )
                    totals[status] += 1
                    if status == "rules_only":
                        totals["rules_only_held_as_corroboration"] += (
                            "corroborated" in f["source_events"]
                        )
                    if r["colocated"]:
                        totals["colocated_" + status] += 1
                    for mode, record in (("rules", r), ("fusion", f)):
                        if record["first_ms"] is not None:
                            all_evidence.setdefault(mode, set()).update(record["evidence"])
                        represented = all_evidence.setdefault(mode + "_any_attribution", set())
                        represented.update(record["explicit_evidence_ms"])
                        if record["citations"]:
                            represented.update(record["evidence"])
                        all_evidence.setdefault(mode + "_urgent", set()).update(
                            record["urgent_evidence"]
                        )
                    if left is not None and right is not None:
                        totals["later_in_fusion"] += right > left
                    print(
                        json.dumps(
                            {
                                "scenario": name,
                                "agents": n,
                                "seed": seed,
                                "report": mid,
                                "status": status,
                                "rules": r,
                                "fusion": f,
                                "review": status != "both" or right != left,
                            }
                        ),
                        file=rows,
                    )
        write_json(
            out / "summary.json",
            {
                "counts": dict(totals),
                "unique_evidence": {k: len(v) for k, v in all_evidence.items()},
                "rules_only_evidence": len(all_evidence["rules"] - all_evidence["fusion"]),
                "rules_urgent_absent_from_fusion_citations": len(
                    all_evidence["rules_urgent"] - all_evidence["fusion"]
                ),
                "rules_urgent_absent_from_any_fusion_attribution": len(
                    all_evidence["rules_urgent"] - all_evidence["fusion_any_attribution"]
                ),
                "rules_only_any_attribution": len(
                    all_evidence["rules_any_attribution"] - all_evidence["fusion_any_attribution"]
                ),
                "matched_sha256": digest(out / "matched.jsonl"),
                "plan_sha256": digest(plan_file),
            },
        )
        out.rename(dest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve().drive.upper() != "D:":
        parser.error("use D: storage")
    run(Path("configs/experiments/phase6_field_command.json"), args.output)
