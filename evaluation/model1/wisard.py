"""WiSARD metadata readiness and separately authorized local training."""

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch

from evaluation.data.contracts import Manifest, Registry
from evaluation.data.model2 import digest
from evaluation.data.release_authorization import (
    AuthorizationBundle,
    manifest_sha256,
    require_training_authorization,
)
from evaluation.model1.active_scope import require_trainable_task
from evaluation.model1.data import (
    AuthorizedTaskDataset,
    DatasetSplit,
    TaskDataConfig,
    TaskValidationSession,
    build_task_dataloader,
)
from evaluation.model1.detection_cache import prepare_detection_cache
from evaluation.model1.models import ModelConfig, build_model
from evaluation.model1.prepare_wisard import ROOT
from evaluation.model1.training import (
    DetectionTask,
    TrainingConfig,
    authorized_training_context,
    fit,
    seed_everything,
)


def run(release: Path, root: Path, *, execute: bool = False,
        resume: Path | None = None, resume_sha256: str | None = None) -> None:
    started = time.perf_counter()
    print("[initialization] metadata authorization", flush=True)
    registry = Registry.model_validate_json((release / "registry.json").read_bytes())
    inputs = Manifest.model_validate_json((release / "operational.json").read_bytes())
    targets = Manifest.model_validate_json((release / "targets.json").read_bytes())
    bundle = AuthorizationBundle.model_validate_json((release / "authorization_bundle.json").read_bytes())
    candidate = json.loads((release / "candidate.json").read_bytes())
    task = candidate["task"]
    if execute or resume is not None:
        require_trainable_task(task)
    auth = require_training_authorization(registry, inputs, task_id=task,
        candidate_manifest_paths={"wisard": release / "candidate.json"},
        authorization_records=bundle.records, dataset_root=root, training_targets_manifest=targets)
    require_training_authorization(registry, inputs, task_id=task,
        candidate_manifest_paths={"wisard": release / "candidate.json"},
        authorization_records=bundle.records, dataset_root=root, training_targets_manifest=targets,
        required_scope="local_evaluation")
    print(f"[authorization] release verified elapsed_s={time.perf_counter() - started:.2f}", flush=True)
    if not execute:
        print("[completion] metadata only; no training started", flush=True)
        return
    start = json.loads((release / "training_start.approved.json").read_bytes())
    expected: dict[str, Any] = {"decision": "APPROVE_TRAINING_START",
        "owner_identity": auth.authorizing_owner_identity, "authorization_id": auth.authorization_id,
        "input_sha256": manifest_sha256(inputs), "target_sha256": manifest_sha256(targets),
        "candidate_sha256": digest(release / "candidate.json"),
        "config_sha256": digest(release / "training_config.json")}
    if any(start.get(k) != v for k, v in expected.items()):
        raise ValueError("missing or mismatched separate training-start approval")
    when = datetime.fromisoformat(start["approved_at"])
    if when.tzinfo is None or when > datetime.now(UTC):
        raise ValueError("invalid training-start approval timestamp")
    config = TrainingConfig.model_validate_json((release / "training_config.json").read_bytes())
    if config.workers != 0:
        raise ValueError("verified epoch resumption requires zero workers")
    seed_everything(config.seed)
    session = TaskValidationSession()
    data_config = TaskDataConfig("object_detection", image_size=config.image_size,
        batch_size=config.batch_size, development_only=True)
    datasets = []
    splits: tuple[DatasetSplit, ...] = ("train", "validation")
    for split in splits:
        tick = time.perf_counter()
        print(f"[initialization] integrity and dataset split={split}", flush=True)
        data = AuthorizedTaskDataset(registry, inputs, targets, root, data_config, task_id=task,
            candidate_manifest_path=release / "candidate.json", authorization_records=bundle.records,
            split=split, validation_session=session)
        prepare_detection_cache(data, root / "cache/phase11g8")
        datasets.append(data)
        print(f"[initialization] split={split} seconds={time.perf_counter() - tick:.2f}", flush=True)
    mc = ModelConfig(task="object_detection", num_classes=2, image_size=config.image_size)
    model = build_model(mc)
    loaders = [build_task_dataloader(d, seed=config.seed, device=torch.device(config.device))
               for d in datasets]
    print(f"[initialization] complete seconds={time.perf_counter() - started:.2f}", flush=True)
    fit(model, loaders[0], loaders[1], DetectionTask(), config=config,
        context=authorized_training_context(datasets[0]), model_config=mc.model_dump(mode="json"),
        resume_path=resume, resume_sha256=resume_sha256)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--resume-sha256")
    args = parser.parse_args()
    if (args.resume is None) != (args.resume_sha256 is None):
        parser.error("resume requires both path and trusted checksum")
    run(args.release, args.root, execute=args.execute,
        resume=args.resume, resume_sha256=args.resume_sha256)


if __name__ == "__main__":
    main()
