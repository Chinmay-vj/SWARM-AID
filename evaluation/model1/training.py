"""Reusable task adapters and bounded training/evaluation loops."""

import copy
import importlib.util
import json
import random
import sys
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sized
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, cast

import torch
from pydantic import Field, model_validator
from torch import Tensor, nn
from torch.optim import Optimizer
from torch.optim.lr_scheduler import LRScheduler, ReduceLROnPlateau
from torch.utils.data import DataLoader, Dataset

from agents.shared.domain import Record
from evaluation.data.release_authorization import Digest
from evaluation.model1.active_scope import require_trainable_task
from evaluation.model1.metrics import (
    classification_metrics,
    detection_metrics,
    expected_calibration_error,
    regression_metrics,
    segmentation_metrics,
)
from evaluation.model1.segmentation import StreamingSegmentation, segmentation_loss


class TrainingConfig(Record):
    epochs: int = Field(default=30, ge=1)
    learning_rate: float = Field(default=0.001, gt=0)
    weight_decay: float = Field(default=0.0001, ge=0)
    gradient_accumulation: int = Field(default=1, ge=1)
    early_stopping_patience: int = Field(default=5, ge=1)
    gradient_clip_norm: float = Field(default=1.0, gt=0)
    mixed_precision: bool = False
    amp_dtype: Literal["float16", "bfloat16"] = "bfloat16"
    seed: int = Field(default=2025, ge=0)
    device: str = "cpu"
    batch_size: int = Field(default=8, ge=1)
    workers: int = Field(default=0, ge=0)
    image_size: int = Field(default=224, ge=32)
    checkpoint_every: int = Field(default=0, ge=0)
    max_gpu_memory_gb: float = Field(default=24, gt=0)
    checkpoint_root: Path = Path(r"D:\SWARM-AID-DATA\checkpoints")
    profile_output_root: Path = Path(r"D:\SWARM-AID-DATA\runs\phase11")
    progress: bool = False


class TrainingContext(Record):
    artifact_kind: Literal[
        "synthetic_fixture", "authorized_training", "authorized_symbolic_training"
    ]
    task_id: str = Field(min_length=1)
    release_manifest_sha256: Digest
    authorization_id: str | None = None
    candidate_manifest_sha256: Digest | None = None
    training_targets_manifest_sha256: Digest | None = None

    @model_validator(mode="after")
    def gate_real_training(self) -> "TrainingContext":
        if self.artifact_kind in {"authorized_training", "authorized_symbolic_training"} and (
            not self.authorization_id
            or self.candidate_manifest_sha256 is None
            or self.training_targets_manifest_sha256 is None
        ):
            raise ValueError(
                "real training requires explicit task authorization and bound manifests"
            )
        if self.artifact_kind == "synthetic_fixture" and (
            self.authorization_id is not None
            or self.candidate_manifest_sha256 is not None
            or self.training_targets_manifest_sha256 is not None
        ):
            raise ValueError("synthetic fixture context cannot claim real-data authorization")
        return self


@dataclass(frozen=True)
class PredictionBatch:
    logits: Tensor
    valid: Tensor | None = None


class TaskAdapter(Protocol):
    def loss(self, model: nn.Module, features: Any, targets: Any) -> Tensor: ...

    def predict(self, model: nn.Module, features: Any) -> Any: ...

    def metrics(self, predictions: Any, targets: Any) -> dict[str, float]: ...

    def selection_score(
        self, metrics: Mapping[str, float]
    ) -> tuple[float, Literal["min", "max"]]: ...


class GradientScaler(Protocol):
    def scale(self, loss: Tensor) -> Tensor: ...

    def unscale_(self, optimizer: Optimizer) -> None: ...

    def step(self, optimizer: Optimizer) -> Any: ...

    def update(self) -> None: ...

    def state_dict(self) -> dict[str, Any]: ...

    def load_state_dict(self, state: dict[str, Any]) -> None: ...


class ClassificationTask:
    def __init__(self) -> None:
        self.criterion = nn.CrossEntropyLoss()

    def loss(self, model: nn.Module, features: Any, targets: Tensor) -> Tensor:
        logits, valid = _classification_output(model, features)
        if valid is not None:
            logits, targets = logits[valid], targets[valid]
        if not len(targets):
            raise ValueError("classification batch has no available sensor evidence")
        return cast(Tensor, self.criterion(logits, targets))

    def predict(self, model: nn.Module, features: Any) -> PredictionBatch:
        logits, valid = _classification_output(model, features)
        return PredictionBatch(logits.detach(), valid.detach() if valid is not None else None)

    def metrics(self, predictions: PredictionBatch, targets: Tensor) -> dict[str, float]:
        if predictions.valid is not None:
            selected = predictions.valid
            predictions = PredictionBatch(predictions.logits[selected])
            targets = targets[selected]
        if not len(targets):
            raise ValueError("validation partition has no available sensor evidence")
        values = classification_metrics(predictions.logits, targets)
        values["ece"] = expected_calibration_error(predictions.logits, targets)
        return values

    def selection_score(self, metrics: Mapping[str, float]) -> tuple[float, Literal["min", "max"]]:
        return metrics["macro_f1"], "max"


