"""Replay integrated command journals and export observed frame availability and evaluation references."""

import argparse
import json
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Any

from agents.command_agent.agent import Entry, Settings
from communication.messages import EnvironmentalObservation, HazardDetection, PossibleHumanDetection
from evaluation.data.field_matrix import Matrix
from evaluation.data.model2 import digest, read_rows, validate_release, write_json
from evaluation.data.model2_collect import LocalReport
from simulation.adapters.model1 import Fleet
from simulation.core.configuration import Scenario
from simulation.core.engine import Engine


def replay(
    batch: Path, episode: dict[str, Any]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    config = Scenario.model_validate(episode["configuration"])
    if config.seed in range(42, 47) or not config.field_profile:
        raise ValueError("requires development field episode")
    engine = Engine(config)
    fleet = Fleet(engine, coordination="shared_information", command=Settings())
    assert fleet.command
    frames: dict[tuple[str, int], tuple[str, ...]] = {}
    reference = {}
    while engine.reason == "running":
        now = engine.t * config.tick_ms
        reference[now] = {p for p, person in engine.people.items() if person.visible}
        for agent in engine.active:
            frame = engine.views[agent].frame
            if frame.samples:
                frames[agent, frame.tick_ms] = tuple(sorted({e.modality for e in frame.samples}))
        fleet.advance(engine)
    journal = [
        j
        for j in fleet.command.journal
        if isinstance(
            j.envelope.payload, (EnvironmentalObservation, HazardDetection, PossibleHumanDetection)
        )
    ]
    if not fleet.command.journal_complete or journal != read_rows(
        batch / episode["journal_file"], Entry
    ):
        raise ValueError("standard fleet journal differs from collector")
    observations: list[dict[str, object]] = []
    references: list[dict[str, object]] = []
    for row in read_rows(batch / episode["model1_file"], LocalReport):
        finding = row.report.finding
        obs = finding.observation
        reading = obs.evidence[0]
        available = frames[reading.origin, reading.captured_ms]
        if not all(
            e.origin == reading.origin
            and e.captured_ms == reading.captured_ms
            and e.modality in available
            for e in obs.evidence
        ):
            raise ValueError("unmatched capture frame")
        observations.append(
            {
                "episode_id": str(row.episode_id),
                "report_id": str(row.report.message_id),
                "observation_id": str(obs.observation_id),
                "agent": reading.origin,
                "captured_ms": reading.captured_ms,
                "available": available,
                "missing": sorted(set(config.modalities) - set(available)),
            }
        )
        if finding.kind == "possible_human" and obs.cell is not None:
            references.append(
                {
                    "episode_id": str(row.episode_id),
                    "report_id": str(row.report.message_id),
                    "source": "simulator_reference_at_observation",
                    "observed_ms": obs.observed_ms,
                    "visible_person_at_reported_cell": (obs.cell.x, obs.cell.y)
                    in reference[obs.observed_ms],
                }
            )
    return observations, references


def run(root: Path, matrix_file: Path) -> dict[str, Any]:
    matrix = Matrix.model_validate_json(matrix_file.read_bytes())
    destination = root / "simulation" / matrix.version
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(destination)
    missing: Counter[str] = Counter()
    reference_counts: Counter[str] = Counter()
    receipts = epochs = 0
    hashes = {}
    with TemporaryDirectory(dir=destination.parent) as tmp:
        out = Path(tmp) / "archive"
        out.mkdir()
        for sub in ("operational", "evaluator"):
            (out / sub).mkdir()
        for name in matrix.plans():
            batch = root / "processed/model2" / (matrix.version + "-" + name)
            validate_release(batch)
            hashes[name] = digest(batch / "release.json")
            metadata = json.loads((batch / "release.json").read_bytes())
            with (
                (out / "operational" / (name + ".jsonl")).open("x", encoding="utf8") as op,
                (out / "evaluator" / (name + ".jsonl")).open("x", encoding="utf8") as ev,
            ):
                for episode in metadata["episodes"]:
                    observed, refs = replay(batch, episode)
                    epochs += 1
                    receipts += len(observed)
                    for row in observed:
                        print(json.dumps(row), file=op)
                        missing["incomplete" if row["missing"] else "complete"] += 1
                    for row in refs:
                        print(json.dumps(row), file=ev)
                        reference_counts[str(row["visible_person_at_reported_cell"])] += 1
        summary = {
            "epochs": epochs,
            "reports": receipts,
            "availability": dict(missing),
            "colocation": dict(reference_counts),
            "release_hashes": hashes,
            "files": {p.relative_to(out).as_posix(): digest(p) for p in out.rglob("*.jsonl")},
        }
        write_json(out / "manifest.json", summary)
        out.rename(destination)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, default=Path("configs/datasets/field_matrix.json"))
    args = parser.parse_args()
    if args.root.resolve().drive.upper() != "D:":
        parser.error("use D: storage")
    start = perf_counter()
    print(json.dumps(run(args.root.resolve(), args.matrix)))
    print("Replay seconds", round(perf_counter() - start, 2))
