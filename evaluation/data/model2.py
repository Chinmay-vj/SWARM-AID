"""Offline pilot generation, validation, and independent reviewer export."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, TypeVar
from uuid import UUID, uuid4

from pydantic import Field

from agents.command_agent.agent import Entry
from agents.shared.domain import Record
from communication.messages import EnvironmentalObservation, HazardDetection, PossibleHumanDetection
from evaluation.data.contracts import Dataset, Manifest, Registry, Sample, Storage
from evaluation.data.model2_collect import Episode, LocalReport, challenge, collect
from evaluation.data.model2_records import Features, Input, Receipt, Target, Variant
from evaluation.data.validation import validate

T = TypeVar("T", bound=Record)
DATASET = "swarm-model2-symbolic"


class Plan(Record):
    per_episode: int = Field(gt=0, le=500)
    episodes: tuple[Episode, ...] = Field(min_length=1)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_rows(path: Path, rows: Iterable[Record]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(row.model_dump_json() + "\n")


def read_rows(path: Path, model: type[T]) -> list[T]:
    return [model.model_validate_json(line) for line in path.read_bytes().splitlines()]


def manifest(rows: list[Input], version: str) -> Manifest:
    samples = []
    for row in rows:
        r = row.receipt
        o = r.report.finding.observation
        samples.append(
            Sample(
                sample_id=str(row.sample_id),
                source_ref=str(row.parent_id or row.sample_id),
                source_id=r.sender,
                licence_ref="internal-synthetic-pending",
                modality=o.evidence[0].modality,
                representation="symbolic",
                split=row.split,
                evidence=o.evidence,
                observation_id=o.observation_id,
                mission_id=row.mission_id,
                tick_ms=r.received_ms,
                scenario_id=row.scenario_id,
                seed=row.seed,
                sequence_id=str(row.episode_id),
            )
        )
    return Manifest(
        schema_version="1.0",
        manifest_version="1",
        dataset_id=DATASET,
        dataset_version=version,
        origin="synthetic",
        role="operational",
        samples=tuple(samples),
    )


def validate_release(path: Path) -> dict[str, int]:
    meta = json.loads((path / "release.json").read_bytes())
    for name, sha in meta["files"].items():
        file = (path / name).resolve()
        if not file.is_relative_to(path.resolve()) or digest(file) != sha:
            raise ValueError("source or export checksum mismatch")
    rows = read_rows(path / "inputs.jsonl", Input)
    targets = read_rows(path / "targets.jsonl", Target)
    if [Features.from_input(s) for s in rows] != read_rows(path / "features.jsonl", Features):
        raise ValueError("feature export differs from as-of input projection")
    sources: dict[str, dict[UUID, Receipt]] = {}
    episode_plans = {}
    for ep in meta["episodes"]:
        episode_plans[ep["episode_id"]] = Episode.model_validate(ep["plan"])
        if any(ep[key] not in meta["files"] for key in ("source_file", "journal_file")):
            raise ValueError("unindexed source ledger")
        receipts = read_rows(path / ep["source_file"], Receipt)
        entries = read_rows(path / ep["journal_file"], Entry)
        if ep["configuration"].get("version") == "2":
            if ep["plan"]["seed"] in range(42, 47) or ep["model1_file"] not in meta["files"]:
                raise ValueError("invalid expansion provenance")
            for sample, receipt in zip(
                read_rows(path / ep["model1_file"], LocalReport), receipts, strict=True
            ):
                if (
                    str(sample.episode_id) != ep["episode_id"]
                    or sample.report != receipt.report
                    or sample.sender != receipt.sender
                    or sample.seed != ep["plan"]["seed"]
                    or sample.scenario_id != ep["plan"]["scenario"]
                    or tuple(r.evidence for r in sample.readings)
                    != receipt.report.finding.observation.evidence
                ):
                    raise ValueError("Model 1 inputs and report evidence disagree")
        if len(entries) != len(receipts):
            raise ValueError("source journal length mismatch")
        for r, j in zip(receipts, entries, strict=True):
            p = j.envelope.payload
            f = r.report.finding
            expected: tuple[str, str | None]
            if isinstance(p, EnvironmentalObservation):
                expected = ("environment", p.feature)
            elif isinstance(p, HazardDetection):
                expected = ("hazard", p.hazard)
            elif isinstance(p, PossibleHumanDetection):
                expected = ("possible_human", None)
            else:
                raise TypeError("non-observation in source ledger")
            if (
                (f.kind, f.label) != expected
                or p.observation != f.observation
                or r.report.message_id != j.envelope.message_id
                or r.sender != j.principal
                or r.sent_ms != j.envelope.sent_ms
                or r.received_ms != j.received_ms
                or r.session_id != j.envelope.session_id
                or j.envelope.source != j.principal
            ):
                raise ValueError("journal provenance mismatch")
        sources[ep["episode_id"]] = {r.report.message_id: r for r in receipts}
    indexed = {s.sample_id: s for s in rows}
    if len(indexed) != len(rows) or len({t.sample_id for t in targets}) != len(rows):
        raise ValueError("duplicate identifiers or unpaired targets")
    for s, t in zip(rows, targets, strict=True):
        t.check(s)
        if t.provenance == "human_reviewed":
            raise ValueError("independent review belongs outside frozen weak targets")
        plan = episode_plans[str(s.episode_id)]
        if (plan.scenario, plan.seed, plan.agents, plan.split) != (
            s.scenario_id,
            s.seed,
            s.agents,
            s.split,
        ):
            raise ValueError("episode provenance mismatch")
        if s.parent_id:
            p0 = indexed[s.parent_id]
            if challenge(p0, s.variant)[0] != s or s.split != p0.split:
                raise ValueError("invalid transformation lineage")
        else:
            source = sources[str(s.episode_id)]
            for r in (s.receipt, *s.context):
                if source.get(r.report.message_id) != r:
                    raise ValueError("missing original report")
    m = manifest(rows, meta["version"])
    if Manifest.model_validate_json((path / "manifest.json").read_bytes()) != m:
        raise ValueError("index mismatch")
    registry = Registry.model_validate_json((path / "registry.json").read_bytes())
    return validate(registry, [m], path)


def generate(config: Path, root: Path, version: str) -> Path:
    if (
        not version
        or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789.-_" for c in version)
        or version in {".", ".."}
        or version.endswith(".")
    ):
        raise ValueError("invalid release name")
    dest = root / "processed" / "model2" / version
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise FileExistsError(dest)
    plan = Plan.model_validate_json(config.read_bytes())
    with TemporaryDirectory(dir=dest.parent) as tmp:
        path = Path(tmp) / "release"
        path.mkdir()
        rows: list[Input] = []
        targets: list[Target] = []
        episodes = []
        for ep in plan.episodes:
            batch, info = collect(ep, plan.per_episode)
            if "model1" in info:
                name = f"{info['episode_id']}-model1.jsonl"
                write_rows(path / name, (LocalReport.model_validate(v) for v in info.pop("model1")))
                info["model1_file"] = name
            for field, cls in (("source", Receipt), ("journal", Entry)):
                name = f"{info['episode_id']}-{field}.jsonl"
                write_rows(path / name, (cls.model_validate(v) for v in info.pop(field)))
                info[field + "_file"] = name
            episodes.append(info)
            for s, t in batch:
                rows.append(s)
                targets.append(t)
        variants: tuple[Variant, ...] = ("repeat", "relay", "conflict", "stale", "spurious")
        references = []
        for variant in variants:
            parent = next(
                (
                    s
                    for s in rows
                    if s.variant == "native"
                    and s.receipt.report.finding.kind == "environment"
                    and (variant != "spurious" or s.scenario_id == "command_routine")
                ),
                None,
            )
            if parent is None:
                continue
            s, t = challenge(parent, variant)
            rows.append(s)
            targets.append(t)
            if variant == "spurious":
                references.append(
                    {
                        "sample_id": str(s.sample_id),
                        "source": "deterministic_scenario",
                        "reference": "zero people in command_routine configuration",
                        "controlled_false_sighting": True,
                    }
                )
        if not rows:
            raise ValueError("no eligible report inputs")
        write_rows(path / "inputs.jsonl", rows)
        write_rows(path / "features.jsonl", (Features.from_input(s) for s in rows))
        write_rows(path / "targets.jsonl", targets)
        write_json(path / "evaluator.json", references)
        write_json(path / "plan.json", plan.model_dump(exclude_none=True))
        m = manifest(rows, version)
        write_json(path / "manifest.json", m.model_dump(mode="json"))
        registry = Registry(
            schema_version="1.0",
            datasets=(
                Dataset(
                    dataset_id=DATASET,
                    name="Model 2 symbolic command pilot",
                    origin="synthetic",
                    version=version,
                    modalities=("environment", "image", "gps", "imu", "thermal", "text", "peer"),
                    annotation_types=("weak command assessment",),
                    tasks=("command decision support",),
                    privacy_considerations="Symbolic references only",
                    limitations="Expert review pending",
                    sample_count=len(rows),
                    download_status="available",
                ),
            ),
        )
        write_json(path / "registry.json", registry.model_dump(mode="json"))
        review_ids = {
            next(s.sample_id for s in rows if str(s.episode_id) == ep["episode_id"])
            for ep in episodes
            if any(str(s.episode_id) == ep["episode_id"] for s in rows)
        }
        review_ids.update(s.sample_id for s in rows if s.parent_id)
        if any("model1_file" in ep for ep in episodes):
            for metadata in episodes:
                for relationship in ("conflicting", "duplicate", "corroborating", "single"):
                    candidate = next(
                        (
                            s
                            for s, t in zip(rows, targets, strict=True)
                            if str(s.episode_id) == metadata["episode_id"]
                            and t.relationship == relationship
                        ),
                        None,
                    )
                    if candidate:
                        review_ids.add(candidate.sample_id)
        write_rows(
            path / "review-queue.jsonl",
            (
                Target(sample_id=s.sample_id, provenance="unresolved")
                for s in rows
                if s.sample_id in review_ids
            ),
        )
        stats = statistics(rows, targets)
        write_json(path / "statistics.json", stats)
        files = {p.name: digest(p) for p in path.iterdir()}
        source_paths = [
            Path("configs/model1.json"),
            config,
            Path(__file__),
            *Path("evaluation/data").glob("model2_*.py"),
            *[Path("configs/scenarios") / (ep.scenario + ".json") for ep in plan.episodes],
            Path("agents/command_agent/agent.py"),
            Path("simulation/sensors/mock.py"),
            Path("agents/drone_agent/components.py"),
            Path("simulation/adapters/model1.py"),
            Path("simulation/core/configuration.py"),
            Path("simulation/environments/base.py"),
            Path("simulation/core/engine.py"),
            Path("communication/network.py"),
            Path("agents/drone_agent/baselines.py"),
        ]
        write_json(
            path / "release.json",
            {
                "version": version,
                "schema_version": "1.0",
                "taxonomy_version": "1.0",
                "created_at": datetime.now(UTC).isoformat(),
                "git_commit": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], text=True
                ).strip(),
                "working_tree_dirty": bool(
                    subprocess.check_output(["git", "status", "--porcelain"])
                ),
                "source_digests": {p.as_posix(): digest(p) for p in source_paths},
                "episodes": episodes,
                "files": files,
            },
        )
        try:
            validate_release(path)
        except (ValueError, TypeError, KeyError, OSError) as exc:
            quarantine = root / "interim" / "model2" / "quarantine" / str(uuid4())
            quarantine.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), quarantine)
            write_json(quarantine / "validation-error.json", {"error": str(exc)})
            raise
        path.rename(dest)
    return dest


def statistics(rows: list[Input], targets: list[Target]) -> dict[str, Any]:
    def counts(values: Iterable[object]) -> dict[str, int]:
        return dict(sorted(Counter(str(v) for v in values).items()))

    return {
        "records": len(rows),
        "episodes": len({s.episode_id for s in rows}),
        "native": sum(s.variant == "native" for s in rows),
        "age_at_least_1500_ms": sum(s.age_ms >= 1500 for s in rows),
        "delivered_after_send": sum(s.receipt.received_ms > s.receipt.sent_ms for s in rows),
        "unique_baseline_incidents": len(
            {
                (s.episode_id, t.baseline_incident.incident_id)
                for s, t in zip(rows, targets, strict=True)
                if t.baseline_incident
            }
        ),
        "groups_unique_report_sets": len(
            {
                (
                    s.episode_id,
                    tuple(sorted({r.report.message_id for r in (*s.context, s.receipt)})),
                )
                for s in rows
            }
        ),
        "public_records": 0,
        "human_reviewed": 0,
        "variants": counts(s.variant for s in rows),
        "scenario": counts(s.scenario_id for s in rows),
        "agent_count": counts(s.agents for s in rows),
        "split": counts(s.split for s in rows),
        "assessment": counts(t.assessment for t in targets),
        "urgency": counts(t.urgency for t in targets),
        "relationships": counts(t.relationship for t in targets),
        "provenance": counts(t.provenance for t in targets),
        "status": counts(t.status for t in targets),
        "evidence_count": counts(len(s.evidence_ids) for s in rows),
        "disabled_modalities": counts(",".join(s.disabled_modalities) or "none" for s in rows),
        "focal_modality": counts(
            e.modality for s in rows for e in s.receipt.report.finding.observation.evidence
        ),
        "recommendations": counts(t.recommendation.request for t in targets if t.recommendation),
    }


def save_review(release: Path, file: Path) -> Path:
    validate_release(release)
    rows = {s.sample_id: s for s in read_rows(release / "inputs.jsonl", Input)}
    proposal = Target.model_validate_json(file.read_bytes())
    if proposal.provenance != "human_reviewed":
        raise ValueError("reviewer and human provenance required")
    proposal.check(rows[proposal.sample_id])
    if proposal.recommendation:
        source = next(
            t
            for t in read_rows(release / "targets.jsonl", Target)
            if t.sample_id == proposal.sample_id
        )
        rec = proposal.recommendation
        inc = source.baseline_incident
        if not inc or (inc.incident_id, inc.revision) != (rec.incident_id, rec.incident_revision):
            raise ValueError("review proposal must reference the recorded incident revision")
    directory = release.parent.parent.parent / "annotations" / "model2" / release.name
    directory.mkdir(parents=True, exist_ok=True)
    revision = proposal.revision
    if revision > 1 and not (directory / f"{proposal.sample_id}-{revision - 1}.json").exists():
        raise ValueError("previous revision missing")
    dest = directory / f"{proposal.sample_id}-{revision}.json"
    temp = directory / f".{uuid4()}.tmp"
    try:
        write_json(temp, proposal.model_dump(mode="json"))
        os.link(temp, dest)
    finally:
        temp.unlink(missing_ok=True)
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("generate", "validate", "show", "review", "export-reviews")
    )
    parser.add_argument("--version", default="pilot-2")
    parser.add_argument("--plan", type=Path, default=Path("configs/datasets/model2_pilot.json"))
    parser.add_argument("--review-file", type=Path)
    parser.add_argument("--sample-id", type=UUID)
    args = parser.parse_args()
    root = Path(
        os.environ.get(
            "SWARM_DATASET_ROOT",
            Storage.model_validate_json(Path("configs/datasets/storage.json").read_bytes()).root,
        )
    ).resolve()
    if (
        root.drive.upper() != "D:"
        or Path(args.version).name != args.version
        or args.version in (".", "..")
    ):
        parser.error("use D: storage and a plain release name")
    path = root / "processed" / "model2" / args.version
    if args.action == "generate":
        print(generate(args.plan, root, args.version))
    elif args.action == "validate":
        print(validate_release(path))
    elif args.action == "show":
        validate_release(path)
        queue = read_rows(path / "review-queue.jsonl", Target)
        selected = args.sample_id or queue[0].sample_id
        rows = read_rows(path / "inputs.jsonl", Input)
        row = next((s for s in rows if s.sample_id == selected), None)
        if row is None:
            parser.error("unknown sample identifier")
        print(Features.from_input(row).model_dump_json(indent=2))
    elif args.action == "review" and args.review_file:
        print(save_review(path, args.review_file))
    elif args.action == "export-reviews":
        validate_release(path)
        samples = {s.sample_id: s for s in read_rows(path / "inputs.jsonl", Input)}
        latest: dict[UUID, Target] = {}
        for file in (root / "annotations" / "model2" / args.version).glob("*.json"):
            target = Target.model_validate_json(file.read_bytes())
            target.check(samples[target.sample_id])
            if target.provenance != "human_reviewed":
                raise ValueError("unexpected review source")
            if (
                target.sample_id not in latest
                or latest[target.sample_id].revision < target.revision
            ):
                latest[target.sample_id] = target
        for key in sorted(latest):
            print(latest[key].model_dump_json())
    else:
        parser.error("review requires --review-file")


if __name__ == "__main__":
    main()