class SegmentationTask:
    def __init__(self, ignore_index: int = 255, *, dice_weight: float = 0.0) -> None:
        if not 0 <= dice_weight <= 10:
            raise ValueError("Dice weight must be finite and between zero and ten")
        self.ignore_index = ignore_index
        self.dice_weight = dice_weight
        self.criterion = nn.CrossEntropyLoss(ignore_index=ignore_index)

    def loss(self, model: nn.Module, features: Tensor, targets: Tensor) -> Tensor:
        logits = _segmentation_output(model(features))
        if self.dice_weight == 0:
            return cast(Tensor, self.criterion(logits, targets))
        return segmentation_loss(logits, targets, self.ignore_index, self.dice_weight)

    def predict(self, model: nn.Module, features: Tensor) -> Tensor:
        return _segmentation_output(model(features)).detach()

    def metrics(self, predictions: Tensor, targets: Tensor) -> dict[str, float]:
        return segmentation_metrics(
            predictions, targets, predictions.shape[1], ignore_index=self.ignore_index
        )

    def selection_score(self, metrics: Mapping[str, float]) -> tuple[float, Literal["min", "max"]]:
        return metrics["macro_iou"], "max"


class DetectionTask:
    def validate_batch(
        self, model: nn.Module, features: list[Tensor], targets: list[dict[str, Tensor]]
    ) -> tuple[list[dict[str, Tensor]], Tensor]:
        """Faster R-CNN validation: one transform/backbone, separate head modes.

        Evaluation proposals produce metrics; sampled training proposals produce
        diagnostic losses. BatchNorm stays in eval mode and sampling preserves RNG.
        """
        detector: Any = model
        sizes = [tuple(image.shape[-2:]) for image in features]
        images, transformed = detector.transform(features, targets)
        encoded = detector.backbone(images.tensors)
        if isinstance(encoded, Tensor):
            encoded = {"0": encoded}
        proposals, _ = detector.rpn(images, encoded, transformed)
        predictions, _ = detector.roi_heads(encoded, proposals, images.image_sizes)
        predictions = detector.transform.postprocess(predictions, images.image_sizes, sizes)
        devices = [features[0].device.index or 0] if features[0].is_cuda else []
        flags = detector.rpn.training, detector.roi_heads.training
        try:
            with torch.random.fork_rng(devices=devices):
                detector.rpn.training = detector.roi_heads.training = True
                proposals, rpn_losses = detector.rpn(images, encoded, transformed)
                _, roi_losses = detector.roi_heads(
                    encoded, proposals, images.image_sizes, transformed
                )
                loss = torch.stack(list(rpn_losses.values()) + list(roi_losses.values())).sum()
        finally:
            detector.rpn.training, detector.roi_heads.training = flags
        return cast(list[dict[str, Tensor]], predictions), loss

    def loss(
        self, model: nn.Module, features: list[Tensor], targets: list[dict[str, Tensor]]
    ) -> Tensor:
        losses: Any = model(features, targets)
        if not isinstance(losses, dict) or not losses:
            raise ValueError("detection training model must return named loss tensors")
        terms = [value for value in losses.values() if isinstance(value, Tensor)]
        if len(terms) != len(losses):
            raise TypeError("detection loss values must be tensors")
        return torch.stack(terms).sum()

    def predict(self, model: nn.Module, features: list[Tensor]) -> list[dict[str, Tensor]]:
        predictions: Any = model(features)
        if not isinstance(predictions, list) or any(
            not isinstance(item, dict)
            or any(not isinstance(value, Tensor) for value in item.values())
            for item in predictions
        ):
            raise TypeError("detection model must return lists of tensor dictionaries")
        return cast(list[dict[str, Tensor]], predictions)

    def metrics(
        self, predictions: list[dict[str, Tensor]], targets: list[dict[str, Tensor]]
    ) -> dict[str, float]:
        metrics = detection_metrics(predictions, targets)
        average_precisions = [metrics["map50"]]
        for threshold in range(55, 100, 5):
            result = detection_metrics(predictions, targets, iou_threshold=threshold / 100)
            average_precisions.append(result["map50"])
        metrics["map50_95"] = sum(average_precisions) / len(average_precisions)
        return metrics

    def selection_score(self, metrics: Mapping[str, float]) -> tuple[float, Literal["min", "max"]]:
        return metrics["map50"], "max"


