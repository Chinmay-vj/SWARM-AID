"""Verify frozen native releases and publish a blinded, stratified review batch."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from evaluation.data.model2 import digest, read_rows, validate_release, write_json
from evaluation.data.model2_collect import presentation_pattern
from evaluation.data.model2_records import Features, Input, Target


def agreement(first: dict[UUID, str], second: dict[UUID, str]) -> dict[str, float | int | None]:
    keys = first.keys() & second.keys()
    if not keys:
        return {"paired": 0, "observed": None, "kappa": None}
    a, b = Counter(first[i] for i in keys), Counter(second[i] for i in keys)
    observed = sum(first[i] == second[i] for i in keys) / len(keys)
    expected = sum(n * b[k] for k, n in a.items()) / len(keys) ** 2
    return {
        "paired": len(keys),
        "observed": observed,
        "kappa": (observed - expected) / (1 - expected) if expected < 1 else None,
    }


def run(root: Path, destination: Path) -> None:
    manifest = root / "simulation/field-v1/manifest.json"
    replay = json.loads(manifest.read_bytes())
    verified = 0
    for name, sha in replay["files"].items():
        if digest(manifest.parent / name) != sha:
            raise ValueError("changed replay")
        verified += 1
    pilot = root / "processed/model2/pilot-2"
    pilot_splits = validate_release(pilot)
    prior = read_rows(pilot / "inputs.jsonl", Input)
    pilot_ids = {r.sample_id for r in prior}
    pilot_evidence = set().union(*(r.evidence_ids for r in prior))
    pilot_patterns = {presentation_pattern(r) for r in prior if r.seed not in range(42, 47)}
    overlap: Counter[str] = Counter()
    strata: dict[str, list[tuple[str, Input]]] = defaultdict(list)
    counts: Counter[str] = Counter()
    episodes = set()
    field_ids: set[UUID] = set()
    field_evidence: dict[UUID, str] = {}
    release_hashes = {}
    for family, sha in sorted(replay["release_hashes"].items()):
        version = "field-v1-" + family
        batch = root / "processed/model2" / version
        if digest(batch / "release.json") != sha:
            raise ValueError("changed release")
        release_hashes[version] = sha
        validate_release(batch)
        meta = json.loads((batch / "release.json").read_bytes())
        verified += 1 + len(meta["files"])
        for row, target in zip(
            read_rows(batch / "inputs.jsonl", Input),
            read_rows(batch / "targets.jsonl", Target),
            strict=True,
        ):
            if (
                row.seed in range(42, 47)
                or row.sample_id in field_ids
                or target.status != "pending"
            ):
                raise ValueError("unexpected development candidate")
            field_ids.add(row.sample_id)
            for evidence in row.evidence_ids:
                if field_evidence.setdefault(evidence, row.split) != row.split:
                    raise ValueError("cross-partition evidence identity")
            overlap["pilot_sample_ids"] += row.sample_id in pilot_ids
            overlap["field_rows_sharing_pilot_evidence"] += bool(pilot_evidence & row.evidence_ids)
            overlap["field_rows_sharing_development_pilot_pattern"] += (
                presentation_pattern(row) in pilot_patterns
            )
            episodes.add(row.episode_id)
            counts[row.split] += 1
            flags = {
                "conflicting": target.relationship == "conflicting",
                "duplicate": target.relationship == "duplicate",
                "ambiguous": target.provenance == "unresolved",
                "urgent": target.urgency == "potentially_urgent",
                "incomplete": bool(target.missing_information or row.disabled_modalities),
                "routine": target.assessment == "routine",
            }
            for flag, on in flags.items():
                if on:
                    strata[flag].append((version, row))
            strata["other"].append((version, row))
    selected: set[UUID] = set()
    episode_counts: Counter[UUID] = Counter()
    selected_strata: Counter[str] = Counter()
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destination.parent) as tmp:
        out = Path(tmp) / destination.name
        out.mkdir()
        with (out / "review-queue.jsonl").open("x", encoding="utf8") as queue:
            while len(selected) < min(100, len(field_ids)):
                for flag in (
                    "ambiguous",
                    "conflicting",
                    "duplicate",
                    "urgent",
                    "routine",
                    "incomplete",
                    "other",
                ):
                    available = [v for v in strata[flag] if v[1].sample_id not in selected]
                    if not available:
                        continue
                    version, row = min(
                        available, key=lambda v: (episode_counts[v[1].episode_id], v[1].sample_id)
                    )
                    selected.add(row.sample_id)
                    episode_counts[row.episode_id] += 1
                    selected_strata[flag] += 1
                    print(
                        json.dumps(
                            {
                                "version": version,
                                "features": Features.from_input(row).model_dump(mode="json"),
                                "form": Target(
                                    sample_id=row.sample_id, provenance="unresolved"
                                ).model_dump(mode="json"),
                            }
                        ),
                        file=queue,
                    )
                    if len(selected) == min(100, len(field_ids)):
                        break
        write_json(
            out / "manifest.json",
            {
                "version": destination.name,
                "pilot_splits": pilot_splits,
                "field_splits": dict(counts),
                "pending": len(field_ids),
                "episodes": len(episodes),
                "replay_reports": replay["reports"],
                "checksums_verified": verified,
                "release_hashes": release_hashes,
                "overlap": dict(overlap),
                "queue": len(selected),
                "queued_episodes": len(episode_counts),
                "selection": dict(selected_strata),
                "queue_sha256": digest(out / "review-queue.jsonl"),
                "agreement": agreement({}, {}),
                "code_sha256": digest(Path(__file__)),
            },
        )
        out.rename(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    if args.root.resolve().drive.upper() != "D:":
        parser.error("use D: storage")
    run(args.root, args.root / "annotations/model2/phase10g-field-v1")
