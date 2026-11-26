import json
from pathlib import Path

import pytest

from evaluation.data.contracts import Manifest, Registry
from evaluation.data.training_partition import approved_training

ROOT = Path(__file__).resolve().parents[2]


def test_phase10i_registry_is_additive_and_unapproved() -> None:
    original = Registry.model_validate_json(
        (ROOT / "configs/datasets/registry.json").read_bytes()
    )
    reconciled = Registry.model_validate_json(
        (ROOT / "configs/datasets/registry.phase10i-v1.json").read_bytes()
    )
    original_ids = {dataset.dataset_id for dataset in original.datasets}
    reconciled_ids = {dataset.dataset_id for dataset in reconciled.datasets}
    assert original_ids <= reconciled_ids
    assert reconciled_ids - original_ids == {"sard", "flame", "wisard", "humaid", "crisismmd"}

    indexed = [dataset for dataset in reconciled.datasets if dataset.download_status == "available"]
    assert len(indexed) == 12
    assert all(
        dataset.licence_status == "unverified"
        and dataset.privacy_status == "pending"
        and dataset.verification == "unverified"
        for dataset in indexed
    )


def test_phase10i_b_inventory_covers_blockers_without_starting_work() -> None:
    inventory = json.loads((ROOT / "configs/datasets/phase10i_b_tasks.json").read_bytes())
    task_ids = {task["id"] for task in inventory["tasks"]}
    assert task_ids == {
        "heridal-sard-parent-groups-and-empty-annotations",
        "flame-near-test-training-frames",
        "flame-unpaired-segmentation-masks",
        "floodnet-rescuenet-site-event-groups",
        "wisard-flagged-records-and-pairing",
        "esc50-cross-fold-recordings",
        "humaid-cross-partition-text-keys",
        "crisismmd-repeated-events-and-media",
        "smoke-usgs-missing-split-assignments",
        "sensor-horizon-units-and-overlapping-windows",
    }
    assert inventory["status"] == "NOT_STARTED"
    assert all(
        task["status"] == "NOT_STARTED"
        and task["training_approved"] is False
        and task["large_scale_split_reconstruction_allowed"] is False
        for task in inventory["tasks"]
    )


def test_training_loader_rejects_unregistered_release_version(tmp_path: Path) -> None:
    registry = Registry.model_validate(
        {
            "schema_version": "1.0",
            "datasets": [
                {
                    "dataset_id": "fixture",
                    "name": "Fixture",
                    "origin": "real",
                    "version": "1",
                    "licence": "terms",
                    "licence_status": "verified",
                    "privacy_status": "approved",
                    "verification": "verified",
                    "privacy_considerations": "test fixture",
                    "modalities": ["image"],
                    "annotation_types": ["boxes"],
                    "tasks": ["test"],
                    "limitations": "test fixture",
                }
            ],
        }
    )
    manifest = Manifest.model_validate(
        {
            "schema_version": "1.0",
            "manifest_version": "1",
            "dataset_id": "fixture",
            "dataset_version": "2",
            "origin": "real",
            "role": "operational",
            "samples": [
                {
                    "sample_id": "sample-1",
                    "source_ref": "flight-1",
                    "source_id": "camera-1",
                    "licence_ref": "terms",
                    "modality": "image",
                    "representation": "physical",
                    "split": "train",
                    "sequence_id": "flight-1",
                    "asset": {
                        "path": "raw/image.jpg",
                        "sha256": "0" * 64,
                        "availability": "available",
                    },
                }
            ],
        }
    )
    with pytest.raises(ValueError, match="unknown dataset version"):
        next(approved_training(registry, (manifest,), tmp_path))