class RegressionTask:
    def __init__(self, loss: Literal["mse", "huber"] = "mse", huber_delta: float = 1.0) -> None:
        if loss not in {"mse", "huber"} or huber_delta <= 0:
            raise ValueError("invalid regression loss configuration")
        self.loss_kind = loss
        self.huber_delta = huber_delta

    def loss(self, model: nn.Module, features: Any, targets: Tensor) -> Tensor:
        predictions, valid = _regression_output(model, features)
        return self.loss_from_outputs(predictions, valid, targets)

    def loss_from_outputs(
        self, predictions: Tensor, valid: Tensor | None, targets: Tensor
    ) -> Tensor:
        if valid is not None:
            predictions, targets = predictions[valid], targets[valid]
        if not len(targets):
            raise ValueError("regression batch has no available sensor evidence")
        if self.loss_kind == "huber":
            return nn.functional.huber_loss(predictions, targets, delta=self.huber_delta)
        return nn.functional.mse_loss(predictions, targets)

    def predict(self, model: nn.Module, features: Any) -> PredictionBatch:
        predictions, valid = _regression_output(model, features)
        return PredictionBatch(predictions.detach(), valid.detach() if valid is not None else None)

    def metrics(self, predictions: PredictionBatch, targets: Tensor) -> dict[str, float]:
        if predictions.valid is not None:
            selected = predictions.valid
            predictions = PredictionBatch(predictions.logits[selected])
            targets = targets[selected]
        return regression_metrics(predictions.logits, targets)

    def selection_score(self, metrics: Mapping[str, float]) -> tuple[float, Literal["min", "max"]]:
        return metrics["rmse"], "min"


@dataclass(frozen=True)
class EpochResult:
    epoch: int
    train_loss: float
    validation_score: float
    validation_metrics: dict[str, float]
    global_step: int
    best_epoch: int
    stage_timings: dict[str, float] = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class TrainingResult:
    history: tuple[EpochResult, ...]
    best_epoch: int
    best_score: float
    global_step: int


class SyntheticTaskDataset(Dataset[tuple[Any, Any]]):
    """In-memory fixtures are explicitly tagged and cannot impersonate a real release."""

    def __init__(
        self,
        examples: tuple[tuple[Any, Any], ...],
        *,
        fixture_id: str,
        fixture_sha256: str,
    ) -> None:
        if not examples or not fixture_id.strip() or len(fixture_sha256) != 64:
            raise ValueError("synthetic fixture requires examples and checksum-bound identity")
        self.examples = examples
        self.fixture_id = fixture_id
        self.fixture_sha256 = fixture_sha256

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, index: int) -> tuple[Any, Any]:
        return self.examples[index]


def authorized_training_context(dataset: Any) -> TrainingContext:
    if getattr(dataset, "split", None) != "train":
        raise ValueError("real training context requires an authorized training partition")
    return TrainingContext(
        artifact_kind="authorized_training",
        task_id=dataset.task_id,
        release_manifest_sha256=dataset.manifest_sha256,
        authorization_id=dataset.authorization_id,
        candidate_manifest_sha256=dataset.candidate_manifest_sha256,
        training_targets_manifest_sha256=dataset.target_manifest_sha256,
    )


def seed_everything(seed: int, *, deterministic: bool = True) -> None:
    if seed < 0:
        raise ValueError("seed must be nonnegative")
    random.seed(seed)
    torch.manual_seed(seed)
    if importlib.util.find_spec("numpy") is not None:
        import numpy as np

        np.random.seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = deterministic
    torch.use_deterministic_algorithms(deterministic, warn_only=True)


def synthetic_training_context(task_id: str, fixture: SyntheticTaskDataset) -> TrainingContext:
    return TrainingContext(
        artifact_kind="synthetic_fixture",
        task_id=task_id,
        release_manifest_sha256=fixture.fixture_sha256,
    )


def make_gradient_scaler(*, enabled: bool) -> GradientScaler:
    constructor = cast(Callable[..., GradientScaler], vars(torch.amp)["GradScaler"])
    return constructor("cuda", enabled=enabled)


