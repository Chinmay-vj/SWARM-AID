"""Prepare WiSARD detection releases from existing audited metadata, without image decoding."""

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Literal

import numpy as np

from evaluation.data.contracts import Annotation, Asset, Manifest, Registry, Sample
from evaluation.data.model1_prep import CandidateManifest, CandidateRow, _write_json, _write_jsonl
from evaluation.data.model2 import digest
from evaluation.data.release_authorization import AuthorizationBundle, manifest_sha256
from evaluation.data.validation import validate
from evaluation.model1.training import TrainingConfig

ROOT = Path("D:/SWARM-AID-DATA")
EXPECTED = {"visual": {"train": 9839, "validation": 3311, "test": 3424},
            "thermal": {"train": 8218, "validation": 2514, "test": 2563}}
LIMITATIONS = (
    "Positive human annotations only; false-alarm performance is not adequately established. "
    "Location groups are provisional, not verified flight identities. Thermal images are display "
    "imagery, not calibrated temperature measurements. Human presence does not establish distress. "
    "Local non-commercial academic research only; attribution required; no cloud upload, raw "
    "redistribution or personal identification. Publisher imagery licence scope remains ambiguous; "
    "no individual permission or definitive legal clearance is claimed."
)


def yolo_annotation(payload: bytes, dimensions: tuple[int, int], asset: Asset) -> Annotation:
    rows = [line.split() for line in payload.decode("utf8").splitlines() if line.strip()]
    if not rows or any(len(row) != 5 for row in rows):
        raise ValueError("expected nonempty five-column YOLO annotations")
    values = np.asarray(rows, dtype=np.float64)
    c, cx, cy, w, h = values.T
    if (min(dimensions) <= 0 or not np.isfinite(values).all() or np.any(c != 0)
            or np.any(w <= 0) or np.any(h <= 0) or np.any(w > 1) or np.any(h > 1)
            or np.any(cx < w / 2) or np.any(cx > 1 - w / 2)
            or np.any(cy < h / 2) or np.any(cy > 1 - h / 2)):
        raise ValueError("invalid publisher class or normalized YOLO box")
    boxes = np.column_stack((cx - w / 2, cy - h / 2, w, h))
    boxes *= np.asarray([*dimensions, *dimensions])
    # Valid normalized edge boxes can exceed the pixel edge by one rounding ULP.
    boxes[:, 2:] = np.minimum(boxes[:, 2:], np.asarray(dimensions) - boxes[:, :2])
    overflow = boxes[:, :2] + boxes[:, 2:] > np.asarray(dimensions)
    boxes[:, 2:] = np.where(overflow, np.nextafter(boxes[:, 2:], 0), boxes[:, 2:])
    return Annotation(format="yolo", asset=asset, labels=("human",),
                      label_schema_version="wisard-human-boxes-1", label_source="publisher-sidecar",
                      review_status="source", boxes=tuple(tuple(row) for row in boxes.tolist()),
                      box_labels=("human",) * len(boxes))


