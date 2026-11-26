"""Validate the private review indexes, measure CPU previews and freeze split overlays."""

import argparse
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from evaluation.data.contracts import Registry
from evaluation.data.crisismmd import snapshot_integrity
from evaluation.data.final_native import checked
from evaluation.data.final_raw import inventory
from evaluation.data.model2 import digest, write_json
from evaluation.data.phase10g import SOURCES
from evaluation.data.phase10g_quality import rows
from evaluation.data.review_loaders import native_batches, public_batches


def describe(example: dict[str, Any]) -> dict[str, Any]:
    shapes: dict[str, Any] = {}
    for key, value in example.items():
        if hasattr(value, "mode") and hasattr(value, "size"):
            shapes[key] = [*value.size, value.mode]
        elif isinstance(value, dict):
            shapes[key] = {
                k: list(v.shape) if hasattr(v, "shape") else type(v).__name__
                for k, v in value.items()
            }
        elif isinstance(value, list):
            shapes[key] = len(value)
        else:
            shapes[key] = type(value).__name__
    return shapes


def audit(root: Path, out: Path) -> dict[str, Any]:
    manifests = root / "manifests"
    qpath = manifests / "phase10g-v1/quality.json"
    checked(qpath, "38b7e87d60757e3ad4b709b236f6fb49e183c9c7c6a0568a25a618123a024b95")
    quality = json.loads(qpath.read_bytes())
    registry_file = Path("configs/datasets/registry.json")
    checked(registry_file, quality["source_registry_sha256"])
    registry = Registry.model_validate_json(registry_file.read_bytes())
    lookup = {r.dataset_id: r for r in registry.datasets}
    views = qpath.parent / "crisis-task-views.jsonl"
    checked(views, "3791b413ce189ddb922d0a6da00aaf34ec25095207ce1f71d65cd93a344de9be")
    crisis = manifests / "phase10g-crisis-decode-v1/summary.json"
    checked(crisis, "afea52e3120f1c70de5109159fbda6617f25393f5cc8d4fb87f7883a066f712b")
    checked(crisis.parent / "flags.jsonl", json.loads(crisis.read_bytes())["flags_sha256"])
    datasets = {}
    for name in SOURCES:
        folder = root / "processed/phase10g-v1" / name
        info = quality["datasets"][name]
        checked(folder / "summary.json", info["metadata_sha256"])
        meta = json.loads((folder / "summary.json").read_bytes())
        for filename, sha in meta["outputs"].items():
            checked(folder / filename, sha)
        raw = Path(meta["configuration"]["source"])
        paths = {p if p != "." else raw.name for p, _ in inventory(raw)}
        ids = set()
        seq: Counter[str] = Counter()
        split_hash = hashlib.sha256()
        groups: dict[str, set[str]] = defaultdict(set)
        visuals = manifests / "phase10g-visual-v1" / name
        visual: dict[str, Any] = {}
        if visuals.exists():
            visual = json.loads((visuals / "summary.json").read_bytes())
            checked(folder / "index.jsonl", visual["index_sha256"])
            checked(visuals / "flags.jsonl", visual["flags_sha256"])
            checked(visuals / "frame-hashes.jsonl", visual["frame_hashes_sha256"])
        for row in rows(folder / "index.jsonl"):
            for key in ("path", "mask", "source"):
                if key in row and row[key] not in paths:
                    raise ValueError(f"{name} unresolved {key}")
            identity = (row["source"], row["line"]) if "line" in row else (row["path"],)
            if identity in ids:
                raise ValueError(f"{name} repeated source row")
            ids.add(identity)
            split = str(row.get("split") or row.get("fold") or "unassigned")
            split_hash.update(json.dumps([identity, split]).encode() + b"\n")
            if name in {"HumAID", "ESC-50"}:
                group = str(row["text_key"] if name == "HumAID" else row["group"])
                groups[group].add(split)
            if "sequence" in row:
                seq[row["sequence"]] += 1
        if len(ids) != meta["counts"]["valid"]:
            raise ValueError("index coverage mismatch")
        excluded = sorted(k for k, v in groups.items() if len(v) > 1)
        rid = {
            "ESC-50": "esc50",
            "Smoke": "smoke-detection-iot",
            "UCI": "uci-air-quality",
            "USGS": "usgs-water-data",
        }.get(name, name.lower())
        entry = lookup.get(rid)
        batch = next(public_batches(folder, 2))
        single = next(public_batches(folder, 1))
        datasets[name] = {
            "source": str(raw),
            "schema": meta["schema_version"],
            "version": entry.version if entry else None,
            "source_digests": meta["source_digests"],
            "configuration": meta["configuration"],
            "outputs": meta["outputs"],
            "summary_sha256": info["metadata_sha256"],
            "review_rows": len(ids),
            "raw_files": meta["raw_files"],
            "raw_bytes": meta["raw_bytes"],
            "review_index_bytes": info["output_bytes"],
            "visual_flags": visual.get("counts", {}).get("invalid", 0),
            "visual_summary_sha256": digest(visuals / "summary.json") if visual else None,
            "mask_pixels": visual.get("mask_pixels", {}),
            "sidecar_classes": visual.get("sidecar_classes", {}),
            "png_depth": visual.get("png_bit_depth", {}),
            "sequence_counts": seq,
            "counts": meta["counts"],
            "distributions": meta["distributions"],
            "source_registry": entry.model_dump(mode="json") if entry else None,
            "single": len(single),
            "batch": len(batch),
            "preview": describe(batch[0]),
            "split_sha256": split_hash.hexdigest(),
            "research_excluded_groups": excluded,
            "source_groups": len(groups),
            "draft_row_counts": info["draft_row_counts"],
            "official_split_policy": "retain; exclude listed groups from research comparisons",
            "readiness": "BLOCKED",
            "approved_training_records": 0,
        }
    snapshot = snapshot_integrity(Path(datasets["CrisisMMD"]["source"]), {})
    if snapshot["status"] != "matched":
        raise ValueError("snapshot identity mismatch")
    native = {}
    for kind in ("model1", "model2"):
        batch = next(native_batches(root / "processed/model2/field-v1-flood_field", kind, 2))
        native[kind] = [describe(row) for row in batch]
    return {
        "public": datasets,
        "native_preview": native,
        "crisis_snapshot": snapshot,
        "quality_sha256": digest(qpath),
        "registry_sha256": digest(registry_file),
        "crisis_task_labels": quality["crisis_benchmark"]["labels"],
    }


def main(root: Path) -> None:
    dest = root / "manifests/phase10h-public-v1"
    if root.resolve().drive.upper() != "D:" or shutil.disk_usage(root).free < 20480 << 20:
        raise ValueError("D-drive release with 20 GiB reserve required")
    if dest.exists():
        raise FileExistsError(dest)
    with TemporaryDirectory(dir=dest.parent) as tmp:
        out = Path(tmp) / dest.name
        out.mkdir()
        write_json(out / "public.json", audit(root, out))
        out.rename(dest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    main(parser.parse_args().root)