def fit(
    model: nn.Module,
    train_batches: Iterable[tuple[Any, Any]],
    validation_batches: Iterable[tuple[Any, Any]],
    adapter: TaskAdapter,
    *,
    config: TrainingConfig,
    context: TrainingContext,
    optimizer: Optimizer | None = None,
    scheduler: LRScheduler | ReduceLROnPlateau | None = None,
    resume_path: Path | None = None,
    resume_sha256: str | None = None,
    model_config: dict[str, Any] | None = None,
    stop_after_epoch: int | None = None,
    deadline: float | None = None,
) -> TrainingResult:
    require_trainable_task(context.task_id)
    _validate_training_sources(train_batches, validation_batches, context)
    from evaluation.model1.checkpoints import restore_checkpoint, save_checkpoint

    if (resume_path is None) != (resume_sha256 is None):
        raise ValueError("resume requires both checkpoint path and checksum")
    if config.checkpoint_every or resume_path is not None:
        if model_config is None:
            raise ValueError("checkpointing requires an explicit model configuration")
        for loader in (train_batches, validation_batches):
            if not isinstance(loader, DataLoader) or loader.num_workers != 0:
                raise ValueError("exact epoch resume requires zero-worker DataLoaders")
        if config.checkpoint_root.resolve().drive.upper() != "D:" and sys.platform == "win32":
            raise ValueError("checkpoint output must remain on D:")
    device = torch.device(config.device)
    if device.type not in {"cpu", "cuda"}:
        raise ValueError("Model 1 training supports CPU and CUDA devices only")
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable")
    if config.mixed_precision and device.type not in {"cuda", "cpu"}:
        raise ValueError("mixed precision is unsupported on the requested device")
    if config.epochs > 1 and isinstance(train_batches, Iterator):
        raise ValueError("multiple epochs require a re-iterable training loader")
    if config.epochs > 1 and isinstance(validation_batches, Iterator):
        raise ValueError("multiple epochs require a re-iterable validation loader")
    if config.mixed_precision and device.type == "cpu" and config.amp_dtype == "float16":
        raise ValueError("CPU mixed precision requires bfloat16")
    if device.type == "cuda":
        index = device.index if device.index is not None else torch.cuda.current_device()
        total = torch.cuda.get_device_properties(index).total_memory
        torch.cuda.set_per_process_memory_fraction(
            min(0.8, config.max_gpu_memory_gb * 1024**3 / total), index
        )
    seed_everything(config.seed)
    model.to(device)
    optimizer = optimizer or torch.optim.AdamW(
        model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay
    )
    scaler = make_gradient_scaler(
        enabled=config.mixed_precision and device.type == "cuda" and config.amp_dtype == "float16"
    )
    history: list[EpochResult] = []
    best_state: dict[str, Tensor] | None = None
    best_optimizer_state: dict[str, Any] | None = None
    best_scheduler_state: dict[str, Any] | None = None
    best_scaler_state: dict[str, Any] | None = None
    best_score: float | None = None
    best_epoch = 0
    best_global_step = 0
    global_step = 0
    stale_epochs = 0
    start_epoch = 1
    run_started = time.perf_counter()
    checkpoint_path: Path | None = None
    if resume_path is not None and resume_sha256 is not None:
        restored = restore_checkpoint(
            resume_path,
            resume_sha256,
            config.checkpoint_root,
            model,
            optimizer,
            scheduler,
            scaler,
            expected_model_config=model_config or {},
            expected_training_config=config.model_dump(mode="json"),
            expected_context=context,
            device=device,
        )
        state = restored.loop_state
        if not state:
            raise ValueError("checkpoint lacks epoch-resume loop state")
        start_epoch = restored.epoch + 1
        global_step = restored.global_step
        best_score, best_epoch = state["best_score"], state["best_epoch"]
        stale_epochs = state["stale_epochs"]
        best_state, best_optimizer_state = state["best_state"], state["best_optimizer_state"]
        best_scheduler_state, best_scaler_state = (
            state["best_scheduler_state"],
            state["best_scaler_state"],
        )
        best_global_step = state["best_global_step"]
        history = [EpochResult(**item) for item in state["history"]]
        for label, loader in (("train", train_batches), ("validation", validation_batches)):
            if isinstance(loader, DataLoader) and loader.generator is not None:
                loader.generator.set_state(state[label + "_generator"])
        if start_epoch > config.epochs or stale_epochs >= config.early_stopping_patience:
            raise ValueError("checkpoint run has already completed or early-stopped")
    out_of_time = False
    for epoch in range(start_epoch, config.epochs + 1):
        epoch_started = time.perf_counter()
        stage_timings = {
            "loader_wait_seconds": 0.0,
            "host_to_device_seconds": 0.0,
            "forward_and_loss_seconds": 0.0,
            "backward_and_optimizer_seconds": 0.0,
            "validation_forward_and_loss_seconds": 0.0,
            "checkpoint_save_seconds": 0.0,
        }
        cuda_intervals: dict[str, list[tuple[Any, Any]]] = {}

        def start_stage() -> Any:
            if device.type == "cuda":
                event = cast(Any, torch.cuda.Event)(enable_timing=True)
                event.record()
                return event
            return time.perf_counter()

        def stop_stage(
            name: str,
            started: Any,
            *,
            _cuda_intervals: dict[str, list[tuple[Any, Any]]] = cuda_intervals,
            _stage_timings: dict[str, float] = stage_timings,
        ) -> None:
            if device.type == "cuda":
                ended = cast(Any, torch.cuda.Event)(enable_timing=True)
                ended.record()
                _cuda_intervals.setdefault(name, []).append((started, ended))
            else:
                _stage_timings[name] += time.perf_counter() - started

        def record_loader_wait(
            seconds: float, *, _stage_timings: dict[str, float] = stage_timings
        ) -> None:
            _stage_timings["loader_wait_seconds"] += seconds

        model.train()
        optimizer.zero_grad(set_to_none=True)
        total_loss: Tensor | None = None
        batch_count = 0
        pending = 0
        for batch_index, ((features, targets), is_last_batch) in enumerate(
            _with_last(train_batches, on_wait=record_loader_wait)
        ):
            transfer_started = start_stage()
            features = _to_device(features, device)
            targets = _to_device(targets, device)
            stop_stage("host_to_device_seconds", transfer_started)
            forward_started = start_stage()
            with _autocast(device, config):
                if isinstance(adapter, RegressionTask):
                    outputs, valid = _regression_output(model, features)
                    loss = adapter.loss_from_outputs(outputs, valid, targets)
                else:
                    loss = adapter.loss(model, features, targets)
            stop_stage("forward_and_loss_seconds", forward_started)
            if not torch.isfinite(loss):
                raise ValueError("nonfinite training loss")
            backward_started = start_stage()
            torch.autograd.backward(scaler.scale(loss / config.gradient_accumulation))
            total_loss = (
                loss.detach().to(torch.float64)
                if total_loss is None
                else total_loss + loss.detach().to(torch.float64)
            )
            batch_count += 1
            pending += 1
            if pending == config.gradient_accumulation or is_last_batch:
                scaler.unscale_(optimizer)
                if pending < config.gradient_accumulation:
                    correction = config.gradient_accumulation / pending
                    for parameter in model.parameters():
                        if parameter.grad is not None:
                            parameter.grad.mul_(correction)
                torch.nn.utils.clip_grad_norm_(
                    model.parameters(), config.gradient_clip_norm, error_if_nonfinite=True
                )
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad(set_to_none=True)
                global_step += 1
                pending = 0
            stop_stage("backward_and_optimizer_seconds", backward_started)
            if config.progress and ((batch_index + 1) % 10 == 0 or is_last_batch):
                try:
                    total_batches = len(train_batches)  # type: ignore[arg-type]
                except TypeError:
                    total_batches = 0
                elapsed = time.perf_counter() - epoch_started
                remaining_batches = max(total_batches - batch_index - 1, 0)
                eta = elapsed / (batch_index + 1) * remaining_batches if total_batches else 0.0
                count_label = str(total_batches) if total_batches else "?"
                print(
                    f"[batch {batch_index + 1}/{count_label}] epoch={epoch}/{config.epochs} "
                    f"loss={float(total_loss.cpu()) / batch_count:.6f} "
                    f"lr={optimizer.param_groups[0]['lr']:.6g} "
                    f"elapsed_s={elapsed:.1f} eta_s={eta:.1f} "
                    + (
                        f"allocated_MiB={torch.cuda.memory_allocated(device) / 2**20:.1f} "
                        f"reserved_MiB={torch.cuda.memory_reserved(device) / 2**20:.1f} "
                        f"peak_MiB={torch.cuda.max_memory_allocated(device) / 2**20:.1f} "
                        f"utilization={_sample_gpu_utilization()}"
                        if device.type == "cuda"
                        else "device=cpu"
                    ),
                    flush=True,
                )
        if batch_count == 0:
            raise ValueError("training loader is empty")
        model.eval()
        predictions: list[Any] = []
        expected: list[Any] = []
        validation_loss_total: Tensor | None = None
        validation_batch_count = 0
        segmentation_state: StreamingSegmentation | None = None
        prediction: Any
        with torch.inference_mode():
            for features, targets in _iter_with_wait(
                validation_batches, on_wait=record_loader_wait
            ):
                transfer_started = start_stage()
                features = _to_device(features, device)
                targets = _to_device(targets, device)
                stop_stage("host_to_device_seconds", transfer_started)
                validation_started = start_stage()
                if isinstance(adapter, SegmentationTask):
                    with _autocast(device, config):
                        logits = _segmentation_output(model(features))
                    if segmentation_state is None:
                        segmentation_state = StreamingSegmentation(
                            logits.shape[1], device, adapter.ignore_index
                        )
                    segmentation_state.update(logits, targets)
                    batch_loss = logits.new_zeros(())
                    del logits
                elif isinstance(adapter, RegressionTask):
                    output, valid = _regression_output(model, features)
                    prediction = PredictionBatch(
                        output.detach(), valid.detach() if valid is not None else None
                    )
                    batch_loss = adapter.loss_from_outputs(output, valid, targets)
                elif isinstance(adapter, ClassificationTask):
                    logits, valid = _classification_output(model, features)
                    prediction = PredictionBatch(
                        logits.detach(), valid.detach() if valid is not None else None
                    )
                    selected_logits = logits
                    selected_targets = targets

                    if valid is not None:
                        selected_logits = logits[valid]
                        selected_targets = targets[valid]

                    if not len(selected_targets):
                        raise ValueError("classification batch has no available sensor evidence")

                    batch_loss = adapter.criterion(selected_logits, selected_targets)
                elif isinstance(adapter, DetectionTask):
                    with _autocast(device, config):
                        prediction, batch_loss = adapter.validate_batch(model, features, targets)
                    prediction = _to_device(prediction, torch.device("cpu"))
                    targets = _to_device(targets, torch.device("cpu"))
                else:
                    prediction = adapter.predict(model, features)
                    batch_loss = adapter.loss(model, features, targets)
                stop_stage("validation_forward_and_loss_seconds", validation_started)
                if not isinstance(adapter, SegmentationTask):
                    predictions.append(prediction)
                    expected.append(targets)
                validation_loss_total = (
                    batch_loss.detach().to(torch.float64)
                    if validation_loss_total is None
                    else validation_loss_total + batch_loss.detach().to(torch.float64)
                )
                validation_batch_count += 1
                if config.progress and isinstance(adapter, DetectionTask):
                    validation_total = (
                        len(validation_batches) if isinstance(validation_batches, Sized) else "?"
                    )
                    print(
                        f"[validation] epoch={epoch}/{config.epochs} "
                        f"batch={validation_batch_count}/{validation_total} "
                        f"loss={float(batch_loss):.6f}",
                        flush=True,
                    )
        if not validation_batch_count:
            raise ValueError("validation loader is empty")
        if validation_loss_total is None:
            raise RuntimeError("validation did not produce a loss")
        validation_loss = float(validation_loss_total.cpu()) / validation_batch_count
        if isinstance(adapter, SegmentationTask):
            assert segmentation_state is not None
            validation_metrics = segmentation_state.metrics(adapter.dice_weight)
            validation_loss = validation_metrics["validation_loss"]
        else:
            merged_predictions, merged_expected = _merge_batches(predictions, expected)
            validation_metrics = adapter.metrics(merged_predictions, merged_expected)
        score, direction = adapter.selection_score(validation_metrics)
        if not torch.isfinite(torch.tensor(score)):
            raise ValueError("nonfinite validation score")
        improved = best_score is None or (
            score < best_score if direction == "min" else score > best_score
        )
        if improved:
            best_score = score
            best_epoch = epoch
            stale_epochs = 0
        else:
            stale_epochs += 1
        if scheduler is not None:
            if isinstance(scheduler, ReduceLROnPlateau):
                scheduler.step(score)
            else:
                scheduler.step()
        if improved:
            best_state = copy.deepcopy(model.state_dict())
            best_optimizer_state = copy.deepcopy(optimizer.state_dict())
            best_scheduler_state = (
                copy.deepcopy(scheduler.state_dict()) if scheduler is not None else None
            )
            best_scaler_state = copy.deepcopy(scaler.state_dict())
            best_global_step = global_step
        history.append(
            EpochResult(
                epoch,
                float(total_loss.cpu()) / batch_count if total_loss is not None else 0.0,
                score,
                validation_metrics,
                global_step,
                best_epoch,
                stage_timings,
            )
        )
        if device.type == "cuda":
            torch.cuda.synchronize(device)
            for name, intervals in cuda_intervals.items():
                stage_timings[name] = sum(
                    started.elapsed_time(ended) / 1000.0 for started, ended in intervals
                )
        if config.checkpoint_every and (epoch % config.checkpoint_every == 0):
            assert best_score is not None
            loop_state = {
                "best_score": best_score,
                "best_epoch": best_epoch,
                "stale_epochs": stale_epochs,
                "best_state": best_state,
                "best_optimizer_state": best_optimizer_state,
                "best_scheduler_state": best_scheduler_state,
                "best_scaler_state": best_scaler_state,
                "best_global_step": best_global_step,
                "history": [asdict(item) for item in history],
            }
            for label, loader in (("train", train_batches), ("validation", validation_batches)):
                if isinstance(loader, DataLoader) and loader.generator is not None:
                    loop_state[label + "_generator"] = loader.generator.get_state()
            checkpoint_started = time.perf_counter()
            checkpoint = save_checkpoint(
                config.checkpoint_root,
                f"epoch-{epoch:04d}.pt",
                model,
                optimizer,
                scheduler,
                scaler,
                epoch=epoch,
                global_step=global_step,
                best_validation_metric=float(best_score),
                model_config=model_config or {},
                training_config=config.model_dump(mode="json"),
                context=context,
                loop_state=loop_state,
            )
            stage_timings["checkpoint_save_seconds"] = time.perf_counter() - checkpoint_started
            checkpoint_path = checkpoint.path
            checkpoint.path.with_suffix(".json").write_text(
                json.dumps(
                    {
                        "sha256": checkpoint.sha256,
                        "result": asdict(history[-1]),
                        "context": context.model_dump(mode="json"),
                    },
                    sort_keys=True,
                ),
                encoding="utf8",
            )
        epoch_duration = time.perf_counter() - epoch_started
        if config.progress:
            elapsed_remaining = epoch_duration * (config.epochs - epoch)
            metrics = history[-1].validation_metrics
            maermse = ""
            if "macro_f1" in metrics and "accuracy" in metrics:
                maermse = (
                    f" val_accuracy={metrics['accuracy']:.6f}"
                    f" val_macro_f1={metrics['macro_f1']:.6f}"
                    f" val_precision={metrics['macro_precision']:.6f}"
                    f" val_recall={metrics['macro_recall']:.6f}"
                )
            if "mae" in metrics:
                maermse = f" val_mae={metrics['mae']:.6f} val_rmse={metrics['rmse']:.6f}"
            if "map50" in metrics:
                maermse = " " + " ".join(
                    f"{key}={metrics[key]:.6f}"
                    for key in ("map50", "map50_95", "precision", "recall")
                )
            if "macro_iou" in metrics:
                maermse = (
                    f" val_mIoU={metrics['macro_iou']:.6f} "
                    f"val_mDice={metrics['macro_dice']:.6f} "
                    f"pixel_accuracy={metrics['pixel_accuracy']:.6f}"
                )
            print(
                f"[epoch {epoch}/{config.epochs}] "
                f"train_loss={history[-1].train_loss:.6f} "
                f"val_loss={validation_loss:.6f}"
                f"{maermse} "
                f"epoch_s={epoch_duration:.2f} "
                f"eta_s={elapsed_remaining:.1f}"
                f" total_s={time.perf_counter() - run_started:.2f} "
                f"best_epoch={best_epoch} best_score={best_score:.6f} "
                f"stale={stale_epochs}/{config.early_stopping_patience} "
                f"checkpoint={checkpoint_path}"
                f"{' best_checkpoint_updated' if improved else ''}",
                flush=True,
            )
            print(
                "[stages] "
                + " ".join(f"{name}={seconds:.3f}s" for name, seconds in stage_timings.items()),
                flush=True,
            )
        if deadline is not None:
            # Stop only between epochs, after the checkpoint above has been written.
            remaining = deadline - time.time()
            out_of_time = remaining < 1.15 * (time.perf_counter() - epoch_started)
            if config.progress:
                print(
                    f"[deadline] remaining_s={remaining:.0f} "
                    f"run_elapsed_s={time.perf_counter() - run_started:.0f}",
                    flush=True,
                )
        if (
            stale_epochs >= config.early_stopping_patience
            or out_of_time
            or stop_after_epoch is not None
            and epoch >= stop_after_epoch
        ):
            break
    if (
        best_state is None
        or best_optimizer_state is None
        or best_scaler_state is None
        or best_score is None
    ):
        raise RuntimeError("training did not produce a valid checkpoint state")
    model.load_state_dict(best_state)
    optimizer.load_state_dict(best_optimizer_state)
    if scheduler is not None:
        if best_scheduler_state is None:
            raise RuntimeError("best scheduler state is missing")
        scheduler.load_state_dict(best_scheduler_state)
    scaler.load_state_dict(best_scaler_state)
    if config.progress:
        reason = (
            "early_stopping"
            if stale_epochs >= config.early_stopping_patience
            else "deadline"
            if out_of_time
            else "requested_epoch_boundary"
            if stop_after_epoch is not None
            else "maximum_epochs"
        )
        best_path = (
            config.checkpoint_root
            / (
                "synthetic"
                if context.artifact_kind == "synthetic_fixture"
                else "authorized-symbolic-training"
                if context.artifact_kind == "authorized_symbolic_training"
                else "authorized-training"
            )
            / f"epoch-{best_epoch:04d}.pt"
        )
        print(
            f"[final] reason={reason} best_epoch={best_epoch} best_score={best_score:.6f} "
            f"duration_s={time.perf_counter() - run_started:.2f} "
            f"best_checkpoint={best_path if best_path.is_file() else 'not_saved'} "
            f"report_root={config.profile_output_root}",
            flush=True,
        )
    return TrainingResult(tuple(history), best_epoch, best_score, best_global_step)