def read_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def prepare(root: Path, output: Path) -> None:
    started = time.perf_counter()
    evidence = root / "runs/phase11g8"
    decision = json.loads((evidence / "research_use_decision.json").read_bytes())
    if decision.get("training_pipeline_preparation_approved") is not True:
        raise ValueError("preparation approval missing")
    print("[initialization] loading audited metadata; images will not be decoded", flush=True)
    cleaned = {r["path"]: r for r in read_rows(evidence / "cleaned_candidates.jsonl")}
    index_path = root / "processed/phase10g-v1/WiSARD/index.jsonl"
    inventory_path = root / "manifests/phase10i-a-raw-v1/WiSARD.jsonl"
    index = {r["path"]: r for r in read_rows(index_path) if r["path"] in cleaned}
    ledger = {r["path"]: r for r in read_rows(inventory_path)}
    partitions = []
    locations: dict[str, str] = {}
    for split in ("train", "validation", "test"):
        for row in read_rows(evidence / f"provisional_partitions/{split}.jsonl"):
            candidate = cleaned.get(row["path"])
            if (candidate is None or row["split"] != split
                    or any(row[k] != candidate[k] for k in candidate)):
                raise ValueError("partition differs from cleaned candidate")
            if locations.setdefault(row["location_group"], split) != split:
                raise ValueError("location crosses partitions")
            partitions.append(row)
    if len(partitions) != len(cleaned) or len({r["path"] for r in partitions}) != len(cleaned):
        raise ValueError("partition coverage mismatch")
    registry = Registry.model_validate_json(Path("configs/datasets/registry.phase10j-v1.json").read_bytes())
    base = next(d for d in registry.datasets if d.dataset_id == "wisard")
    provenance_paths = [evidence / n for n in (
        "cleaned_candidates.jsonl", "annotation_reconciliation.json", "publisher_evidence.json",
        "project_policy_approval.json", "research_use_decision.json", "synthetic_gpu_benchmark.json")]
    provenance_paths += [evidence / f"provisional_partitions/{s}.jsonl"
                         for s in ("train", "validation", "test")]
    provenance = {str(p.relative_to(root)): digest(p) for p in provenance_paths}
    index_hash, ledger_hash = digest(index_path), digest(inventory_path)
    output.mkdir(parents=True, exist_ok=False)
    for modality in ("visual", "thermal"):
        selected = [r for r in partitions if r["modality"] == modality]
        counts = Counter(r["split"] for r in selected)
        if dict(counts) != EXPECTED[modality]:
            raise ValueError("provisional partition counts differ")
        destination = output / modality
        destination.mkdir()
        task = f"wisard-{modality}-human-detection"
        version = f"wisard-location-{modality}-v1"
        entry = base.model_copy(update={"version": version, "tasks": (task,),
            "licence": "publisher-imagery-scope-ambiguous", "sample_count": len(selected),
            "label_definitions": {"human": "Publisher class 0; model foreground 1"},
            "limitations": LIMITATIONS})
        reg = Registry(schema_version="1.0", datasets=(entry,))
        inputs, targets, candidates = [], [], []
        for i, row in enumerate(selected):
            info = index[row["path"]]
            if info["sha256"] != row["sha256"] or info.get("orientation", 1) != 1:
                raise ValueError("source digest or orientation requires review")
            reference = "raw/multimodal/WiSARDv1/" + row["path"]
            annotation_ref = str(Path(reference).with_suffix(".txt")).replace("\\", "/")
            label_hash = ledger[str(Path(row["path"]).with_suffix(".txt")).replace("\\", "/")]["sha256"]
            payload = (root / annotation_ref).read_bytes()
            if hashlib.sha256(payload).hexdigest() != label_hash:
                raise ValueError("annotation changed since recorded inventory")
            ann = yolo_annotation(payload, tuple(info["size"]),
                                  Asset(path=annotation_ref, sha256=label_hash, availability="available"))
            sid = hashlib.sha256(row["path"].encode()).hexdigest()[:24]
            sample = Sample(sample_id=sid, source_ref=row["path"], source_id=row["candidate_group"],
                licence_ref=entry.licence or "ambiguous", modality="image" if modality == "visual" else "thermal",
                representation="physical", split=row["split"], location_group=row["location_group"],
                asset=Asset(path=reference, sha256=row["sha256"], availability="available"),
                dimensions=tuple(info["size"]))
            inputs.append(sample)
            targets.append(sample.model_copy(update={"annotation": ann}))
            candidates.append(CandidateRow(record_id=sid, partition=row["split"], source_path=reference,
                source_sha256=row["sha256"], group_ref=row["location_group"], target=task,
                target_label="human", metadata={"location_identity_verified": False}))
            if (i + 1) % 1000 == 0 or i + 1 == len(selected):
                elapsed = time.perf_counter() - started
                print(f"[prepare] modality={modality} samples={i + 1}/{len(selected)} "
                      f"elapsed_s={elapsed:.2f}", flush=True)
        manifests = []
        for role, samples in (("operational", inputs), ("training_targets", targets)):
            typed_role: Literal["operational", "training_targets"] = (
                "operational" if role == "operational" else "training_targets")
            manifests.append(Manifest(schema_version="1.1", manifest_version=version, dataset_id="wisard",
                dataset_version=version, origin="real", role=typed_role, samples=tuple(samples)))
        validate(reg, tuple(manifests), root, verify_files=False)
        _write_json(destination / "registry.json", reg.model_dump(mode="json"))
        for name, manifest in zip(("operational", "targets"), manifests, strict=True):
            _write_json(destination / f"{name}.json", manifest.model_dump(mode="json"))
        records_hash = _write_jsonl(destination / "candidate_records.jsonl", candidates)
        candidate_manifest = CandidateManifest(schema_version="phase10i-candidate-1.0",
            artifact_kind="candidate_only_not_approved_training_release", dataset_id="wisard",
            dataset_version=version, task=task, records_file="candidate_records.jsonl",
            records_sha256=records_hash, candidate_records=len(selected), partition_counts=dict(counts),
            target_distribution={"human": counts["train"]}, partition_integrity="PROVISIONAL_LOCATION_GROUPS",
            source_index_sha256=index_hash, raw_inventory_sha256=ledger_hash)
        _write_json(destination / "candidate.json", candidate_manifest.model_dump(mode="json"))
        config = TrainingConfig(device="cuda:0", epochs=30, early_stopping_patience=7,
            batch_size=32, image_size=512, workers=0, mixed_precision=True, amp_dtype="bfloat16",
            checkpoint_every=1, progress=True, checkpoint_root=root / f"checkpoints/phase11g8/{modality}",
            profile_output_root=root / f"runs/phase11g8/training/{modality}")
        _write_json(destination / "training_config.json", config.model_dump(mode="json"))
        _write_json(destination / "authorization_bundle.json", AuthorizationBundle(
            schema_version="phase10i-authorization-bundle-1.1", records=()).model_dump(mode="json"))
        _write_json(destination / "provenance.json", {"status": "PREPARATION_ONLY_NO_TRAINING",
            "evidence_sha256": provenance, "limitations": LIMITATIONS, "counts": dict(counts),
            "input_sha256": manifest_sha256(manifests[0]), "target_sha256": manifest_sha256(manifests[1]),
            "candidate_sha256": digest(destination / "candidate.json"),
            "config_sha256": digest(destination / "training_config.json"),
            "class_mapping": {"publisher_0": "human", "model_0": "background", "model_1": "human"},
            "images_decoded": 0, "raw_image_hashes_reused": True,
            "required": ["genuine bound release authorization", "separate owner training-start approval"]})
    print(f"[completion] preparation_only elapsed_s={time.perf_counter() - started:.2f}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / "runs/phase11g8/prepared-v1")
    args = parser.parse_args()
    prepare(args.root, args.output)


if __name__ == "__main__":
    main()
