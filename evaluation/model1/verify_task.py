"""Verify a task-bound Model 1 release without starting training."""

import argparse
import json
from pathlib import Path
from typing import Any

from evaluation.data.contracts import Manifest, Registry
from evaluation.data.release_authorization import (
    AuthorizationBundle,
    require_training_authorization,
)
from evaluation.data.validation import validate
from evaluation.model1.data import require_active_source


def verify(
    registry_path: Path,
    input_manifest_path: Path,
    target_manifest_path: Path,
    candidate_manifest_path: Path,
    authorization_bundle_path: Path,
    dataset_root: Path,
    task_id: str,
) -> dict[str, Any]:
    root = dataset_root.resolve()
    for path in (input_manifest_path, target_manifest_path, candidate_manifest_path):
        if not path.resolve().is_relative_to(root):
            raise ValueError("release manifests and candidates must be under the dataset root")
    registry = Registry.model_validate_json(registry_path.read_bytes())
    input_manifest = Manifest.model_validate_json(input_manifest_path.read_bytes())
    target_manifest = Manifest.model_validate_json(target_manifest_path.read_bytes())
    bundle = AuthorizationBundle.model_validate_json(authorization_bundle_path.read_bytes())
    require_active_source(input_manifest.dataset_id)
    authorization = require_training_authorization(
        registry,
        input_manifest,
        task_id=task_id,
        candidate_manifest_paths={input_manifest.dataset_id: candidate_manifest_path},
        authorization_records=bundle.records,
        dataset_root=root,
        training_targets_manifest=target_manifest,
    )
    counts = validate(registry, (input_manifest, target_manifest), root, verify_files=True)
    return {
        "status": "AUTHORIZED_FOR_LOCAL_TRAINING",
        "task_id": task_id,
        "dataset_id": input_manifest.dataset_id,
        "dataset_version": input_manifest.dataset_version,
        "authorization_id": authorization.authorization_id,
        "input_manifest_sha256": authorization.training_manifest_sha256,
        "target_manifest_sha256": authorization.training_targets_manifest_sha256,
        "verified_partition_counts": counts,
        "training_started": False,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--input-manifest", type=Path, required=True)
    parser.add_argument("--target-manifest", type=Path, required=True)
    parser.add_argument("--candidate-manifest", type=Path, required=True)
    parser.add_argument("--authorization-bundle", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    args = parser.parse_args(argv)
    result = verify(
        args.registry,
        args.input_manifest,
        args.target_manifest,
        args.candidate_manifest,
        args.authorization_bundle,
        args.dataset_root,
        args.task_id,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
