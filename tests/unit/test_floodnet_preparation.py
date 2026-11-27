"""Synthetic-only FloodNet pipeline regression checks; no source dataset access."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, cast

import pytest

if importlib.util.find_spec("torch") is None:
    pytest.skip("optional ML dependencies unavailable", allow_module_level=True)

import torch
from PIL import Image
from torch import Tensor, nn
from torch.utils.data import DataLoader

from evaluation.data.contracts import Asset, Manifest, Registry, Sample
from evaluation.data.release_authorization import AuthorizationRecord, manifest_sha256
from evaluation.model1.data import (
    AuthorizedTaskDataset,
    TaskDataConfig,
    TaskValidationSession,
    _image_tensor,
    _mask_tensor,
    fit_training_channel_stats,
)
from evaluation.model1.segmentation import StreamingSegmentation, segmentation_loss
from evaluation.model1.segmentation_cache import prepare_segmentation_cache
from evaluation.model1.training import (
    SegmentationTask,
    SyntheticTaskDataset,
    TrainingConfig,
    fit,
    synthetic_training_context,
)


def fixture_release(tmp_path: Path) -> tuple[Registry, Manifest, Manifest, Path, AuthorizationRecord]:
    registry, inputs, targets, candidate, authorization = importlib.import_module(
        "tests.unit.test_phase11_model1"
    )._authorized_release(tmp_path)
    root = tmp_path / "data"
    rows, labels = [], []
    for i, split in enumerate(("train", "validation", "test")):
        image_path, mask_path = root / f"raw/{split}.png", root / f"labels/{split}.png"
        image = Image.new("RGB", (32, 32), (30 + i * 60, 20, 10))
        image.paste((240, 230-i, 220), (16, 0, 32, 32))
        image.save(image_path)
        mask = Image.new("L", (32, 32), 0)
        mask.paste(5, (16-i, 0, 32, 32))
        mask.save(mask_path)
        row = Sample.model_validate({**inputs.samples[0].model_dump(mode="json"),
            "sample_id": split, "source_ref": split, "sequence_id": split, "split": split,
            "asset": Asset(path=f"raw/{split}.png", sha256=hashlib.sha256(image_path.read_bytes()).hexdigest(), availability="available").model_dump()})
        annotation = targets.samples[0].annotation
        assert annotation is not None
        annotation = annotation.model_copy(update={"format": "mask", "labels": ("background", "water"),
            "asset": Asset(path=f"labels/{split}.png", sha256=hashlib.sha256(mask_path.read_bytes()).hexdigest(), availability="available")})
        rows.append(row)
        labels.append(row.model_copy(update={"annotation": annotation}))
    inputs = inputs.model_copy(update={"samples": tuple(rows)})
    targets = targets.model_copy(update={"samples": tuple(labels)})
    entry = registry.datasets[0].model_copy(update={"label_definitions": {"background": "zero", "water": "five"}})
    registry = registry.model_copy(update={"datasets": (entry,)})
    authorization = authorization.model_copy(update={"training_manifest_sha256": manifest_sha256(inputs),
        "training_targets_manifest_sha256": manifest_sha256(targets)})
    return registry, inputs, targets, candidate, authorization


def dataset(tmp_path: Path, release: Any, split: Any = "train", size: int = 32,
            session: TaskValidationSession | None = None) -> AuthorizedTaskDataset:
    registry, inputs, targets, candidate, auth = release
    return AuthorizedTaskDataset(registry, inputs, targets, tmp_path / "data",
        TaskDataConfig("semantic_segmentation", image_size=size, mask_value_to_label={0: "background", 5: "water"},
                       development_only=True),
        task_id="fixture-classification", candidate_manifest_path=candidate,
        authorization_records=(auth,), split=split, validation_session=session)


def test_vector_mapping_and_rgb_exif_without_mask_rotation(tmp_path: Path) -> None:
    image = Image.new("RGB", (32, 32), (0, 0, 0))
    image.paste((255, 255, 255), (0, 0, 16, 32))
    exif = Image.Exif()
    exif[274] = 3
    path = tmp_path / "rgb.png"
    image.save(path, exif=exif)
    mask = Image.new("L", (32, 32), 0)
    mask.paste(5, (16, 0, 32, 32))
    target = tmp_path / "mask.png"
    mask.save(target)
    x = _image_tensor(path, "RGB", (32, 32))
    y = _mask_tensor(target, (32, 32), {0: "z", 5: "a"}, {"a": 0, "z": 1})
    assert x[:, :, :16].eq(0).all() and x[:, :, 16:].eq(1).all()
    assert y[:, :16].eq(1).all() and y[:, 16:].eq(0).all()
    with pytest.raises(ValueError, match="source-verified"):
        _mask_tensor(target, (32, 32), {0: "z"}, {"z": 0})


def test_cache_integrity_invalidation_normalization_and_test_isolation(tmp_path: Path) -> None:
    release = fixture_release(tmp_path)
    # Test assets are deliberately unavailable: development must never open them.
    (tmp_path / "data/raw/test.png").unlink()
    (tmp_path / "data/labels/test.png").unlink()
    session = TaskValidationSession()
    train = dataset(tmp_path, release, session=session)
    uncached = train[0]
    result = prepare_segmentation_cache(train, tmp_path / "cache")
    assert not result["cache_hit"]
    assert all(torch.equal(a, b) for a, b in zip(uncached, train[0], strict=True))
    fresh = dataset(tmp_path, release, session=session)
    assert prepare_segmentation_cache(fresh, tmp_path / "cache")["cache_hit"]
    other = dataset(tmp_path, release, size=64, session=session)
    assert not prepare_segmentation_cache(other, tmp_path / "cache")["cache_hit"]
    val = dataset(tmp_path, release, split="validation", session=session)
    prepare_segmentation_cache(val, tmp_path / "cache")
    with pytest.raises(ValueError, match="training"):
        fit_training_channel_stats(val)
    mean, scale = fit_training_channel_stats(train)
    train.set_normalization(mean, scale)
    val.set_normalization(mean, scale)
    assert torch.isfinite(val[0][0]).all()
    with pytest.raises(ValueError, match="reserved test"):
        dataset(tmp_path, release, split="test")
    fresh._config.horizontal_flip_probability = 1
    assert torch.equal(fresh[0][1], uncached[1].flip(-1))
    assert torch.equal(fresh[0][0], uncached[0].flip(-1))
    corrupt = Path(result["directory"]) / "masks.npy"
    # Close maps before editing on Windows.
    train._segmentation_cache = None
    fresh._segmentation_cache = None
    with corrupt.open("r+b") as stream:
        stream.seek(-1, 2)
        stream.write(b"\xfe")
    with pytest.raises(ValueError, match="corrupted"):
        prepare_segmentation_cache(dataset(tmp_path, release), tmp_path / "cache")


def test_ce_dice_and_streaming_dataset_metrics() -> None:
    logits = torch.zeros(2, 3, 2, 2, requires_grad=True)
    target = torch.tensor([[[0, 1], [1, 255]], [[1, 0], [0, 255]]])
    loss = segmentation_loss(logits, target, 255, 1)
    assert float(loss.detach()) == pytest.approx(1.0986123 + 0.6, abs=1e-6)
    torch.autograd.backward(loss)
    assert logits.grad is not None and torch.isfinite(logits.grad).all()
    full = StreamingSegmentation(3, torch.device("cpu"))
    chunks = StreamingSegmentation(3, torch.device("cpu"))
    full.update(logits.detach(), target)
    for i in range(2):
        chunks.update(logits[i:i+1].detach(), target[i:i+1])
    assert full.metrics(1) == pytest.approx(chunks.metrics(1))
    values = full.metrics(1)
    assert values["pixel_accuracy"] == 0.5
    assert values["class_2_present"] == 0
    assert values["macro_iou"] == 0.25
    with pytest.raises(ValueError, match="no valid"):
        StreamingSegmentation(3, torch.device("cpu")).metrics()


class CountModel(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.layer = nn.Conv2d(3, 2, 1)
        self.evaluations = 0

    def forward(self, x: Tensor) -> Tensor:
        if not self.training:
            self.evaluations += 1
        return cast(Tensor, self.layer(x))


@pytest.mark.parametrize("device", ["cpu", "cuda:0"])
def test_single_forward_live_logging_and_segmentation_resume(tmp_path: Path, capsys: Any, device: str) -> None:
    if device.startswith("cuda") and not torch.cuda.is_available():
        pytest.skip("CUDA unavailable")
    torch.manual_seed(2025)
    examples = tuple((torch.rand(3, 4, 4), torch.randint(2, (4, 4))) for _ in range(4))
    data = SyntheticTaskDataset(examples, fixture_id="segmentation", fixture_sha256="e"*64)
    context = synthetic_training_context("segmentation", data)
    config = TrainingConfig(epochs=2, checkpoint_every=1, checkpoint_root=tmp_path / "full", progress=True,
                            device=device, mixed_precision=device.startswith("cuda"), amp_dtype="bfloat16")
    model = CountModel().to(device)
    original = copy.deepcopy(model.state_dict())

    def run(config: TrainingConfig, **kwargs: Any) -> Any:
        return fit(model, DataLoader(data, batch_size=2), DataLoader(data, batch_size=2),
                   SegmentationTask(dice_weight=1), config=config, context=context,
                   model_config={"task": "segmentation", "dice_weight": 1}, **kwargs)

    full = run(config)
    expected = copy.deepcopy(model.state_dict())
    assert model.evaluations == 4  # two validation batches per epoch, one forward each
    model.load_state_dict(original)
    partial = config.model_copy(update={"checkpoint_root": tmp_path / "resume"})
    run(partial, stop_after_epoch=1)
    path = partial.checkpoint_root / "synthetic/epoch-0001.pt"
    resumed = run(partial, resume_path=path, resume_sha256=json.loads(path.with_suffix(".json").read_bytes())["sha256"])
    assert full == resumed
    assert all(torch.equal(v, model.state_dict()[k]) for k, v in expected.items())
    output = capsys.readouterr().out
    for text in ("[batch", "lr=", "val_mIoU=", "val_mDice=", "pixel_accuracy=", "checkpoint=", "[stages]", "[final]"):
        assert text in output