def _classification_output(model: nn.Module, features: Any) -> tuple[Tensor, Tensor | None]:
    output = model(**features) if isinstance(features, Mapping) else model(features)
    if isinstance(output, tuple) and len(output) == 2:
        logits, valid = output
        if isinstance(logits, Tensor) and isinstance(valid, Tensor):
            return logits, valid
    if isinstance(output, Tensor):
        return output, None
    raise ValueError("classification model must return logits and optional validity mask")


def _regression_output(model: nn.Module, features: Any) -> tuple[Tensor, Tensor | None]:
    output = model(**features) if isinstance(features, Mapping) else model(features)
    if isinstance(output, tuple) and len(output) == 2:
        predictions, valid = output
        if isinstance(predictions, Tensor) and isinstance(valid, Tensor):
            return predictions, valid
    if isinstance(output, Tensor):
        return output, None
    raise ValueError("regression model must return values and optional validity mask")


def _segmentation_output(output: Any) -> Tensor:
    if isinstance(output, Mapping) and isinstance(output.get("out"), Tensor):
        return cast(Tensor, output["out"])
    if isinstance(output, Tensor):
        return output
    raise ValueError("segmentation model must return logits or an output mapping")


def _to_device(value: Any, device: torch.device) -> Any:
    if isinstance(value, Tensor):
        return value.to(device, non_blocking=device.type == "cuda")
    if isinstance(value, dict):
        return {key: _to_device(item, device) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_device(item, device) for item in value]
    if isinstance(value, tuple):
        return tuple(_to_device(item, device) for item in value)
    return value


