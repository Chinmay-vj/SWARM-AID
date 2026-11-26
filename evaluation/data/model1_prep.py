"""Build private, candidate-only Phase 10I-B1/C1 Model 1 audit artifacts."""

import argparse
import hashlib
import json
import math
import shutil
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from evaluation.data.final_raw import inventory
from evaluation.data.model2 import digest
from evaluation.data.phase10g_quality import near_pairs
from evaluation.data.temporal_partitions import chronological

MODEL1_SOURCES = (
    "HERIDAL",
    "SARD",
    "FLAME",
    "FloodNet",
    "RescueNet",
    "WiSARD",
    "ESC-50",
    "Smoke",
    "UCI",
    "USGS",
)

VISUAL_SOURCES = {"HERIDAL", "SARD", "FLAME", "FloodNet", "RescueNet", "WiSARD"}
SEGMENTATION_SOURCES = {"FloodNet", "RescueNet"}
PUBLIC_SPLITS = {"train": "train", "valid": "validation", "val": "validation", "test": "test"}


class CandidateRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str = Field(min_length=1)
    partition: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    group_ref: str | None = None
    target: str = Field(min_length=1)
    target_label: str | None = None
    source_rows: tuple[int, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class CandidateManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["phase10i-candidate-1.0"]
    artifact_kind: Literal["candidate_only_not_approved_training_release"]
    dataset_id: str
    dataset_version: str | None
    task: str
    records_file: str
    records_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_records: int = Field(ge=0)
    partition_counts: dict[str, int]
    target_distribution: dict[str, int]
    partition_integrity: str
    source_index_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_inventory_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    training_approved: Literal[False] = False
    approved_training_records: Literal[0] = 0
    human_review_required: Literal[True] = True


def _json_rows(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def _write_json(path: Path, payload: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def _write_jsonl(path: Path, payloads: Iterable[BaseModel | dict[str, Any]]) -> str:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        for payload in payloads:
            item = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
            stream.write(
                json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            )
            stream.write("\n")
    return digest(path)


def _normalize_ref(reference: str) -> str:
    return reference.replace("\\", "/")


def _source_inventory_fingerprint(source: Path) -> tuple[str, int, int]:
    fingerprint = hashlib.sha256()
    files = 0
    size = 0
    for reference, stat in inventory(source):
        files += 1
        size += stat.st_size
        fingerprint.update(json.dumps([reference, stat.st_size, stat.st_mtime_ns]).encode("utf-8"))
    return fingerprint.hexdigest(), files, size


def _raw_key(reference: str, source: Path) -> str:
    normalized = _normalize_ref(reference)
    if source.is_file() and normalized in {".", source.name}:
        return "."
    return normalized


def _verify_source(
    root: Path,
    name: str,
    raw_ledger: dict[str, Any],
    expected_detail_hashes: dict[str, str],
) -> tuple[dict[str, Any], set[str]]:
    started = time.perf_counter()
    folder = root / "processed" / "phase10g-v1" / name
    meta = json.loads((folder / "summary.json").read_bytes())
    index = folder / "index.jsonl"
    source = Path(meta["configuration"]["source"])
    detail_name = raw_ledger["detail_file"]
    detail = root / "manifests" / "phase10i-a-raw-v1" / detail_name

    index_sha = digest(index)
    if index_sha != meta["outputs"]["index.jsonl"]:
        raise ValueError(f"{name}: Phase 10G index changed")
    if index_sha != raw_ledger["phase10g_index_sha256"]:
        raise ValueError(f"{name}: Phase 10I-A index binding changed")
    if digest(detail) != expected_detail_hashes[detail_name]:
        raise ValueError(f"{name}: Phase 10I-A raw hash ledger changed")

    current_inventory, current_files, current_bytes = _source_inventory_fingerprint(source)
    if current_inventory != meta["configuration"]["inventory_sha256"]:
        raise ValueError(f"{name}: current raw inventory differs from Phase 10G")
    if current_inventory != raw_ledger["current_inventory_sha256"]:
        raise ValueError(f"{name}: current raw inventory differs from Phase 10I-A")
    if (current_files, current_bytes) != (
        raw_ledger["current_files"],
        raw_ledger["current_bytes"],
    ):
        raise ValueError(f"{name}: current raw file count or size differs from Phase 10I-A")

    raw_hashes: dict[str, str] = {}
    raw_statuses: Counter[str] = Counter()
    raw_bytes = 0
    for item in _json_rows(detail):
        reference = _normalize_ref(item["path"])
        if reference in raw_hashes:
            raise ValueError(f"{name}: duplicate path in Phase 10I-A hash ledger")
        if not isinstance(item.get("sha256"), str) or len(item["sha256"]) != 64:
            raise ValueError(f"{name}: invalid Phase 10I-A hash for {reference}")
        if item.get("status") not in {"historical_match", "new_baseline"}:
            raise ValueError(f"{name}: unresolved raw hash status for {reference}")
        raw_hashes[reference] = item["sha256"]
        raw_statuses[item["status"]] += 1
        raw_bytes += item["bytes"]
    if len(raw_hashes) != current_files or raw_bytes != current_bytes:
        raise ValueError(f"{name}: Phase 10I-A hash ledger inventory mismatch")
    if raw_statuses != Counter(raw_ledger["hash_counts"]):
        raise ValueError(f"{name}: Phase 10I-A hash coverage summary mismatch")

    metadata_hashes: dict[str, str] = {}
    for reference, checksum in meta["source_digests"].items():
        key = _raw_key(reference, source)
        if raw_hashes.get(key) != checksum:
            raise ValueError(f"{name}: source metadata hash mismatch for {reference}")
        metadata_hashes[key] = checksum

    index_rows = 0
    exact_image_hashes: set[str] = set()
    asset_references: Counter[str] = Counter()
    modality_counts: Counter[str] = Counter()
    index_hash_groups: dict[str, list[tuple[str, str, str | None]]] = defaultdict(list)
    indexed_masks: set[str] = set()
    for row in _json_rows(index):
        index_rows += 1
        if row.get("path"):
            reference = _normalize_ref(row["path"])
            expected = raw_hashes.get(reference)
            if expected is None:
                raise ValueError(f"{name}: unverified indexed asset {reference}")
            if row.get("sha256") != expected:
                raise ValueError(f"{name}: indexed asset hash differs for {reference}")
            asset_references["indexed_path"] += 1
            if name in VISUAL_SOURCES and not (
                name == "FLAME" and row.get("task") == "unpaired_mask"
            ):
                exact_image_hashes.add(expected)
                split = str(row.get("split") or row.get("fold") or "unassigned")
                index_hash_groups[expected].append(
                    (reference, split, str(row.get("label")) if row.get("label") else None)
                )
            if row.get("modality"):
                modality_counts[str(row["modality"])] += 1
            elif name == "WiSARD":
                modality_counts[str(row.get("modality", "image"))] += 1
        if row.get("mask"):
            reference = _normalize_ref(row["mask"])
            if reference not in raw_hashes:
                raise ValueError(f"{name}: unverified indexed mask {reference}")
            indexed_masks.add(reference)
            asset_references["indexed_mask"] += 1
        if row.get("source"):
            key = _raw_key(str(row["source"]), source)
            if key not in metadata_hashes and key not in raw_hashes:
                raise ValueError(f"{name}: unverified source metadata {row['source']}")
        if name == "WiSARD" and row.get("annotation"):
            sidecar = _normalize_ref(str(Path(row["path"]).with_suffix(".txt")))
            if sidecar not in raw_hashes:
                raise ValueError(f"{name}: indexed sidecar missing from raw ledger")
            asset_references["indexed_sidecar"] += 1

    unmatched_masks = 0
    if name in SEGMENTATION_SOURCES:
        source_masks = {
            reference
            for reference in raw_hashes
            if Path(reference).name.endswith("_lab.png")
            and Path(reference).parent.name.endswith("-label-img")
        }
        unmatched_masks = len(source_masks - indexed_masks)
        if unmatched_masks:
            raise ValueError(f"{name}: unindexed class-index masks remain")

    if index_rows != meta["counts"]["valid"]:
        raise ValueError(f"{name}: index row count differs from source summary")

    visual_summary: dict[str, Any] = {}
    flags: list[dict[str, Any]] = []
    visual_folder = root / "manifests" / "phase10g-visual-v1" / name
    if name in VISUAL_SOURCES:
        visual_summary = json.loads((visual_folder / "summary.json").read_bytes())
        if visual_summary["index_sha256"] != index_sha:
            raise ValueError(f"{name}: visual audit bound to a different index")
        if digest(visual_folder / "flags.jsonl") != visual_summary["flags_sha256"]:
            raise ValueError(f"{name}: visual flags checksum mismatch")
        if digest(visual_folder / "frame-hashes.jsonl") != visual_summary["frame_hashes_sha256"]:
            raise ValueError(f"{name}: visual frame-hash checksum mismatch")
        flags = list(_json_rows(visual_folder / "flags.jsonl"))
        if len(flags) != visual_summary["counts"].get("invalid", 0):
            raise ValueError(f"{name}: visual flag count mismatch")

    report = {
        "dataset": name,
        "source_path": str(source),
        "source_version_evidence": meta["configuration"].get("source_version"),
        "index_rows": index_rows,
        "index_sha256": index_sha,
        "source_inventory_sha256": current_inventory,
        "raw_files": current_files,
        "raw_bytes": current_bytes,
        "historical_hash_matches": raw_statuses["historical_match"],
        "new_baseline_hashes": raw_statuses["new_baseline"],
        "indexed_hash_references_verified": dict(asset_references),
        "unmatched_class_index_masks": unmatched_masks,
        "index_distributions": meta.get("distributions", {}),
        "index_counts": meta.get("counts", {}),
        "index_modality_counts": dict(sorted(modality_counts.items())),
        "visual_counts": visual_summary.get("counts", {}),
        "visual_flags": len(flags),
        "visual_summary_sha256": (
            digest(visual_folder / "summary.json") if visual_summary else None
        ),
        "exact_image_hash_groups_with_repeats": sum(
            len(group) > 1 for group in index_hash_groups.values()
        ),
        "exact_cross_split_image_hash_groups": sum(
            len({split for _, split, _ in group}) > 1 for group in index_hash_groups.values()
        ),
        "seconds": round(time.perf_counter() - started, 3),
    }
    return report, exact_image_hashes


def _normalized_split(value: str | None) -> str:
    if value is None or value not in PUBLIC_SPLITS:
        raise ValueError(f"unrecognized publisher split: {value}")
    return PUBLIC_SPLITS[value]


def audit_coco(root: Path, name: str) -> dict[str, Any]:
    folder = root / "processed" / "phase10g-v1" / name
    source = Path(json.loads((folder / "summary.json").read_bytes())["configuration"]["source"])
    empty: dict[str, list[dict[str, Any]]] = defaultdict(list)
    category_ids: Counter[str] = Counter()
    category_labels: Counter[str] = Counter()
    invalid_boxes = 0
    total_boxes = 0
    rows_count = 0
    for row in _json_rows(folder / "index.jsonl"):
        rows_count += 1
        split = _normalized_split(row.get("split"))
        if row.get("error"):
            raise ValueError(f"{name}: source index contains invalid row")
        if not row.get("annotations"):
            empty[split].append(row)
        categories = row["categories"]
        for annotation in row.get("annotations", []):
            total_boxes += 1
            category_id = str(annotation["category_id"])
            if category_id not in categories:
                invalid_boxes += 1
                continue
            category_ids[category_id] += 1
            category_labels[categories[category_id]] += 1
            box = annotation.get("bbox", [])
            if len(box) != 4:
                invalid_boxes += 1
                continue
            x, y, width, height = (float(value) for value in box)
            image_width, image_height = row["size"]
            if (
                not all(math.isfinite(value) for value in (x, y, width, height))
                or x < 0
                or y < 0
                or width <= 0
                or height <= 0
                or x + width > image_width
                or y + height > image_height
                or annotation.get("image_id") != row.get("image_id")
            ):
                invalid_boxes += 1
    meta = json.loads((folder / "summary.json").read_bytes())
    if sum(len(values) for values in empty.values()) != meta["counts"]["empty_boxes"]:
        raise ValueError(f"{name}: invalid empty annotation count")
    return {
        "rows": rows_count,
        "empty_annotation_rows": sum(len(values) for values in empty.values()),
        "empty_annotation_by_split": {key: len(value) for key, value in sorted(empty.items())},
        "class_counts_by_category_id": dict(sorted(category_ids.items())),
        "class_counts_by_category_name": dict(sorted(category_labels.items())),
        "empty_rows_for_review": {
            split: sorted(
                values,
                key=lambda row: hashlib.sha256(
                    f"{name}|{split}|{row['path']}".encode()
                ).hexdigest(),
            )[:10]
            for split, values in sorted(empty.items())
        },
        "boxes": total_boxes,
        "invalid_boxes": invalid_boxes,
        "source_metadata": {
            "local_readme": str(
                source / ("README.roboflow.txt" if name == "HERIDAL" else "README.dataset.txt")
            ),
            "category_id_aliases": name == "HERIDAL" or name == "SARD",
            "parent_flight_or_site_fields_in_index": False,
        },
    }


def audit_flame(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[CandidateRow]]:
    folder = root / "processed" / "phase10g-v1" / "FLAME"
    visual = root / "manifests" / "phase10g-visual-v1" / "FLAME"
    visual_summary = json.loads((visual / "summary.json").read_bytes())
    indexed = list(_json_rows(folder / "index.jsonl"))
    frames = list(_json_rows(visual / "frame-hashes.jsonl"))
    hashes = [int(row["dhash"], 16) for row in frames]
    by_path = {row["path"]: row for row in indexed if row.get("split")}
    frame_by_path = {row["path"]: row for row in frames}
    neighbors: dict[str, dict[str, int]] = defaultdict(dict)
    distance_counts: Counter[str] = Counter()
    for left, right in near_pairs(hashes):
        first, second = frames[left], frames[right]
        if {first["split"], second["split"]} != {"train", "test"}:
            continue
        train = first if first["split"] == "train" else second
        test = second if second["split"] == "test" else first
        distance = (hashes[left] ^ hashes[right]).bit_count()
        neighbors[train["path"]][test["path"]] = distance
        distance_counts[str(distance)] += 1
    if len(frame_by_path) != len(frames) or set(frame_by_path) - set(by_path):
        raise ValueError("FLAME visual hashes do not map one-to-one to image rows")

    exact_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in indexed:
        if row.get("split"):
            exact_groups[row["sha256"]].append(row)
    repeated = [group for group in exact_groups.values() if len(group) > 1]
    cross_split_exact = [group for group in repeated if len({row["split"] for row in group}) > 1]
    expected_near = visual_summary["counts"]["train_frames_near_any_test_frame"]
    if len(neighbors) != expected_near:
        raise ValueError("FLAME recomputed near-test exclusions differ from the frozen visual audit")
    if cross_split_exact:
        raise ValueError("FLAME exact content hashes cross the official train/test split")
    train_labels_before: Counter[str] = Counter()
    train_labels_after: Counter[str] = Counter()
    test_labels: Counter[str] = Counter()
    for row in indexed:
        if not row.get("split"):
            continue
        label = str(row["label"])
        if row["split"] == "test":
            test_labels[label] += 1
        else:
            train_labels_before[label] += 1
            if row["path"] not in neighbors:
                train_labels_after[label] += 1

    overlay = [
        {
            "dataset": "FLAME",
            "path": path,
            "split": "train",
            "dhash": frame_by_path[path]["dhash"],
            "matched_test_paths": [
                {"path": test_path, "hamming_distance": distance}
                for test_path, distance in sorted(neighbors[path].items())
            ],
            "reason": "dhash_hamming_distance_at_most_3_to_official_test_frame",
            "training_approved": False,
        }
        for path in sorted(neighbors)
    ]
    candidate_rows = [
        CandidateRow(
            record_id=hashlib.sha256(f"FLAME|{row['path']}|{row['sha256']}".encode()).hexdigest()[
                :24
            ],
            partition=str(row["split"]),
            source_path=row["path"],
            source_sha256=row["sha256"],
            target="frame fire classification",
            metadata={"official_split": row["split"]},
        )
        for row in sorted(indexed, key=lambda row: row["path"])
        if row.get("split") and not (row["split"] == "train" and row["path"] in neighbors)
    ]
    return (
        {
            "indexed_frames": len(frames),
            "near_test_pair_count": sum(distance_counts.values()),
            "near_test_distance_counts": dict(sorted(distance_counts.items())),
            "training_frames_excluded": len(neighbors),
            "near_test_training_paths": sorted(neighbors),
            "exact_image_hash_groups_with_repeats": len(repeated),
            "exact_cross_split_image_hash_groups": len(cross_split_exact),
            "exact_image_hash_duplicate_rows": sum(len(group) - 1 for group in repeated),
            "official_train_class_distribution_before": dict(sorted(train_labels_before.items())),
            "official_train_class_distribution_after_near_exclusion": dict(
                sorted(train_labels_after.items())
            ),
            "official_test_class_distribution_unchanged": dict(sorted(test_labels.items())),
            "verified_video_group_field": False,
            "fire_masks": sum(row.get("task") == "unpaired_mask" for row in indexed),
            "verified_fire_mask_image_pairs": 0,
            "candidate_partition_integrity": "PREPARATION_ONLY_GROUPING_BLOCKED",
        },
        overlay,
        candidate_rows,
    )


def audit_masks(root: Path, name: str, workers: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    folder = root / "processed" / "phase10g-v1" / name
    source = Path(json.loads((folder / "summary.json").read_bytes())["configuration"]["source"])
    indexed = [row for row in _json_rows(folder / "index.jsonl") if row.get("mask")]
    class_pixels: dict[str, Counter[str]] = defaultdict(Counter)
    class_images: dict[str, Counter[str]] = defaultdict(Counter)
    review_paths: dict[tuple[str, str], tuple[str, str]] = {}
    allowed = set(range(11 if name == "RescueNet" else 10))

    def inspect(row: dict[str, Any]) -> tuple[dict[str, int], str]:
        from PIL import Image

        mask_path = source / row["mask"]
        with Image.open(mask_path) as mask:
            if mask.size != tuple(row["size"]) or mask.mode not in {"L", "P", "I", "I;16"}:
                raise ValueError(f"{name}: mask dimensions or mode changed: {row['mask']}")
            values = mask.getcolors(256)
            if values is None:
                raise ValueError(f"{name}: mask contains more than 256 classes: {row['mask']}")
            histogram: dict[str, int] = {}
            for count, class_id in values:
                if not isinstance(class_id, int):
                    raise TypeError(f"{name}: mask class is not a scalar index: {row['mask']}")
                histogram[str(class_id)] = count
            if any(int(class_id) not in allowed for class_id in histogram):
                raise ValueError(f"{name}: mask has an unknown class: {row['mask']}")
        return histogram, _normalized_split(row["split"])

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for offset in range(0, len(indexed), 16):
            batch = indexed[offset : offset + 16]
            results = list(pool.map(inspect, batch))
            for row, (histogram, split) in zip(batch, results, strict=True):
                for key, pixels in histogram.items():
                    class_pixels[split][key] += pixels
                    if pixels:
                        class_images[split][key] += 1
                        stable = hashlib.sha256(
                            f"{name}|{split}|{key}|{row['mask']}".encode()
                        ).hexdigest()
                        previous = review_paths.get((split, key))
                        if previous is None or stable < previous[0]:
                            review_paths[(split, key)] = (stable, row["mask"])

    expected = json.loads(
        (root / "manifests" / "phase10g-visual-v1" / name / "summary.json").read_bytes()
    )["mask_pixels"]
    totals: Counter[str] = Counter()
    for per_split in class_pixels.values():
        totals.update(per_split)
    if dict(sorted(totals.items())) != dict(sorted(expected.items())):
        raise ValueError(f"{name}: mask class pixel counts differ from the frozen visual audit")

    focus: dict[str, set[str]] = defaultdict(set)
    path_splits: dict[str, str] = {}
    for (split, class_id), (_, path) in sorted(review_paths.items()):
        focus[path].add(class_id)
        path_splits[path] = split
    reviews = [
        {
            "dataset": name,
            "source_path": path,
            "split": path_splits[path],
            "focus_class_ids": sorted(focus_classes, key=int),
            "review_status": "pending",
            "decision": None,
            "human_annotation_created": False,
        }
        for path, focus_classes in sorted(focus.items())
    ]
    class_names = (
        {
            "0": "background",
            "1": "building_flooded",
            "2": "building_non_flooded",
            "3": "road_flooded",
            "4": "road_non_flooded",
            "5": "water",
            "6": "tree",
            "7": "vehicle",
            "8": "pool",
            "9": "grass",
        }
        if name == "FloodNet"
        else {
            "0": "background",
            "1": "water",
            "2": "building_no_damage",
            "3": "building_minor_damage",
            "4": "building_major_damage",
            "5": "building_total_destruction",
            "6": "road_clear",
            "7": "road_blocked",
            "8": "vehicle",
            "9": "tree",
            "10": "pool",
        }
    )
    return (
        {
            "source": name,
            "mask_count": len(indexed),
            "publisher_split_counts": dict(
                sorted(Counter(_normalized_split(row["split"]) for row in indexed).items())
            ),
            "class_names_from_publisher_readme": class_names,
            "pixel_counts_before_by_split": {
                split: dict(sorted(counts.items()))
                for split, counts in sorted(class_pixels.items())
            },
            "pixel_counts_after_by_split": {
                split: dict(sorted(counts.items()))
                for split, counts in sorted(class_pixels.items())
            },
            "images_containing_class_by_split": {
                split: dict(sorted(counts.items()))
                for split, counts in sorted(class_images.items())
            },
            "total_pixel_counts": dict(sorted(totals.items())),
            "mask_pair_status": "verified image-mask paths from source index",
            "site_or_flight_group_status": "unverified",
            "candidate_rows_excluded": 0,
            "seconds": round(time.perf_counter() - started, 3),
        },
        reviews,
    )


def build_esc50_candidate(
    rows_in: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[CandidateRow]]:
    folds_by_source: dict[str, set[int]] = defaultdict(set)
    rows_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows_in:
        group = str(row["group"])
        folds_by_source[group].add(int(row["fold"]))
        rows_by_source[group].append(row)
    repeated = {group: sorted(folds) for group, folds in folds_by_source.items() if len(folds) > 1}
    if set(repeated) != {"131943", "134049", "209698", "234879"}:
        raise ValueError("ESC-50 cross-fold recording IDs differ from the audited set")
    excluded = {row["path"] for group in repeated for row in rows_by_source[group]}
    overlay = [
        {
            "dataset": "ESC-50",
            "source_path": row["path"],
            "recording_id": str(row["group"]),
            "official_fold": int(row["fold"]),
            "reason": "publisher_source_recording_id_crosses_official_folds",
            "training_approved": False,
        }
        for row in sorted(rows_in, key=lambda item: item["path"])
        if row["path"] in excluded
    ]
    retained = [row for row in rows_in if row["path"] not in excluded]
    before: Counter[str] = Counter(str(row["label"]) for row in rows_in)
    after: Counter[str] = Counter(str(row["label"]) for row in retained)
    before_folds: Counter[str] = Counter(str(row["fold"]) for row in rows_in)
    after_folds: Counter[str] = Counter(str(row["fold"]) for row in retained)
    candidate_rows = [
        CandidateRow(
            record_id=hashlib.sha256(f"ESC-50|{row['path']}|{row['sha256']}".encode()).hexdigest()[
                :24
            ],
            partition=f"official-fold-{row['fold']}",
            source_path=row["path"],
            source_sha256=row["sha256"],
            group_ref=str(row["group"]),
            target="environmental sound classification",
            metadata={"fold": int(row["fold"]), "sample_rate_hz": int(row["rate"])},
        )
        for row in sorted(retained, key=lambda item: item["path"])
    ]
    return (
        {
            "publisher_recording_groups_crossing_folds": repeated,
            "excluded_records": len(excluded),
            "excluded_by_recording_id": {
                group: len(rows_by_source[group]) for group in sorted(repeated)
            },
            "class_distribution_before": dict(sorted(before.items())),
            "class_distribution_after": dict(sorted(after.items())),
            "fold_distribution_before": dict(sorted(before_folds.items())),
            "fold_distribution_after": dict(sorted(after_folds.items())),
            "retained_records": len(retained),
            "recording_group_field": "publisher src_file identifier",
            "candidate_partition_integrity": "TECHNICALLY_VALID_CANDIDATE",
        },
        overlay,
        candidate_rows,
    )


def build_uci_windows(
    rows_in: list[dict[str, Any]],
    source_path: str,
    source_sha256: str,
    lookback_hours: int = 24,
) -> tuple[dict[str, Any], list[CandidateRow]]:
    if lookback_hours <= 0:
        raise ValueError("lookback_hours must be positive")
    ordered = sorted(rows_in, key=lambda row: datetime.fromisoformat(row["timestamp"]))
    by_timestamp: dict[datetime, dict[str, Any]] = {}
    for row in ordered:
        timestamp = datetime.fromisoformat(row["timestamp"])
        if timestamp in by_timestamp:
            raise ValueError("UCI index contains duplicate timestamps")
        by_timestamp[timestamp] = row
    if not ordered:
        raise ValueError("UCI source index is empty")

    by_day: dict[str, list[datetime]] = defaultdict(list)
    for timestamp in by_timestamp:
        by_day[timestamp.date().isoformat()].append(timestamp)
    day_spans = [
        (day, min(stamps).isoformat(), max(stamps).isoformat())
        for day, stamps in sorted(by_day.items())
    ]
    assignment = chronological(day_spans)
    split_by_timestamp = {
        timestamp: assignment[timestamp.date().isoformat()] for timestamp in by_timestamp
    }
    if set(assignment.values()) != {"train", "validation", "test"}:
        raise ValueError("UCI chronological proposal did not create all three partitions")

    missing_target_rows = 0
    valid_target_rows_by_partition: Counter[str] = Counter()
    windows: list[CandidateRow] = []
    cross_partition_rows: dict[int, set[str]] = defaultdict(set)
    time_gaps = Counter[str]()
    for position, row in enumerate(ordered):
        target_time = datetime.fromisoformat(row["timestamp"])
        target_value = row["measurements"]["CO(GT)"]
        partition = split_by_timestamp[target_time]
        if target_value[2] is None or target_value[4]:
            missing_target_rows += 1
            continue
        valid_target_rows_by_partition[partition] += 1
        feature_rows = ordered[max(0, position - lookback_hours) : position]
        if len(feature_rows) != lookback_hours:
            time_gaps["insufficient_lookback"] += 1
            continue
        feature_times = [datetime.fromisoformat(item["timestamp"]) for item in feature_rows]
        if feature_times[-1] + timedelta(hours=1) != target_time:
            time_gaps["target_gap"] += 1
            continue
        if any(right - left != timedelta(hours=1) for left, right in pairwise(feature_times)):
            time_gaps["feature_gap"] += 1
            continue
        row_times = [*feature_times, target_time]
        if any(split_by_timestamp[value] != partition for value in row_times):
            time_gaps["partition_boundary_purge"] += 1
            continue
        lines = tuple(int(item["line"]) for item in feature_rows)
        for line in lines:
            cross_partition_rows[line].add(partition)
        missing_features = sum(
            bool(value[4]) for item in feature_rows for value in item["measurements"].values()
        )
        windows.append(
            CandidateRow(
                record_id=hashlib.sha256(
                    f"UCI|{row['timestamp']}|{source_sha256}".encode()
                ).hexdigest()[:24],
                partition=partition,
                source_path=source_path,
                source_sha256=source_sha256,
                group_ref=target_time.date().isoformat(),
                target="CO(GT) at t; one-hour-ahead from latest hourly input, mg/m^3",
                source_rows=lines,
                metadata={
                    "input_window_start": feature_times[0].isoformat(),
                    "input_window_end": feature_times[-1].isoformat(),
                    "target_timestamp": target_time.isoformat(),
                    "lookback_hours": lookback_hours,
                    "horizon_hours": 1,
                    "missing_feature_cells": missing_features,
                    "missing_values_preserved": True,
                },
            )
        )
    if any(len(partitions) > 1 for partitions in cross_partition_rows.values()):
        raise ValueError("UCI source row is shared across candidate partitions")

    counts = Counter(window.partition for window in windows)
    return (
        {
            "timestamp_rows": len(ordered),
            "day_groups": len(by_day),
            "day_group_assignments": assignment,
            "source_row_counts_by_partition": dict(
                sorted(Counter(split_by_timestamp.values()).items())
            ),
            "candidate_windows_by_partition": dict(sorted(counts.items())),
            "candidate_windows": len(windows),
            "valid_target_rows_by_partition": dict(sorted(valid_target_rows_by_partition.items())),
            "lookback_hours": lookback_hours,
            "forecast_horizon_hours": 1,
            "target": "CO(GT)",
            "target_unit": "mg/m^3",
            "target_missing_rows_excluded": missing_target_rows,
            "gap_and_purge_counts": dict(sorted(time_gaps.items())),
            "cross_partition_raw_row_overlap": 0,
            "publisher_site_group_available": False,
            "candidate_partition_integrity": "TECHNICALLY_VALID_CANDIDATE_TEMPORAL_ONLY",
            "missing_value_policy": "preserve sentinel-derived missing flags; no imputation in this phase",
        },
        windows,
    )


def _review_id(source: str, path: str, reason: str) -> str:
    return hashlib.sha256(f"{source}|{path}|{reason}".encode()).hexdigest()[:24]


def build_review_queue(
    coco: dict[str, dict[str, Any]],
    wisard_flags: list[dict[str, Any]],
    mask_reviews: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    for source, audit in sorted(coco.items()):
        for split, examples in audit["empty_rows_for_review"].items():
            for row in examples:
                path = str(row["path"])
                queue.append(
                    {
                        "review_id": _review_id(source, path, "empty_coco_annotation"),
                        "dataset": source,
                        "source_path": path,
                        "split": split,
                        "review_task": "determine whether empty annotation means no person, omitted label, or other",
                        "source_sha256": row["sha256"],
                        "annotation_state": "empty_array",
                        "review_status": "pending",
                        "decision": None,
                        "reviewer": None,
                        "human_annotation_created": False,
                        "estimated_minutes": 3,
                    }
                )

    by_sequence: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for flag in wisard_flags:
        parts = str(flag["path"]).replace("\\", "/").split("/")
        sequence = parts[0] if parts else "unknown-sequence"
        by_sequence[sequence].append(flag)
    ordered_by_sequence = {
        sequence: sorted(
            flags,
            key=lambda row: hashlib.sha256(str(row["path"]).encode("utf-8")).hexdigest(),
        )[:3]
        for sequence, flags in sorted(by_sequence.items())
    }
    wisard_sample = [
        flags[offset]
        for offset in range(3)
        for flags in ordered_by_sequence.values()
        if offset < len(flags)
    ][:30]
    for flag in wisard_sample:
        path = str(flag["path"])
        queue.append(
            {
                "review_id": _review_id("WiSARD", path, "invalid_normalized_box"),
                "dataset": "WiSARD",
                "source_path": path,
                "review_task": "classify invalid sidecar geometry and whether source format or label requires correction",
                "flag": flag.get("error"),
                "review_status": "pending",
                "decision": None,
                "reviewer": None,
                "human_annotation_created": False,
                "estimated_minutes": 2,
            }
        )
    for item in mask_reviews:
        path = str(item["source_path"])
        queue.append(
            {
                "review_id": _review_id(
                    str(item["dataset"]),
                    path,
                    "mask_label_semantics",
                ),
                "dataset": item["dataset"],
                "source_path": path,
                "split": item["split"],
                "review_task": "compare source mask classes with the publisher legend and visible scene",
                "focus_class_ids": item["focus_class_ids"],
                "review_status": "pending",
                "decision": None,
                "reviewer": None,
                "human_annotation_created": False,
                "estimated_minutes": 3,
            }
        )
    return sorted(queue, key=lambda item: item["review_id"])


def _candidate_manifest(
    *,
    dataset_id: str,
    version: str | None,
    task: str,
    records_path: str,
    records_sha256: str,
    records: list[CandidateRow],
    source_index_sha256: str,
    raw_inventory_sha256: str,
    target_distribution: Counter[str],
    partition_integrity: str,
) -> CandidateManifest:
    return CandidateManifest(
        schema_version="phase10i-candidate-1.0",
        artifact_kind="candidate_only_not_approved_training_release",
        dataset_id=dataset_id,
        dataset_version=version,
        task=task,
        records_file=records_path,
        records_sha256=records_sha256,
        candidate_records=len(records),
        partition_counts=dict(sorted(Counter(row.partition for row in records).items())),
        target_distribution=dict(sorted(target_distribution.items())),
        partition_integrity=partition_integrity,
        source_index_sha256=source_index_sha256,
        raw_inventory_sha256=raw_inventory_sha256,
    )


def _governance_evidence(registry: dict[str, Any]) -> dict[str, Any]:
    evidence: dict[str, dict[str, Any]] = {
        "HERIDAL": {
            "urls": ["http://ipsar.fesb.unist.hr/HERIDAL%20database.html"],
            "observed": "Official page fetch failed at DNS/TLS; local Roboflow export README states 1,600 COCO person images.",
            "licence_finding": "No usable dataset licence evidence found.",
            "privacy_review": "Pending: aerial person imagery; location and identity risk not cleared.",
        },
        "SARD": {
            "urls": [
                "https://raass.uniri.hr/?p=646",
                "https://universe.roboflow.com/datasets-pdabr/sard-8xjhy",
            ],
            "observed": "Local README identifies a Roboflow v17 3x3 tile export and says licence undefined; public Roboflow page returned 403.",
            "licence_finding": "Unresolved; no permission inferred.",
            "privacy_review": "Pending: aerial person imagery and unknown parent capture grouping.",
        },
        "FLAME": {
            "urls": ["https://sites.google.com/g.clemson.edu/is-win-lab/resources/datasets"],
            "observed": "Official page returned only a datasets heading; local task labels and paths do not establish publisher release terms.",
            "licence_finding": "No usable dataset licence evidence found.",
            "privacy_review": "Pending: aerial fire footage and unknown capture-video grouping.",
        },
        "FloodNet": {
            "urls": ["https://github.com/BinaLab/FloodNet-Supervised_v1.0"],
            "observed": "Publisher README describes Hurricane Harvey UAS imagery and states Community Data License Agreement (permissive) 1.0.",
            "licence_finding": "Source-reported CDLA Permissive 1.0; local archive identity and privacy review remain pending. No approval granted.",
            "privacy_review": "Pending: aerial post-disaster imagery; no cloud transfer.",
        },
        "RescueNet": {
            "urls": [
                "https://github.com/BinaLab/RescueNet-A-High-Resolution-Post-Disaster-UAV-Dataset-for-Semantic-Segmentation"
            ],
            "observed": "Publisher README describes Hurricane Michael UAS imagery and states the dataset is CC BY-NC-ND 4.0. GitHub repository code is separately marked MIT.",
            "licence_finding": "Dataset README says CC BY-NC-ND 4.0; do not treat repository code MIT as dataset permission. Local archive identity and legal review pending.",
            "privacy_review": "Pending: aerial post-disaster imagery and building damage labels.",
        },
        "WiSARD": {
            "urls": ["https://sites.google.com/uw.edu/wisard"],
            "observed": "Official page did not expose usable licence text; local folders and sidecars do not establish rights or calibrated pairing.",
            "licence_finding": "Unresolved; no permission inferred.",
            "privacy_review": "Pending: RGB/thermal search imagery, human presence, capture metadata and local-only handling.",
        },
        "ESC-50": {
            "urls": ["https://github.com/karolpiczak/ESC-50"],
            "observed": "Source README says 2,000 five-second clips from Freesound, grouped by source recording. The bundled LICENSE states overall CC BY-NC 3.0, ESC-10 CC BY 3.0, and per-clip terms.",
            "licence_finding": "Clip-level licence/attribution must be checked; overall repository terms are not assumed to clear every recording.",
            "privacy_review": "Pending source-audio review; non-speech human sounds occur in some classes.",
        },
        "Smoke": {
            "urls": [
                "https://community.element14.com/products/arduino/arduino-projects/b/blog/posts/real-time-smoke-detection-with-ai-based-sensor-fusion"
            ],
            "observed": "Source page returned 403; local CSV is not accompanied by a usable licence grant or independent alarm-label provenance.",
            "licence_finding": "Unresolved; no permission inferred.",
            "privacy_review": "Pending source provenance and collection-site review.",
        },
        "UCI": {
            "urls": ["https://archive.ics.uci.edu/dataset/360/air+quality"],
            "observed": "UCI metadata states CC BY 4.0 and also says use exclusively for research, with commercial purposes excluded.",
            "licence_finding": "Conflicting/restrictive source statements require owner/legal reconciliation; no training approval.",
            "privacy_review": "Pending: timestamped measurements from a single urban monitoring location.",
        },
        "USGS": {
            "urls": ["https://api.waterdata.usgs.gov/download/"],
            "observed": "USGS download documentation describes API data retrieval but did not establish reuse terms for this local interval-summary file.",
            "licence_finding": "Unresolved for this artifact; no permission inferred.",
            "privacy_review": "Pending source/station metadata review; no personal identifiers observed in the index.",
        },
    }
    entries = {str(item["dataset_id"]): item for item in registry["datasets"]}
    registry_ids = {
        "HERIDAL": "heridal",
        "SARD": "sard",
        "FLAME": "flame",
        "FloodNet": "floodnet",
        "RescueNet": "rescuenet",
        "WiSARD": "wisard",
        "ESC-50": "esc50",
        "Smoke": "smoke-detection-iot",
        "UCI": "uci-air-quality",
        "USGS": "usgs-water-data",
    }
    result: dict[str, Any] = {}
    for source in MODEL1_SOURCES:
        entry = entries[registry_ids[source]]
        result[source] = {
            **evidence[source],
            "registry_dataset_id": entry["dataset_id"],
            "registry_version": entry.get("version"),
            "registry_licence_status": entry["licence_status"],
            "registry_privacy_status": entry["privacy_status"],
            "registry_verification": entry["verification"],
            "training_approved": False,
        }
    return {
        "evidence_date": datetime.now(UTC).date().isoformat(),
        "status": "HUMAN_GOVERNANCE_REVIEW_PENDING",
        "sources": result,
        "prohibited_inference": "A source webpage or repository-code licence is not dataset authorization; no permissions are granted by this report.",
        "cloud_gpu_transfer": "not authorized",
        "redistribution": "not authorized",
    }


def _model1_readiness(
    coco: dict[str, Any],
    flame: dict[str, Any],
    masks: dict[str, Any],
    wisard: dict[str, Any],
    esc: dict[str, Any],
    sensors: dict[str, Any],
) -> dict[str, Any]:
    tasks = [
        {
            "task": "RGB person detection",
            "sources": ["HERIDAL", "SARD"],
            "status": "BLOCKED",
            "blocker_categories": [
                "HUMAN_REVIEW_REQUIRED",
                "BLOCKED_METADATA",
                "GOVERNANCE_PENDING",
            ],
            "candidate_artifact": False,
            "blockers": [
                "Parent flight/site IDs are absent.",
                f"{coco['HERIDAL']['empty_annotation_rows']} HERIDAL and {coco['SARD']['empty_annotation_rows']} SARD empty annotations need source-policy review.",
                "Category aliases and source rights/privacy remain pending.",
            ],
        },
        {
            "task": "RGB fire classification",
            "sources": ["FLAME"],
            "status": "BLOCKED",
            "blocker_categories": ["BLOCKED_METADATA", "GOVERNANCE_PENDING"],
            "candidate_artifact": True,
            "blockers": [
                f"Excluded {flame['training_frames_excluded']} train frames near official test frames.",
                "Parent video/capture groups are unavailable; near-frame exclusion does not establish group independence.",
                "Rights and privacy remain pending.",
            ],
        },
        {
            "task": "FloodNet semantic segmentation",
            "sources": ["FloodNet"],
            "status": "BLOCKED",
            "blocker_categories": ["BLOCKED_METADATA", "GOVERNANCE_PENDING"],
            "candidate_artifact": False,
            "blockers": [
                "Publisher event is Hurricane Harvey; site/capture groups are not present.",
                "Source rights correspondence and privacy review remain pending.",
            ],
        },
        {
            "task": "RescueNet semantic segmentation",
            "sources": ["RescueNet"],
            "status": "BLOCKED",
            "blocker_categories": ["BLOCKED_METADATA", "GOVERNANCE_PENDING"],
            "candidate_artifact": False,
            "blockers": [
                "Publisher event is Hurricane Michael; site/capture groups are not present.",
                "CC BY-NC-ND dataset terms and privacy review remain pending.",
            ],
        },
        {
            "task": "RescueNet infrastructure damage assessment",
            "sources": ["RescueNet"],
            "status": "BLOCKED",
            "blocker_categories": [
                "HUMAN_REVIEW_REQUIRED",
                "BLOCKED_METADATA",
                "GOVERNANCE_PENDING",
            ],
            "candidate_artifact": False,
            "blockers": [
                "Damage-grade semantics require independent review, including rare classes.",
                "Site/capture groups and dataset governance remain unresolved.",
            ],
        },
        {
            "task": "FLAME fire segmentation",
            "sources": ["FLAME"],
            "status": "BLOCKED",
            "blocker_categories": ["BLOCKED_DATA_QUALITY", "GOVERNANCE_PENDING"],
            "candidate_artifact": False,
            "blockers": [
                f"{flame['fire_masks']} masks have no verified image pair.",
                "No mask-to-frame matching was inferred from filenames.",
            ],
        },
        {
            "task": "WiSARD thermal perception",
            "sources": ["WiSARD"],
            "status": "BLOCKED",
            "blocker_categories": [
                "HUMAN_REVIEW_REQUIRED",
                "BLOCKED_METADATA",
                "GOVERNANCE_PENDING",
            ],
            "candidate_artifact": False,
            "blockers": [
                f"{wisard['visual_flags']} invalid normalized-box flags remain unadjudicated.",
                f"{wisard['missing_annotation_sidecars']} images have no sidecar; absence is not a negative label.",
                "Thermal imagery is RGB/8-bit display-coded, not calibrated temperature.",
            ],
        },
        {
            "task": "WiSARD RGB-thermal pairing",
            "sources": ["WiSARD"],
            "status": "BLOCKED",
            "blocker_categories": ["BLOCKED_METADATA", "GOVERNANCE_PENDING"],
            "candidate_artifact": False,
            "blockers": [
                "Zero verified pairs; authoritative synchronization, alignment, calibration and capture IDs are absent."
            ],
        },
        {
            "task": "ESC-50 environmental sound classification",
            "sources": ["ESC-50"],
            "status": "BLOCKED",
            "blocker_categories": ["GOVERNANCE_PENDING"],
            "candidate_artifact": True,
            "blockers": [
                f"Excluded {esc['excluded_records']} clips in four cross-fold source recording groups.",
                "Clip-specific terms and attribution require human review.",
                "This generic sound task is not a distress-detection target.",
            ],
        },
        {
            "task": "Smoke Detection IoT time-series classification",
            "sources": ["Smoke"],
            "status": "BLOCKED",
            "blocker_categories": ["BLOCKED_SPLIT", "GOVERNANCE_PENDING"],
            "candidate_artifact": False,
            "blockers": [
                "Five counter runs reduce to three repeated sensor-signature groups with overlapping intervals.",
                "Run identity and alarm-label provenance are unresolved.",
            ],
        },
        {
            "task": "UCI next-hour CO concentration",
            "sources": ["UCI"],
            "status": "BLOCKED",
            "blocker_categories": ["GOVERNANCE_PENDING", "SINGLE_SITE_LIMITATION"],
            "candidate_artifact": True,
            "blockers": [
                "A temporal-only 24-hour lookback / 1-hour horizon candidate has a boundary purge and zero cross-partition row reuse.",
                "Single-site evaluation does not establish site generalization.",
                "UCI page contains research-only/commercial exclusion language alongside CC BY 4.0 metadata.",
            ],
        },
        {
            "task": "USGS interval hydrology",
            "sources": ["USGS"],
            "status": "BLOCKED",
            "blocker_categories": ["BLOCKED_DATA_QUALITY", "GOVERNANCE_PENDING"],
            "candidate_artifact": False,
            "blockers": [
                "36 overlapping interval summaries are not a continuous series.",
                "No verified flood-event label or split assignment exists.",
            ],
        },
        {
            "task": "Native Model 1 symbolic observation processing",
            "sources": ["native Model 1"],
            "status": "BLOCKED",
            "blocker_categories": ["BLOCKED_TARGETS"],
            "candidate_artifact": False,
            "blockers": [
                "No native or protected evaluation records were opened in this public-source-only pass.",
                "Independent human evaluation and weak-imitation protocol remain pending.",
            ],
        },
        {
            "task": "Native Model 1 structured report generation",
            "sources": ["native Model 1"],
            "status": "BLOCKED",
            "blocker_categories": ["BLOCKED_TARGETS"],
            "candidate_artifact": False,
            "blockers": [
                "Delivery-selected native reports are not independent targets.",
                "Pilot and alert-journal data remain inaccessible and outside scope.",
            ],
        },
    ]
    return {
        "status": "NO_GO",
        "scope": "Model 1 only; ten public sources and two native task dispositions",
        "tasks": tasks,
        "readiness_counts": dict(sorted(Counter(task["status"] for task in tasks).items())),
        "candidate_manifests": {
            "technically_valid_candidate_partitions": 2,
            "datasets": ["ESC-50", "UCI"],
            "additional_preparation_only_artifacts": ["FLAME"],
            "training_ready": 0,
        },
        "approved_training_records": 0,
        "governance_approvals_granted": 0,
        "model_training_performed": False,
        "human_annotations_created": False,
        "source_audit_count": len(MODEL1_SOURCES),
        "mask_source_count": len(masks),
        "sensor_status": sensors,
    }


def _make_candidate_files(
    out: Path,
    source_audits: dict[str, Any],
    flame_rows: list[CandidateRow],
    esc_rows: list[CandidateRow],
    uci_rows: list[CandidateRow],
) -> dict[str, dict[str, Any]]:
    directory = out / "candidate_manifests"
    directory.mkdir()
    info: dict[str, dict[str, Any]] = {}

    definitions: list[tuple[str, str, str, list[CandidateRow], Counter[str], str]] = [
        (
            "flame-fire-classification-v1",
            "flame",
            "fire/no-fire classification",
            flame_rows,
            Counter(),
            "PREPARATION_ONLY_GROUPING_BLOCKED",
        ),
        (
            "esc50-official-folds-v1",
            "esc50",
            "environmental sound classification",
            esc_rows,
            Counter(),
            "TECHNICALLY_VALID_CANDIDATE",
        ),
        (
            "uci-co-next-hour-24h-v1",
            "uci-air-quality",
            "next-hour CO(GT) concentration; 24-hour lookback",
            uci_rows,
            Counter(),
            "TECHNICALLY_VALID_CANDIDATE_TEMPORAL_ONLY",
        ),
    ]
    registry = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "configs"
            / "datasets"
            / "registry.phase10i-v1.json"
        ).read_bytes()
    )
    versions = {str(entry["dataset_id"]): entry.get("version") for entry in registry["datasets"]}
    for filename, dataset_id, task, records, target_counts, integrity in definitions:
        records_file = f"{filename}.jsonl"
        records_sha = _write_jsonl(directory / records_file, records)
        source_name = {
            "flame": "FLAME",
            "esc50": "ESC-50",
            "uci-air-quality": "UCI",
        }[dataset_id]
        manifest = _candidate_manifest(
            dataset_id=dataset_id,
            version=versions.get(dataset_id),
            task=task,
            records_path=records_file,
            records_sha256=records_sha,
            records=records,
            source_index_sha256=source_audits[source_name]["index_sha256"],
            raw_inventory_sha256=source_audits[source_name]["source_inventory_sha256"],
            target_distribution=target_counts,
            partition_integrity=integrity,
        )
        manifest_path = directory / f"{filename}.json"
        _write_json(manifest_path, manifest.model_dump(mode="json"))
        info[dataset_id] = {
            "manifest": manifest_path.name,
            "manifest_sha256": digest(manifest_path),
            "records": records_file,
            "records_sha256": records_sha,
            "candidate_records": len(records),
            "training_approved": False,
        }
    return info


def run(root: Path, workers: int = 2) -> Path:
    run_started = time.perf_counter()
    root = root.resolve()
    if root.drive.upper() != "D:" or not 1 <= workers <= 2:
        raise ValueError("use D: storage and one or two CPU workers")
    destination = root / "manifests" / "phase10i-b1-c1-v1"
    if destination.exists():
        raise FileExistsError(destination)
    if shutil.disk_usage(root).free < 20 << 30:
        raise ValueError("retain at least 20 GiB of free space on D:")
    manifests = root / "manifests"
    release = manifests / "phase10h-v1" / "release.json"
    phase10i = manifests / "phase10i-a-raw-v1"
    raw_summary = json.loads((phase10i / "summary.json").read_bytes())
    raw_checksums = json.loads((phase10i / "checksums.json").read_bytes())
    if digest(phase10i / "summary.json") != raw_checksums["files"]["summary.json"]:
        raise ValueError("Phase 10I-A summary checksum mismatch")
    if digest(release) != raw_checksums["phase10h_release_sha256"]:
        raise ValueError("frozen Phase 10H release changed")
    registry_path = (
        Path(__file__).resolve().parents[2] / "configs" / "datasets" / "registry.phase10i-v1.json"
    )
    if raw_summary["source_count"] != 12 or not raw_summary["inventory_all_sources_match_phase10g"]:
        raise ValueError("Phase 10I-A raw coverage summary is incomplete")

    source_audits: dict[str, Any] = {}
    cross_source_hashes: dict[str, set[str]] = defaultdict(set)
    for name in MODEL1_SOURCES:
        raw_ledger = raw_summary["sources"][name]
        report, image_hashes = _verify_source(
            root,
            name,
            raw_ledger,
            raw_checksums["files"],
        )
        source_audits[name] = report
        for checksum in image_hashes:
            cross_source_hashes[checksum].add(name)
        print(
            f"verified {name}: {report['index_rows']} rows ({report['seconds']:.2f}s)", flush=True
        )

    cross_overlaps = [
        {"sha256": checksum, "sources": sorted(names)}
        for checksum, names in sorted(cross_source_hashes.items())
        if len(names) > 1
    ]
    if cross_overlaps:
        raise ValueError("unexpected exact image-hash overlap across Model 1 sources")

    coco_audits = {name: audit_coco(root, name) for name in ("HERIDAL", "SARD")}
    flame_audit, flame_overlay, flame_candidate = audit_flame(root)
    mask_audits: dict[str, Any] = {}
    mask_reviews: list[dict[str, Any]] = []
    for name in ("FloodNet", "RescueNet"):
        mask_audits[name], reviews = audit_masks(root, name, workers)
        mask_reviews.extend(reviews)
        print(f"audited {name} class-index masks: {mask_audits[name]['mask_count']}", flush=True)

    wisard_summary = source_audits["WiSARD"]
    wisard_folder = root / "manifests" / "phase10g-visual-v1" / "WiSARD"
    wisard_flags = list(_json_rows(wisard_folder / "flags.jsonl"))
    wisard_index = list(_json_rows(root / "processed" / "phase10g-v1" / "WiSARD" / "index.jsonl"))
    wisard_summary["missing_annotation_sidecars"] = sum(
        not bool(row.get("annotation")) for row in wisard_index
    )
    wisard_summary["paired_records"] = sum(bool(row.get("paired")) for row in wisard_index)
    wisard_summary["visual_flags"] = len(wisard_flags)
    wisard_summary["flagged_path_count"] = len({str(row["path"]) for row in wisard_flags})
    wisard_summary["display_representation"] = (
        "RGB / 8-bit display-coded; not calibrated temperature"
    )
    if wisard_summary["visual_flags"] != 1275 or wisard_summary["paired_records"] != 0:
        raise ValueError("WiSARD blocker counts changed from the audited source")

    flame_candidate_manifest = flame_audit
    flame_candidate_manifest["candidate_records"] = len(flame_candidate)

    esc_rows_in = list(_json_rows(root / "processed" / "phase10g-v1" / "ESC-50" / "index.jsonl"))
    esc_audit, esc_overlay, esc_candidate = build_esc50_candidate(esc_rows_in)

    uci_rows_in = list(_json_rows(root / "processed" / "phase10g-v1" / "UCI" / "index.jsonl"))
    uci_meta = json.loads(
        (root / "processed" / "phase10g-v1" / "UCI" / "summary.json").read_bytes()
    )
    uci_source = Path(uci_meta["configuration"]["source"])
    uci_relative = uci_source.name if uci_source.is_file() else "."
    uci_raw_sha = uci_meta["source_digests"][uci_source.name]
    uci_audit, uci_candidate = build_uci_windows(uci_rows_in, uci_relative, uci_raw_sha)
    uci_missing: Counter[str] = Counter()
    for row in uci_rows_in:
        for value in row["measurements"].values():
            if value[4]:
                uci_missing["missing_flags"] += 1
            if value[0] in {"-200", "-200.0"}:
                uci_missing["literal_minus_200"] += 1
            if value[0] == "-200,0":
                uci_missing["decimal_comma_minus_200"] += 1
    uci_audit["missing_value_reconciliation"] = {
        **dict(uci_missing),
        "resolved_total_missing_cells": uci_missing["missing_flags"],
        "explanation": "The earlier 16,244 count included only literal -200/-200.0. Another 457 values encode -200 as -200,0; all are flagged missing, giving 16,701.",
    }

    smoke_rows = list(_json_rows(root / "processed" / "phase10g-v1" / "Smoke" / "index.jsonl"))
    sensor_audits: dict[str, Any] = {
        "UCI": uci_audit,
        "Smoke": _audit_smoke(smoke_rows),
        "USGS": _audit_usgs(
            list(_json_rows(root / "processed" / "phase10g-v1" / "USGS" / "index.jsonl"))
        ),
    }

    mask_summary = mask_audits
    queue = build_review_queue(coco_audits, wisard_flags, mask_reviews)
    review_effort = sum(int(item["estimated_minutes"]) for item in queue)
    registry_data = json.loads(registry_path.read_bytes())
    governance = _governance_evidence(registry_data)
    for name in MODEL1_SOURCES:
        source = Path(
            json.loads((root / "processed" / "phase10g-v1" / name / "summary.json").read_bytes())[
                "configuration"
            ]["source"]
        )
        fingerprint, files, size = _source_inventory_fingerprint(source)
        if (
            fingerprint != source_audits[name]["source_inventory_sha256"]
            or files != source_audits[name]["raw_files"]
            or size != source_audits[name]["raw_bytes"]
        ):
            raise ValueError(f"{name}: raw inventory changed during candidate preparation")

    readiness = _model1_readiness(
        coco_audits,
        flame_candidate_manifest,
        mask_summary,
        wisard_summary,
        esc_audit,
        sensor_audits,
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    free_before = shutil.disk_usage(root).free
    with TemporaryDirectory(dir=destination.parent) as temp:
        out = Path(temp) / destination.name
        out.mkdir()
        overlay_dir = out / "exclusion_overlays"
        overlay_dir.mkdir()
        _write_jsonl(overlay_dir / "flame-near-test-training.jsonl", flame_overlay)
        _write_jsonl(overlay_dir / "esc50-cross-fold-recordings.jsonl", esc_overlay)
        _write_json(out / "source_audit.json", source_audits)
        _write_json(out / "coco_annotation_audit.json", coco_audits)
        _write_json(out / "mask_class_distribution.json", mask_summary)
        _write_json(
            out / "grouping_and_leakage_audit.json",
            {
                "FLAME": flame_audit,
                "ESC-50": esc_audit,
                "Smoke": sensor_audits["Smoke"],
                "UCI": uci_audit,
                "USGS": sensor_audits["USGS"],
                "cross_source_exact_image_hash_overlap_count": len(cross_overlaps),
                "known_group_policy": "Use only publisher-provided identifiers. Do not infer parent flight, site, event, video or recording IDs.",
            },
        )
        _write_json(out / "sensor_candidate_audit.json", sensor_audits)
        _write_json(out / "governance_evidence.json", governance)
        _write_jsonl(out / "human_review_queue.jsonl", queue)
        _write_json(out / "model1_candidate_readiness.json", readiness)
        candidates = _make_candidate_files(
            out,
            source_audits,
            flame_candidate,
            esc_candidate,
            uci_candidate,
        )
        _write_json(
            out / "input_bindings.json",
            {
                "frozen_phase10h_release_sha256": digest(release),
                "phase10i_a_raw_summary_sha256": digest(phase10i / "summary.json"),
                "phase10i_a_hash_ledger_checksum_sha256": digest(phase10i / "checksums.json"),
                "registry_sha256": digest(registry_path),
                "preparation_code_sha256": digest(Path(__file__)),
                "phase10g_visual_inputs": {
                    "FLAME/frame-hashes.jsonl": digest(
                        manifests / "phase10g-visual-v1" / "FLAME" / "frame-hashes.jsonl"
                    ),
                    "FLAME/summary.json": digest(
                        manifests / "phase10g-visual-v1" / "FLAME" / "summary.json"
                    ),
                    "FloodNet/summary.json": digest(
                        manifests / "phase10g-visual-v1" / "FloodNet" / "summary.json"
                    ),
                    "RescueNet/summary.json": digest(
                        manifests / "phase10g-visual-v1" / "RescueNet" / "summary.json"
                    ),
                    "WiSARD/flags.jsonl": digest(
                        manifests / "phase10g-visual-v1" / "WiSARD" / "flags.jsonl"
                    ),
                },
                "source_indexes": {
                    name: {
                        "index_sha256": source_audits[name]["index_sha256"],
                        "raw_inventory_sha256": source_audits[name]["source_inventory_sha256"],
                    }
                    for name in MODEL1_SOURCES
                },
                "source_raw_hashes_reused": True,
                "raw_content_rehashed_in_this_phase": False,
                "raw_data_modified": False,
            },
        )
        _write_json(
            out / "execution.json",
            {
                "generated_utc": datetime.now(UTC).isoformat(),
                "python": sys.version.split()[0],
                "cpu_workers": workers,
                "per_source_seconds": {
                    name: round(
                        source_audits[name]["seconds"] + float(mask_summary[name]["seconds"])
                        if name in mask_summary
                        else source_audits[name]["seconds"],
                        3,
                    )
                    for name in MODEL1_SOURCES
                },
                "per_source_seconds_scope": "inventory/hash-index verification, plus full class-index mask decode for FloodNet and RescueNet",
                "review_queue_records": len(queue),
                "estimated_reviewer_minutes": review_effort,
                "candidate_manifests": candidates,
                "training_approved": False,
                "approved_training_records": 0,
                "model_training_performed": False,
                "protected_evaluation_seeds_touched": [],
                "private_model2_pilot_or_alert_data_accessed": False,
                "raw_data_modified": False,
                "seconds": round(time.perf_counter() - run_started, 3),
                "d_drive_free_bytes_before_publication": free_before,
            },
        )
        file_checksums = {
            path.relative_to(out).as_posix(): digest(path)
            for path in sorted(out.rglob("*"))
            if path.is_file()
        }
        _write_json(out / "checksums.json", file_checksums)
        out.rename(destination)
    return destination


def _audit_smoke(rows_in: list[dict[str, Any]]) -> dict[str, Any]:
    sequences: dict[str, Any] = {}
    sequence_rows: Counter[str] = Counter()
    spans: dict[str, tuple[str, str]] = {}
    for row in rows_in:
        group = str(row["group"])
        sequence_rows[group] += 1
        state = sequences.setdefault(group, hashlib.sha256())
        state.update(
            json.dumps(
                {
                    key: value[0]
                    for key, value in row["measurements"].items()
                    if key != "Temperature[C]"
                },
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )
        start = str(row["timestamp"])
        end = str(row.get("period_end") or start)
        if group in spans:
            spans[group] = min(spans[group][0], start), max(spans[group][1], end)
        else:
            spans[group] = start, end
    fingerprints = {key: value.hexdigest() for key, value in sequences.items()}
    repeats: dict[str, list[str]] = defaultdict(list)
    for group, fingerprint in fingerprints.items():
        repeats[fingerprint].append(group)
    compressed_rows = [(fingerprints[group], start, end) for group, (start, end) in spans.items()]
    assignment = chronological(compressed_rows)
    return {
        "rows": len(rows_in),
        "counter_runs": len(sequences),
        "source_run_row_counts": dict(sorted(sequence_rows.items())),
        "identical_signature_run_groups": [
            sorted(groups) for groups in repeats.values() if len(groups) > 1
        ],
        "distinct_sensor_signatures": len(set(fingerprints.values())),
        "chronological_group_assignments": assignment,
        "draft_row_counts": {
            split: sum(
                sequence_rows[group]
                for fingerprint, groups in repeats.items()
                if assignment.get(fingerprint, "unassigned") == split
                for group in groups
            )
            for split in ("train", "validation", "test", "unassigned")
        },
        "authoritative_session_ids_available": False,
        "candidate_split_emitted": False,
    }


def _audit_usgs(rows_in: list[dict[str, Any]]) -> dict[str, Any]:
    intervals: list[tuple[datetime, datetime, str]] = []
    for row in rows_in:
        start = datetime.fromisoformat(str(row["timestamp"]))
        stop = datetime.fromisoformat(str(row.get("period_end") or row["timestamp"]))
        if stop < start:
            raise ValueError("USGS interval ends before its start")
        intervals.append((start, stop, str(row.get("group"))))
    overlaps = 0
    for index, (start, stop, station) in enumerate(intervals):
        for other_start, other_stop, other_station in intervals[index + 1 :]:
            if station == other_station and start <= other_stop and other_start <= stop:
                overlaps += 1
    assignments = chronological(
        [(station, start.isoformat(), stop.isoformat()) for start, stop, station in intervals]
    )
    return {
        "rows": len(rows_in),
        "station_count": len({station for _, _, station in intervals}),
        "overlapping_interval_pairs": overlaps,
        "chronological_group_assignments": assignments,
        "measurement_type": "interval summaries",
        "continuous_series_eligible": False,
        "flood_event_label_verified": False,
        "candidate_split_emitted": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    print(run(args.root, args.workers))


if __name__ == "__main__":
    main()
