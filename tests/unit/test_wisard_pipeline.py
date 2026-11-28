"""WiSARD preparation and one synthetic detection/cache/resume integration test."""

import copy
import hashlib
import importlib
import importlib.util
import io
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO, cast

import pytest

if importlib.util.find_spec("torch") is None or importlib.util.find_spec("torchvision") is None:
    pytest.skip("optional ML dependencies unavailable", allow_module_level=True)

import torch
from torch.utils.data import DataLoader

from evaluation.data.contracts import Asset, Manifest, Registry
from evaluation.data.release_authorization import AuthorizationRecord, manifest_sha256
from evaluation.model1.data import AuthorizedTaskDataset, TaskDataConfig
from evaluation.model1.detection_cache import prepare_detection_cache
from evaluation.model1.models import ModelConfig, build_model
from evaluation.model1.prepare_wisard import yolo_annotation
from evaluation.model1.training import (
    DetectionTask,
    SyntheticTaskDataset,
    TrainingConfig,
    fit,
    seed_everything,
    synthetic_training_context,
)

_authorized_release = cast(
    Callable[[Path], tuple[Registry, Manifest, Manifest, Path, AuthorizationRecord]],
    importlib.import_module("tests.unit.test_phase11_model1")._authorized_release,
)


class LiveCapture(io.TextIOBase):
    def __init__(self, terminal: TextIO) -> None:
        self.terminal = terminal
        self.buffered = io.StringIO()
        self.flushes = 0

    def write(self, value: str) -> int:
        self.terminal.write(value)
        return self.buffered.write(value)

    def flush(self) -> None:
        self.flushes += 1
        self.terminal.flush()


def collate(batch: list[tuple[Any, Any]]) -> tuple[list[Any], list[Any]]:
    return [item[0] for item in batch], [item[1] for item in batch]


@pytest.mark.parametrize("payload", [b"1 .5 .5 .2 .2", b"0 nan .5 .2 .2", b"0 .1 .5 .4 .2", b""])
def test_invalid_yolo(payload: bytes) -> None:
    with pytest.raises(ValueError):
        yolo_annotation(payload, (100, 80), Asset(
            path="labels.txt", sha256="a" * 64, availability="available"))