def _autocast(device: torch.device, config: TrainingConfig) -> Any:
    dtype = torch.float16 if config.amp_dtype == "float16" else torch.bfloat16
    enabled = config.mixed_precision and (device.type == "cuda" or dtype == torch.bfloat16)
    return torch.autocast(device_type=device.type, dtype=dtype, enabled=enabled)


def _merge_batches(predictions: list[Any], targets: list[Any]) -> tuple[Any, Any]:
    first = predictions[0]
    if isinstance(first, PredictionBatch):
        logits = torch.cat([item.logits for item in predictions], dim=0)
        masks = [item.valid for item in predictions]
        valid = (
            torch.cat([mask for mask in masks if mask is not None])
            if all(mask is not None for mask in masks)
            else None
        )
        return PredictionBatch(logits, valid), torch.cat(targets, dim=0)
    if isinstance(first, Tensor):
        return torch.cat(predictions, dim=0), torch.cat(targets, dim=0)
    if isinstance(first, list):
        return [item for batch in predictions for item in batch], [
            item for batch in targets for item in batch
        ]
    raise ValueError("unsupported task prediction type")


def _with_last(
    batches: Iterable[tuple[Any, Any]],
    *,
    on_wait: Callable[[float], None] | None = None,
) -> Iterable[tuple[tuple[Any, Any], bool]]:
    iterator = iter(_iter_with_wait(batches, on_wait=on_wait))
    try:
        current = next(iterator)
    except StopIteration:
        return
    for following in iterator:
        yield current, False
        current = following
    yield current, True


