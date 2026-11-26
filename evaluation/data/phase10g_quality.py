"""Cross-source integrity, split and loader checks over completed private review indexes."""

import argparse
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from evaluation.data.model2 import digest, write_json
from evaluation.data.phase10g import SOURCES
from evaluation.data.preprocessing import normalized_text
from evaluation.data.public_preprocessing import text_digest
from evaluation.data.review_loaders import asset, native_batches, public_batches
from evaluation.data.temporal_partitions import chronological


def rows(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf8") as stream:
        for line in stream:
            yield json.loads(line)


def near_pairs(keys: list[int], distance: int = 3) -> Iterator[tuple[int, int]]:
    """Four disjoint bands guarantee a shared band for distance at most three."""
    if not 0 <= distance <= 3:
        raise ValueError("requires a distance from zero to three")
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, k in enumerate(keys):
        bands = [(b, (k >> (b * 16)) & 65535) for b in range(4)]
        candidates = {j for band in bands for j in buckets[band]}
        for j in sorted(candidates):
            if (k ^ keys[j]).bit_count() <= distance:
                yield j, i
        for band in bands:
            buckets[band].append(i)


def benchmark(root: Path, out: Path) -> dict[str, Any]:
    """Each task and publisher split stays a distinct view of its original record."""
    from evaluation.data.crisismmd import map_observed

    counts: Counter[str] = Counter()
    labels: dict[str, Counter[str]] = defaultdict(Counter)
    media: dict[str, set[str]] = defaultdict(set)
    hashes = {}
    with (out / "crisis-task-views.jsonl").open("x", encoding="utf8") as index:
        for task in ("damage", "humanitarian", "informative"):
            for split in ("train", "dev", "test"):
                path = root / task / (split + ".json")
                for line, row in enumerate(json.loads(path.read_bytes()), 1):
                    ref = row["image_path"]
                    if ref not in hashes:
                        hashes[ref] = digest(asset(root, ref))
                    key = hashes[ref]
                    media[key].add(split)
                    label = row["label"]
                    labels[task][label] += 1
                    counts[task + "/" + split] += 1
                    print(
                        json.dumps(
                            {
                                "task": task,
                                "source": path.relative_to(root).as_posix(),
                                "record": line,
                                "split": split,
                                "event": row["event_name"],
                                "media": ref,
                                "sha256": key,
                                "text_key": text_digest(normalized_text(row["tweet_text"])),
                                "label": label,
                                "context_label": map_observed(label, {label}),
                            }
                        ),
                        file=index,
                    )
    return {
        "counts": dict(counts),
        "labels": dict(labels),
        "media_keys_in_multiple_splits": sum(len(v) > 1 for v in media.values()),
    }


def run(root: Path, version: str = "phase10g-v1") -> None:
    from evaluation.data.contracts import relative_path

    if "/" in relative_path(version):
        raise ValueError("invalid version")
    base = root / "processed" / version
    destination = root / "manifests" / version
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destination.parent) as tmp:
        out = Path(tmp) / version
        out.mkdir()
        known: dict[str, set[str]] = defaultdict(set)
        summaries = {}
        texts: dict[str, set[str]] = defaultdict(set)
        governance = json.loads(Path("configs/datasets/registry.json").read_bytes())
        for name in SOURCES:
            folder = base / name
            meta = json.loads((folder / "summary.json").read_bytes())
            if digest(folder / "index.jsonl") != meta["outputs"]["index.jsonl"]:
                raise ValueError("stale index")
            unusual: Counter[str] = Counter()
            pixels: Counter[str] = Counter()
            classes: Counter[str] = Counter()
            masks: Counter[str] = Counter()
            depths: Counter[str] = Counter()
            shapes: Counter[str] = Counter()
            near = []
            sensor_keys = set()
            sequences: dict[str, Any] = {}
            sensor_rows: list[tuple[str, str, str]] = []
            mask_paths: set[str] = set()
            source = Path(meta["configuration"]["source"])
            source_directory = source.parent if source.is_file() else source
            for reference, expected in meta["source_digests"].items():
                if digest(asset(source_directory, Path(reference).as_posix())) != expected:
                    raise ValueError("source metadata digest changed")
            registry_ids = {
                "ESC-50": "esc50",
                "Smoke": "smoke-detection-iot",
                "UCI": "uci-air-quality",
                "USGS": "usgs-water-data",
            }
            registry_id = registry_ids.get(name, name.lower())
            registry_row: dict[str, Any] = next(
                (r for r in governance["datasets"] if r["dataset_id"] == registry_id), {}
            )
            units: dict[str, set[str]] = defaultdict(set)
            for row in rows(folder / "index.jsonl"):
                if row.get("sha256"):
                    known[row["sha256"]].add(name)
                if row.get("text_key"):
                    texts[name].add(row["text_key"])
                if row.get("size"):
                    shapes["x".join(map(str, row["size"]))] += 1
                    depths[str(row.get("bit_depth"))] += 1
                if row.get("mask"):
                    mask_paths.add(row["mask"])
                if row.get("mask_histogram"):
                    pixels.update(row["mask_histogram"])
                if row.get("annotations"):
                    classes.update(
                        row["categories"][str(a["category_id"])] for a in row["annotations"]
                    )
                if row.get("dhash"):
                    near.append(int(row["dhash"], 16))
                if "annotation" in row:
                    unusual["missing_annotation_sidecars"] += not row["annotation"]
                if "measurements" in row:
                    key = (row["group"], row["timestamp"], row["parameter"], row["period_end"])
                    # Series and parent statistics can legitimately share a station/period.
                    unusual["repeated_group_time_parameter_keys"] += key in sensor_keys
                    sensor_keys.add(key)
                    group_key = row["timestamp"][:10] if name == "UCI" else str(row["group"])
                    if name == "Smoke":
                        signature = sequences.setdefault(group_key, hashlib.sha256())
                        signature.update(
                            json.dumps(
                                {
                                    k: v[0]
                                    for k, v in row["measurements"].items()
                                    if k != "Temperature[C]"
                                },
                                sort_keys=True,
                            ).encode()
                            + b"\n"
                        )
                    sensor_rows.append(
                        (group_key, row["timestamp"], row["period_end"] or row["timestamp"])
                    )
                    for measurement, values in row["measurements"].items():
                        units[measurement].add(str(values[3]))
                for field in ("missing", "paired"):
                    if field in row:
                        masks[field + "/" + str(row[field])] += 1
            if name in {"FloodNet", "RescueNet"}:
                all_masks = {
                    p.relative_to(source).as_posix()
                    for p in source.rglob("*_lab.png")
                    if p.parent.name.endswith("-label-img")
                }
                unusual["unmatched_class_index_masks"] = len(all_masks - mask_paths)
            if sequences:
                sensor_rows = [
                    (sequences[g].hexdigest(), start, end) for g, start, end in sensor_rows
                ]
            assignment = chronological(sensor_rows)
            smoke = next(public_batches(folder, 1))
            summaries[name] = {
                "source_sequence_groups": {k: v.hexdigest() for k, v in sequences.items()},
                "draft_group_assignments": assignment,
                "draft_row_counts": dict(
                    Counter(assignment[group_key] for group_key, _, _ in sensor_rows)
                ),
                "standardized_units": {k: sorted(v) for k, v in units.items()},
                "source_governance": {
                    k: registry_row.get(k)
                    for k in (
                        "version",
                        "licence",
                        "licence_status",
                        "privacy_status",
                        "verification",
                        "limitations",
                    )
                },
                "approved_training_records": 0,
                "metadata_sha256": digest(folder / "summary.json"),
                "loader_batch_size": len(smoke),
                "loader_fields": sorted(smoke[0]),
                "counts": meta["counts"],
                "distributions": meta["distributions"],
                "extra_checks": dict(unusual),
                "pixel_counts_in_checked_masks": dict(pixels),
                "box_class_counts": dict(classes),
                "availability": dict(masks),
                "dimensions": dict(shapes),
                "reported_bit_depths": dict(depths),
                "near_pairs_in_decoded_pilot": sum(1 for _ in near_pairs(near)),
                "raw_bytes": meta["raw_bytes"],
                "raw_files": meta["raw_files"],
                "seconds": meta["seconds"],
                "output_bytes": sum(p.stat().st_size for p in folder.iterdir()),
            }
        field_batch = root / "processed/model2/field-v1-flood_field"
        native = {k: len(next(native_batches(field_batch, k, 3))) for k in ("model1", "model2")}
        queue = root / "annotations/model2/phase10g-field-v1/review-queue.jsonl"
        missing: set[str] = set()
        for p in (root / "simulation/field-v1/operational").glob("*.jsonl"):
            missing.update(r["report_id"] for r in rows(p) if r["missing"])
        incomplete = sum(
            row["features"]["receipt"]["report"]["message_id"] in missing for row in rows(queue)
        )
        cross = Counter(tuple(sorted(v)) for v in known.values() if len(v) > 1)
        write_json(
            out / "quality.json",
            {
                "datasets": summaries,
                "native_smoke_batches": native,
                "incomplete_focal_reports_in_queue": incomplete,
                "cross_dataset_exact_media": {" & ".join(k): v for k, v in cross.items()},
                "distinct_whole_text_overlap": len(texts["CrisisMMD"] & texts["HumAID"]),
                "crisis_benchmark": benchmark(root / "raw/multimodal/CrisisMMD", out),
                "governance": {
                    r["dataset_id"]: {
                        k: r.get(k)
                        for k in ("licence", "licence_status", "privacy_status", "verification")
                    }
                    for r in governance["datasets"]
                },
                "source_registry_sha256": digest(Path("configs/datasets/registry.json")),
                "storage": shutil.disk_usage(root)._asdict(),
                "approved_training_records": 0,
                "source_sha256": digest(Path(__file__)),
            },
        )
        out.rename(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    if args.root.resolve().drive.upper() != "D:":
        parser.error("use D: storage")
    run(args.root.resolve())
