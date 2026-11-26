"""Reusable task adapters and bounded training/evaluation loops."""

import copy
import importlib.util
import random
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
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
from evaluation.model1.metrics import (
    classification_metrics,
    detection_metrics,
    expected_calibration_error,
    regression_metrics,
    segmentation_metrics,
)


class TrainingConfig(Record):
    epochs: int = Field(default=30, ge=1)
    learning_rate: float = Field(default=0.001, gt=0)
    weight_decay: float = Field(default=0.0001, ge=0)
    gradient_accumulation: int = Field(default=1, ge=1)
    early_stopping_patience: int = Field(default=5, ge=1)
    gradient_clip_norm: float = Field(default=1.0, gt=0)
    mixed_precision: bool = False
    amp_dtype: Literal["float16", "bfloat16"] = "bfloat16"
    seed: int = Field(default=42, ge=0)
    device: str = "cpu"
    batch_size: int = Field(default=8, ge=1)
    workers: int = Field(default=0, ge=0)
    image_size: int = Field(default=224, ge=32)
    max_gpu_memory_gb: float = Field(default=24, gt=0)
    checkpoint_root: Path = Path(r"D:\SWARM-AID-DATA\checkpoints")
    profile_output_root: Path = Path(r"D:\SWARM-AID-DATA\runs\phase11")


class TrainingContext(Record):
    artifact_kind: Literal["synthetic_fixture", "authorized_training"]
    task_id: str = Field(min_length=1)
    release_manifest_sha256: Digest
    authorization_id: str | None = None
    candidate_manifest_sha256: Digest | None = None
    training_targets_manifest_sha256: Digest | None = None

    @model_validator(mode="after")
    def gate_real_training(self) -> "TrainingContext":
        if self.artifact_kind == "authorized_training" and (
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
    def __init__(self, ignore_index: int = 255) -> None:
        self.ignore_index = ignore_index
        self.criterion = nn.CrossEntropyLoss(ignore_index=ignore_index)

    def loss(self, model: nn.Module, features: Tensor, targets: Tensor) -> Tensor:
        return cast(Tensor, self.criterion(_segmentation_output(model(features)), targets))

    def predict(self, model: nn.Module, features: Tensor) -> Tensor:
        return _segmentation_output(model(features)).detach()

    def metrics(self, predictions: Tensor, targets: Tensor) -> dict[str, float]:
        return segmentation_metrics(
            predictions, targets, predictions.shape[1], ignore_index=self.ignore_index
        )

    def selection_score(self, metrics: Mapping[str, float]) -> tuple[float, Literal["min", "max"]]:
        return metrics["macro_iou"], "max"


class DetectionTask:
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
        return detection_metrics(predictions, targets)

    def selection_score(self, metrics: Mapping[str, float]) -> tuple[float, Literal["min", "max"]]:
        return metrics["map50"], "max"


class RegressionTask:
    def loss(self, model: nn.Module, features: Any, targets: Tensor) -> Tensor:
        predictions, valid = _regression_output(model, features)
        if valid is not None:
            predictions, targets = predictions[valid], targets[valid]
        if not len(targets):
            raise ValueError("regression batch has no available sensor evidence")
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
) -> TrainingResult:
    _validate_training_sources(train_batches, validation_batches, context)
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
    for epoch in range(1, config.epochs + 1):
        model.train()
        optimizer.zero_grad(set_to_none=True)
        total_loss = 0.0
        batch_count = 0
        pending = 0
        for batch_index, ((features, targets), is_last_batch) in enumerate(
            _with_last(train_batches)
        ):
            features = _to_device(features, device)
            targets = _to_device(targets, device)
            with _autocast(device, config):
                loss = adapter.loss(model, features, targets)
            if not torch.isfinite(loss):
                raise ValueError("nonfinite training loss")
            torch.autograd.backward(scaler.scale(loss / config.gradient_accumulation))
            total_loss += float(loss.detach())
            batch_count += 1
            pending += 1
            if pending == config.gradient_accumulation or is_last_batch:
                scaler.unscale_(optimizer)
                if pending < config.gradient_accumulation:
                    correction = config.gradient_accumulation / pending
                    for parameter in model.parameters():
                        if parameter.grad is not None:
                            parameter.grad.mul_(correction)
                torch.nn.utils.clip_grad_norm_(model.parameters(), config.gradient_clip_norm)
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad(set_to_none=True)
                global_step += 1
                pending = 0
        if batch_count == 0:
            raise ValueError("training loader is empty")
        model.eval()
        predictions: list[Any] = []
        expected: list[Any] = []
        with torch.inference_mode():
            for features, targets in validation_batches:
                features = _to_device(features, device)
                predictions.append(adapter.predict(model, features))
                expected.append(_to_device(targets, device))
        if not predictions:
            raise ValueError("validation loader is empty")
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
                total_loss / batch_count,
                score,
                validation_metrics,
                global_step,
                best_epoch,
            )
        )
        if stale_epochs >= config.early_stopping_patience:
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
) -> Iterable[tuple[tuple[Any, Any], bool]]:
    iterator = iter(batches)
    try:
        current = next(iterator)
    except StopIteration:
        return
    for following in iterator:
        yield current, False
        current = following
    yield current, True


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
