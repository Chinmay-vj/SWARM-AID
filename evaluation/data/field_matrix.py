"""Bounded field-scenario generation using validated Phase 10E family batches."""

import argparse
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from time import perf_counter
from typing import Literal
from uuid import UUID

from pydantic import Field

from agents.shared.domain import Record
from evaluation.data.model2 import Plan, digest, generate, read_rows, validate_release, write_json
from evaluation.data.model2_collect import Episode, presentation_pattern
from evaluation.data.model2_records import Input
from simulation.core.configuration import Difficulty, load


class Matrix(Record):
    version: str = Field(pattern=r"^field-[a-z0-9-]+$")
    families: dict[str, Literal["train", "validation"]] = Field(min_length=1, max_length=6)
    episodes_per_family: int = Field(ge=1, le=16)
    per_episode: int = Field(ge=1, le=100)
    first_seed: int = Field(ge=0)
    fleets: tuple[int, ...] = Field(min_length=1)
    levels: tuple[Difficulty, ...] = Field(min_length=1)
    budget_bytes: int = Field(gt=0)
    free_reserve_bytes: int = Field(gt=0)

    def plans(self) -> dict[str, Plan]:
        if not set(self.fleets) <= {1, 2, 3, 5, 8}:
            raise ValueError("unsupported fleet")
        plans = {}
        for family, (name, split) in enumerate(self.families.items()):
            if not name.isidentifier() or load(name).version != "2":
                raise ValueError("expected registered field scenario")
            episodes = tuple(
                Episode(
                    scenario=name,
                    split=split,
                    seed=self.first_seed + family * self.episodes_per_family + i,
                    agents=self.fleets[(i + family) % len(self.fleets)],
                    difficulty=self.levels[(i + family) % len(self.levels)],
                )
                for i in range(self.episodes_per_family)
            )
            if any(e.seed in range(42, 47) for e in episodes):
                raise ValueError("reserved seed in matrix")
            plans[name] = Plan(per_episode=self.per_episode, episodes=episodes)
        return plans


def guard(root: Path, matrix: Matrix, occupied: int, estimate: int) -> None:
    if (
        occupied + estimate > matrix.budget_bytes
        or shutil.disk_usage(root).free < matrix.free_reserve_bytes + estimate
    ):
        raise ValueError("field generation storage budget exceeded")


def run(matrix_file: Path, root: Path) -> dict[str, object]:
    matrix = Matrix.model_validate_json(matrix_file.read_bytes())
    plans = matrix.plans()
    folder = root / "manifests" / "model2" / matrix.version
    folder.mkdir(parents=True, exist_ok=True)
    counters: dict[str, Counter[str]] = defaultdict(Counter)
    totals: Counter[str] = Counter()
    evidence_splits: dict[UUID, str] = {}
    patterns: dict[tuple[object, ...], set[str]] = defaultdict(set)
    samples: set[UUID] = set()
    sizes = {}
    for name, plan in plans.items():
        plan_path = folder / (name + ".json")
        expected = plan.model_dump(exclude_none=True)
        if plan_path.exists():
            if json.loads(plan_path.read_bytes()) != json.loads(
                plan.model_dump_json(exclude_none=True)
            ):
                raise ValueError("existing batch plan differs")
        else:
            with plan_path.open("x", encoding="utf-8") as stream:
                json.dump(expected, stream, indent=2)
        version = matrix.version + "-" + name
        batch = root / "processed/model2" / version
        if not batch.exists():
            # Conservative per-agent episode allocation, based on the measured preflight.
            guard(root, matrix, totals["bytes"], sum(ep.agents for ep in plan.episodes) * 700_000)
            generate(plan_path, root, version)
        validate_release(batch)
        meta = json.loads((batch / "release.json").read_bytes())
        if json.loads((batch / "plan.json").read_bytes()) != json.loads(plan_path.read_bytes()):
            raise ValueError("wrong batch plan")
        if any(digest(Path(p)) != sha for p, sha in meta["source_digests"].items()):
            raise ValueError("batch source changed; select a new matrix version")
        size = sum(p.stat().st_size for p in batch.iterdir())
        guard(root, matrix, totals["bytes"], size)
        sizes[name] = size
        totals["bytes"] += size
        for ep in meta["episodes"]:
            totals["episodes"] += 1
            with (batch / ep["model1_file"]).open("rb") as stream:
                totals["model1_reports"] += sum(1 for _ in stream)
        for row in read_rows(batch / "inputs.jsonl", Input):
            if row.sample_id in samples or row.seed in range(42, 47):
                raise ValueError("duplicate sample or protected seed")
            samples.add(row.sample_id)
            patterns[presentation_pattern(row)].add(row.split)
            for evidence in row.evidence_ids:
                if evidence_splits.setdefault(evidence, row.split) != row.split:
                    raise ValueError("cross-partition evidence")
        stats = json.loads((batch / "statistics.json").read_bytes())
        for key in (
            "assessment",
            "relationships",
            "status",
            "provenance",
            "split",
            "agent_count",
            "focal_modality",
            "variants",
            "scenario",
        ):
            counters[key].update(stats[key])
        totals["model2"] += stats["records"]
        totals["groups"] += stats["groups_unique_report_sets"]
        totals["incidents"] += stats["unique_baseline_incidents"]
        totals["pending_forms"] += len((batch / "review-queue.jsonl").read_bytes().splitlines())
    result = {
        "matrix_sha256": digest(matrix_file),
        "totals": dict(totals),
        "batch_bytes": sizes,
        "counts": {k: dict(v) for k, v in counters.items()},
        "distinct_patterns": len(patterns),
        "cross_split_patterns": sum(len(v) > 1 for v in patterns.values()),
        "unique_evidence": len(evidence_splits),
    }
    path = folder / "summary.json"
    if path.exists() and json.loads(path.read_bytes()) != result:
        raise ValueError("published summary differs")
    if not path.exists():
        write_json(path, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=Path("configs/datasets/field_matrix.json"))
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    if args.root.resolve().drive.upper() != "D:":
        parser.error("use D: storage")
    start = perf_counter()
    print(json.dumps(run(args.matrix, args.root.resolve()), indent=2))
    print("Elapsed seconds", round(perf_counter() - start, 2))