def test_wisard_synthetic_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    capture = LiveCapture(sys.stdout)
    monkeypatch.setattr(sys, "stdout", capture)
    torch.set_num_threads(2)
    seed_everything(2025)
    registry, inputs, targets, candidate, auth = _authorized_release(tmp_path)
    payload = b"0 0.5 0.5 0.5 0.5\n"
    label_path = tmp_path / "data/labels/human.txt"
    label_path.write_bytes(payload)
    annotation = yolo_annotation(payload, (32, 32), Asset(path="labels/human.txt",
        sha256=hashlib.sha256(payload).hexdigest(), availability="available"))
    assert annotation.boxes == ((8.0, 8.0, 16.0, 16.0),)
    edge = yolo_annotation(b"0 .5 .5 1 1", (3840, 2160), annotation.asset)
    assert edge.boxes == ((0., 0., 3840., 2160.),)
    entry = registry.datasets[0].model_copy(update={"label_definitions": {"human": "synthetic"}})
    registry = registry.model_copy(update={"datasets": (entry,)})
    targets = targets.model_copy(update={"samples": (
        targets.samples[0].model_copy(update={"annotation": annotation}),)})
    auth = auth.model_copy(update={"training_targets_manifest_sha256": manifest_sha256(targets)})
    config_data = TaskDataConfig("object_detection", image_size=64, batch_size=2, development_only=True)
    with pytest.raises(ValueError):
        AuthorizedTaskDataset(registry, inputs, targets, tmp_path / "data", config_data,
            task_id=auth.task_id, candidate_manifest_path=candidate, authorization_records=())
    data = AuthorizedTaskDataset(registry, inputs, targets, tmp_path / "data", config_data,
        task_id=auth.task_id, candidate_manifest_path=candidate, authorization_records=(auth,))
    thermal_registry = registry.model_copy(update={"datasets": (
        entry.model_copy(update={"modalities": ("thermal",)}),)})
    thermal_inputs = inputs.model_copy(update={"samples": (
        inputs.samples[0].model_copy(update={"modality": "thermal"}),)})
    thermal_targets = targets.model_copy(update={"samples": (
        targets.samples[0].model_copy(update={"modality": "thermal"}),)})
    thermal_auth = auth.model_copy(update={
        "training_manifest_sha256": manifest_sha256(thermal_inputs),
        "training_targets_manifest_sha256": manifest_sha256(thermal_targets)})
    thermal = AuthorizedTaskDataset(thermal_registry, thermal_inputs, thermal_targets,
        tmp_path / "data", config_data, task_id=auth.task_id,
        candidate_manifest_path=candidate, authorization_records=(thermal_auth,))
    assert thermal[0][0].shape == (3, 64, 64)  # Display imagery, not temperatures.
    raw_x, raw_y = data[0]
    assert raw_y["labels"].tolist() == [1]
    assert raw_y["boxes"].tolist() == [[16., 16., 48., 48.]]
    assert not prepare_detection_cache(data, tmp_path / "cache")["cache_hit"]
    assert prepare_detection_cache(data, tmp_path / "cache")["cache_hit"]
    x, y = data[0]
    assert torch.equal(x, raw_x) and torch.equal(y["boxes"], raw_y["boxes"])
    data.split = "test"
    with pytest.raises(ValueError, match="development"):
        prepare_detection_cache(data, tmp_path / "cache")
    data.split = "train"
    fixture = SyntheticTaskDataset(((x, y), (x.clone(), copy.deepcopy(y))),
        fixture_id="wisard-synthetic-only", fixture_sha256="e" * 64)
    loader = DataLoader(fixture, batch_size=2, collate_fn=collate)
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    cfg = TrainingConfig(epochs=2, early_stopping_patience=7, batch_size=2, image_size=64,
        device=device, mixed_precision=device.startswith("cuda"), progress=True, checkpoint_every=1,
        checkpoint_root=tmp_path / "checkpoints", profile_output_root=tmp_path / "logs")
    mc = ModelConfig(task="object_detection", num_classes=2, image_size=64)
    model = build_model(mc)
    context = synthetic_training_context("wisard-synthetic", fixture)
    adapter = DetectionTask()
    calls: list[int] = []
    hook = cast(torch.nn.Module, model.backbone).register_forward_hook(lambda *_: calls.append(1))
    first = fit(model, loader, loader, adapter, config=cfg, context=context,
                model_config=mc.model_dump(mode="json"), stop_after_epoch=1)
    assert len(calls) == 2  # One training and one validation backbone pass.
    hook.remove()
    path = cfg.checkpoint_root / "synthetic/epoch-0001.pt"
    sha = json.loads(path.with_suffix(".json").read_bytes())["sha256"]
    with pytest.raises(ValueError, match="checksum"):
        fit(model, loader, loader, adapter, config=cfg, context=context,
            model_config=mc.model_dump(mode="json"), resume_path=path, resume_sha256="0" * 64)
    resumed = fit(build_model(mc), loader, loader, adapter, config=cfg, context=context,
        model_config=mc.model_dump(mode="json"), resume_path=path, resume_sha256=sha)
    assert len(first.history) == 1 and len(resumed.history) == 2
    metrics = resumed.history[-1].validation_metrics
    assert all(0 <= metrics[k] <= 1 for k in ("map50", "map50_95", "precision", "recall"))
    assert adapter.metrics([{**y, "scores": torch.ones(1)}], [y])["map50_95"] == 1
    logs = capture.buffered.getvalue()
    assert capture.flushes >= 10
    for token in ("[cache-build]", "hit=True", "[validation]", "batch=1/1", "train_loss=",
                  "val_loss=", "map50=", "map50_95=", "precision=", "recall=", "eta_s=",
                  "best_checkpoint", "stale=", "[final]"):
        assert token in logs
    if device.startswith("cuda"):
        assert "utilization=" in logs and "allocated_MiB=" in logs
    cached = data._detection_cache.paths[1]
    with cached.open("r+b") as stream:
        stream.seek(-1, 2)
        stream.write(b"x")
    with pytest.raises(ValueError, match="corrupted"):
        prepare_detection_cache(data, tmp_path / "cache")