def _iter_with_wait(
    batches: Iterable[tuple[Any, Any]],
    *,
    on_wait: Callable[[float], None] | None = None,
) -> Iterator[tuple[Any, Any]]:
    iterator = iter(batches)
    while True:
        started = time.perf_counter()
        try:
            batch = next(iterator)
        except StopIteration:
            return
        if on_wait is not None:
            on_wait(time.perf_counter() - started)
        yield batch


def _validate_training_sources(
    train_batches: Iterable[tuple[Any, Any]],
    validation_batches: Iterable[tuple[Any, Any]],
    context: TrainingContext,
) -> None:
    if not isinstance(train_batches, DataLoader) or not isinstance(validation_batches, DataLoader):
        raise TypeError("training requires explicit authorized or synthetic data loaders")
    training_data, validation_data = train_batches.dataset, validation_batches.dataset
    if context.artifact_kind == "synthetic_fixture":
        if (
            not isinstance(training_data, SyntheticTaskDataset)
            or not isinstance(validation_data, SyntheticTaskDataset)
            or training_data.fixture_id != validation_data.fixture_id
            or training_data.fixture_sha256 != context.release_manifest_sha256
            or validation_data.fixture_sha256 != context.release_manifest_sha256
        ):
            raise ValueError("synthetic context requires matching synthetic fixture loaders")
        return
    from evaluation.model1.symbolic_dataset import (
        AuthorizedSymbolicDataset,
        digest,
    )

    if context.artifact_kind == "authorized_symbolic_training":
        if (
            not isinstance(training_data, AuthorizedSymbolicDataset)
            or not isinstance(validation_data, AuthorizedSymbolicDataset)
            or training_data.split != "train"
            or validation_data.split != "validation"
        ):
            raise ValueError("Symbolic context requires matching symbolic partitions")

        for dataset in (training_data, validation_data):
            fresh = AuthorizedSymbolicDataset(dataset.split)

            if (
                dataset.manifest_sha256 != fresh.manifest_sha256
                or dataset.approval_sha256 != fresh.approval_sha256
                or dataset.config != fresh.config
                or dataset.release != fresh.release
                or not torch.equal(dataset.values, fresh.values)
                or not torch.equal(dataset.available, fresh.available)
                or not torch.equal(dataset.targets, fresh.targets)
                or context.task_id != "offline-environment-classification"
                or context.release_manifest_sha256 != fresh.manifest_sha256
                or context.authorization_id != fresh.approval_sha256
                or context.candidate_manifest_sha256 != digest(fresh.release / "provenance.json")
                or context.training_targets_manifest_sha256 != digest(fresh.release / "targets.npy")
            ):
                raise ValueError("Symbolic authorization binding mismatch")
        return

    from evaluation.model1.data import AuthorizedFusionDataset, AuthorizedTaskDataset

    if (
        not isinstance(training_data, (AuthorizedTaskDataset, AuthorizedFusionDataset))
        or not isinstance(validation_data, (AuthorizedTaskDataset, AuthorizedFusionDataset))
        or training_data.split != "train"
        or validation_data.split != "validation"
    ):
        raise ValueError("real training requires authorization-gated train and validation loaders")
    if (
        training_data.task_id != context.task_id
        or validation_data.task_id != context.task_id
        or training_data.authorization_id != context.authorization_id
        or validation_data.authorization_id != context.authorization_id
        or training_data.manifest_sha256 != context.release_manifest_sha256
        or validation_data.manifest_sha256 != context.release_manifest_sha256
        or training_data.target_manifest_sha256 != context.training_targets_manifest_sha256
        or validation_data.target_manifest_sha256 != context.training_targets_manifest_sha256
        or training_data.candidate_manifest_sha256 != context.candidate_manifest_sha256
        or validation_data.candidate_manifest_sha256 != context.candidate_manifest_sha256
    ):
        raise ValueError("training loaders do not match the authorized task release context")


def _sample_gpu_utilization() -> str:
    import subprocess
    import time

    now = time.monotonic()

    previous = getattr(_sample_gpu_utilization, "_cached", (0.0, "unavailable"))

    if now - previous[0] < 5.0:
        return previous[1]

    try:
        result = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            text=True,
            timeout=2,
        )

        value = result.strip().splitlines()[0] + "%"

    except (OSError, subprocess.SubprocessError, IndexError):
        value = "unavailable"

    setattr(  # noqa: B010
        _sample_gpu_utilization, "_cached", (now, value)
    )

    return value
