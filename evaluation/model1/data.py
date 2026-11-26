"""Authorization-gated, task-specific Model 1 data loading."""

import importlib
import random
from collections.abc import Mapping, Sequence
from functools import lru_cache, partial
from pathlib import Path
from typing import Any, Literal, cast

import torch
from PIL import Image, ImageOps
from torch import Tensor
from torch.utils.data import DataLoader, Dataset

from evaluation.data.contracts import Manifest, Registry, Sample
from evaluation.data.release_authorization import (
    AuthorizationRecord,
    require_training_authorization,
)
from evaluation.data.training_partition import approved_training
from evaluation.data.validation import validate
from evaluation.model1.models import TaskKind

DatasetSplit = Literal["train", "validation", "test"]


def require_active_source(dataset_id: str) -> None:
    """Phase 10J exclusions apply even when a caller supplies a historical registry."""
    if dataset_id.casefold() in {"heridal", "sard"}:
        raise ValueError("dataset excluded from active Model 1 scope")


class TaskDataConfig:
    def __init__(
        self,
        task: TaskKind,
        *,
        image_size: int = 224,
        batch_size: int = 8,
        workers: int = 0,
        horizontal_flip_probability: float = 0.0,
        mask_value_to_label: Mapping[int, str] | None = None,
    ) -> None:
        if image_size < 32 or batch_size < 1 or workers < 0:
            raise ValueError("invalid image size, batch size or worker count")
        if not 0 <= horizontal_flip_probability <= 1:
            raise ValueError("horizontal flip probability must be in [0, 1]")
        if task == "semantic_segmentation" and not mask_value_to_label:
            raise ValueError("segmentation requires a source-verified mask value mapping")
        self.task = task
        self.image_size = image_size
        self.batch_size = batch_size
        self.workers = workers
        self.horizontal_flip_probability = horizontal_flip_probability
        self.mask_value_to_label = dict(mask_value_to_label or {})


class AuthorizedTaskDataset(Dataset[tuple[Any, Any]]):
    """Only yields train or validation rows from a checksum-bound approved task release."""

    def __init__(
        self,
        registry: Registry,
        input_manifest: Manifest,
        target_manifest: Manifest,
        root: Path,
        config: TaskDataConfig,
        *,
        task_id: str,
        candidate_manifest_path: Path,
        authorization_records: tuple[AuthorizationRecord, ...],
        split: DatasetSplit = "train",
    ) -> None:
        if input_manifest.role != "operational" or target_manifest.role != "training_targets":
            raise ValueError("task data requires operational inputs and a training-target manifest")
        if (input_manifest.dataset_id, input_manifest.dataset_version) != (
            target_manifest.dataset_id,
            target_manifest.dataset_version,
        ):
            raise ValueError("task input and target dataset versions differ")
        require_active_source(input_manifest.dataset_id)
        auth = require_training_authorization(
            registry,
            input_manifest,
            task_id=task_id,
            candidate_manifest_paths={input_manifest.dataset_id: candidate_manifest_path},
            authorization_records=authorization_records,
            dataset_root=root,
            training_targets_manifest=target_manifest,
            required_scope="local_training" if split == "train" else "local_evaluation",
        )
        validate(registry, (input_manifest, target_manifest), root, verify_files=True)
        input_rows = {sample.sample_id: sample for sample in input_manifest.samples}
        target_rows = {sample.sample_id: sample for sample in target_manifest.samples}
        if input_rows.keys() != target_rows.keys():
            raise ValueError("task input and target sample identifiers differ")
        for sample_id, sample in input_rows.items():
            target = target_rows[sample_id]
            if (sample.split, sample.source_ref) != (target.split, target.source_ref):
                raise ValueError("task input and target lineage or partition differs")
            if target.annotation is None:
                raise ValueError("task target annotation is missing")
        if split == "train":
            approved = list(
                approved_training(
                    registry,
                    (input_manifest,),
                    root,
                    task_id=task_id,
                    candidate_manifest_paths={input_manifest.dataset_id: candidate_manifest_path},
                    authorization_records=authorization_records,
                    training_targets_manifest=target_manifest,
                )
            )
            rows = [sample for batch in approved for sample in batch]
        else:
            rows = [sample for sample in input_manifest.samples if sample.split == split]
        self._dataset = next(
            dataset
            for dataset in registry.datasets
            if (dataset.dataset_id, dataset.version)
            == (input_manifest.dataset_id, input_manifest.dataset_version)
        )
        self._inputs = input_rows
        self._targets = target_rows
        self._root = root.resolve()
        self._config = config
        self.normalization: tuple[Tensor, Tensor] | None = None
        self.task_id = task_id
        self.authorization_id = auth.authorization_id
        self.manifest_sha256 = auth.training_manifest_sha256
        self.target_manifest_sha256 = auth.training_targets_manifest_sha256
        self.candidate_manifest_sha256 = auth.candidate_manifest_sha256
        self.split = split
        self.augmentation_enabled = split == "train"
        self.rows = tuple(row for row in rows if row.split == split)
        if not self.rows:
            raise ValueError(f"authorized {split} partition is empty")
        self.labels = tuple(sorted(self._dataset.label_definitions))
        self.label_indices = {label: index for index, label in enumerate(self.labels)}
        if config.task == "object_detection":
            self.label_indices = {label: index + 1 for index, label in enumerate(self.labels)}
        if config.mask_value_to_label:
            unknown = set(config.mask_value_to_label.values()) - set(self.label_indices)
            if unknown:
                raise ValueError("mask mapping contains labels outside the registered taxonomy")
            if len(config.mask_value_to_label) < 2:
                raise ValueError("mask mapping must describe at least two source values")
        for sample in self.rows:
            self._validate_task_sample(sample, target_rows[sample.sample_id])
        self._sensor_values: Tensor | None = None
        self._sensor_available: Tensor | None = None
        self._normalized_sensor_values: Tensor | None = None
        self._sensor_targets: Tensor | None = None
        if config.task.startswith("sensor_"):
            sensor_windows = []
            source_indices: dict[Path, Mapping[int, Mapping[str, float]]] = {}
            for sample in self.rows:
                if sample.asset is None:
                    raise ValueError("sensor sample is missing an operational asset")
                source_path = self._asset_path(sample.asset.path)
                source_index = source_indices.get(source_path)
                if source_index is None:
                    source_index = _sensor_source_index(source_path)
                    source_indices[source_path] = source_index
                sensor_windows.append(_sensor_window_from_index(source_index, sample))
            self._sensor_values = torch.stack([window[0] for window in sensor_windows])
            self._sensor_available = torch.stack([window[1] for window in sensor_windows])
            if config.task == "sensor_regression":
                sensor_targets = []
                for sample in self.rows:
                    annotation = target_rows[sample.sample_id].annotation
                    if annotation is None:
                        raise ValueError("sensor regression sample is missing a target")
                    sensor_targets.append(annotation.numeric_targets)
                self._sensor_targets = torch.tensor(sensor_targets, dtype=torch.float32)

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> tuple[Any, Any]:
        x: Any
        y: Any
        sample = self.rows[index]
        target_sample = self._targets[sample.sample_id]
        if self._sensor_values is not None and self._sensor_available is not None:
            values = (
                self._normalized_sensor_values[index]
                if self._normalized_sensor_values is not None
                else self._sensor_values[index]
            )
            x = {"values": values, "available": self._sensor_available[index]}
            annotation = target_sample.annotation
            if annotation is None:
                raise ValueError("authorized sensor target is missing an annotation")
            y = (
                self._sensor_targets[index]
                if self._sensor_targets is not None
                else torch.tensor(self._class_index(annotation.labels[0]), dtype=torch.int64)
            )
        else:
            x, y = self._load_sample(sample, target_sample)
        if (
            self.augmentation_enabled
            and self._config.horizontal_flip_probability
            and torch.rand(()) < self._config.horizontal_flip_probability
            and self._config.task
            in {
                "image_classification",
                "thermal_classification",
                "object_detection",
                "semantic_segmentation",
            }
        ):
            x = x.flip(-1)
            if self._config.task == "object_detection":
                y["boxes"][:, [0, 2]] = self._config.image_size - y["boxes"][:, [2, 0]]
            elif self._config.task == "semantic_segmentation":
                y = y.flip(-1)
        if self.normalization is not None and self._normalized_sensor_values is None:
            mean, scale = self.normalization
            if isinstance(x, Tensor):
                x = (x - mean.reshape(-1, 1, 1)) / scale.reshape(-1, 1, 1)
            elif isinstance(x, dict):
                values, available = x["values"], x["available"]
                normalized = (values - mean) / scale
                x["values"] = torch.where(available, normalized, torch.zeros_like(normalized))
        return x, y

    def previous_sensor_measurement(self, index: int, measurement: str) -> float | None:
        if self._config.task != "sensor_regression" or not measurement.strip():
            raise ValueError("previous measurements require a named sensor-regression target")
        sample = self.rows[index]
        if sample.asset is None or not sample.source_rows:
            raise ValueError("sensor sample has no historical source row")
        source_index = _sensor_source_index(self._asset_path(sample.asset.path))
        source_row = source_index.get(sample.source_rows[-1])
        if source_row is None:
            raise ValueError("last historical sensor row is missing from the source index")
        return source_row.get(measurement)

    def set_normalization(self, mean: Tensor, scale: Tensor) -> None:
        if self.normalization is not None or mean.shape != scale.shape:
            raise ValueError("normalization is already set or statistics have different shapes")
        expected = (
            len(self.rows[0].sensor_feature_names)
            if self._config.task.startswith("sensor_")
            else 1
            if self._config.task in {"thermal_classification", "audio_classification"}
            else 3
        )
        if mean.shape != (expected,):
            raise ValueError("normalization channel count differs from the task input")
        if not torch.isfinite(mean).all() or not torch.isfinite(scale).all() or (scale <= 0).any():
            raise ValueError("normalization statistics must be finite with positive scale")
        self.normalization = (mean.detach().clone(), scale.detach().clone())
        if self._sensor_values is not None and self._sensor_available is not None:
            normalized = (self._sensor_values - mean) / scale
            self._normalized_sensor_values = torch.where(
                self._sensor_available, normalized, torch.zeros_like(normalized)
            )

    def _validate_task_sample(self, sample: Sample, target: Sample) -> None:
        ann = target.annotation
        if ann is None:
            raise ValueError("task target annotation is missing")
        if self._config.task in {
            "image_classification",
            "object_detection",
            "semantic_segmentation",
        }:
            if sample.modality != "image":
                raise ValueError("RGB task requires image input")
        elif self._config.task == "thermal_classification" and sample.modality != "thermal":
            raise ValueError("thermal classification requires thermal input")
        elif self._config.task == "audio_classification" and sample.modality != "audio":
            raise ValueError("audio classification requires audio input")
        elif self._config.task in {"sensor_classification", "sensor_regression"} and (
            sample.modality != "environment"
            or not sample.source_rows
            or not sample.sensor_feature_names
            or sample.prediction_horizon is None
        ):
            raise ValueError("sensor task requires explicit rows, features and horizon metadata")
        if (
            self._config.task
            in {
                "image_classification",
                "thermal_classification",
                "audio_classification",
                "sensor_classification",
            }
            and len(ann.labels) != 1
        ):
            raise ValueError("classification requires exactly one registered target label")
        if self._config.task == "object_detection" and (
            not ann.boxes or len(ann.box_labels) != len(ann.boxes)
        ):
            raise ValueError("detection requires a source-verified class for every box")
        if self._config.task == "semantic_segmentation" and ann.format != "mask":
            raise ValueError("segmentation requires a mask annotation")
        if self._config.task == "sensor_regression" and len(ann.numeric_targets) != 1:
            raise ValueError("sensor regression requires exactly one numeric target")
        if ann.format == "mask" and sample.dimensions != target.dimensions:
            raise ValueError("segmentation input and mask dimensions differ")

    def _load_sample(self, sample: Sample, target: Sample) -> tuple[Any, Any]:
        annotation = target.annotation
        if sample.asset is None or annotation is None:
            raise ValueError("authorized physical sample is missing an asset or annotation")
        image_path = self._asset_path(sample.asset.path)
        target_path = self._asset_path(annotation.asset.path)
        task = self._config.task
        if task in {"image_classification", "thermal_classification"}:
            mode = "L" if task == "thermal_classification" else "RGB"
            x = _image_tensor(image_path, mode, (self._config.image_size, self._config.image_size))
            return x, self._class_index(annotation.labels[0])
        if task == "audio_classification":
            result = importlib.import_module("evaluation.data.preprocessing").audio(image_path)
            x = torch.from_numpy(result["log_mel"].copy()).to(torch.float32).unsqueeze(0)
            return x, self._class_index(annotation.labels[0])
        if task == "object_detection":
            x = _image_tensor(image_path, "RGB", (self._config.image_size, self._config.image_size))
            width, height = sample.dimensions or (0, 0)
            if width <= 0 or height <= 0:
                raise ValueError("detection requires source image dimensions")
            sx, sy = self._config.image_size / width, self._config.image_size / height
            boxes = [
                (x0 * sx, y0 * sy, (x0 + box_width) * sx, (y0 + box_height) * sy)
                for x0, y0, box_width, box_height in annotation.boxes
            ]
            labels = [self._class_index(label) for label in annotation.box_labels]
            return x, {
                "boxes": torch.tensor(boxes, dtype=torch.float32).reshape(-1, 4),
                "labels": torch.tensor(labels, dtype=torch.int64),
            }
        if task == "semantic_segmentation":
            x = _image_tensor(image_path, "RGB", (self._config.image_size, self._config.image_size))
            mask = _mask_tensor(
                target_path,
                (self._config.image_size, self._config.image_size),
                self._config.mask_value_to_label,
                self.label_indices,
            )
            return x, mask
        if task in {"sensor_classification", "sensor_regression"}:
            values, available = _sensor_window(image_path, sample)
            y: Any = (
                self._class_index(annotation.labels[0])
                if task == "sensor_classification"
                else torch.tensor(annotation.numeric_targets, dtype=torch.float32)
            )
            if task == "sensor_classification":
                y = torch.tensor(y, dtype=torch.int64)
            return {"values": values, "available": available}, y
        raise ValueError(f"unsupported task: {task}")

    def _asset_path(self, reference: str) -> Path:
        path = (self._root / reference).resolve()
        if not path.is_relative_to(self._root) or not path.is_file():
            raise ValueError("authorized asset is missing or escapes the dataset root")
        return path

    def _class_index(self, label: str) -> int:
        if label not in self.label_indices:
            raise ValueError(f"target label is outside the authorized source taxonomy: {label}")
        return self.label_indices[label]


class AuthorizedFusionDataset(Dataset[tuple[Any, Tensor]]):
    """Loads only explicit RGB/thermal pairs; unrelated records are never aligned by proximity."""

    def __init__(
        self,
        registry: Registry,
        input_manifest: Manifest,
        target_manifest: Manifest,
        root: Path,
        *,
        task_id: str,
        candidate_manifest_path: Path,
        authorization_records: tuple[AuthorizationRecord, ...],
        split: DatasetSplit = "train",
        image_size: int = 224,
        batch_size: int = 8,
        workers: int = 0,
        modality_dropout_probability: float = 0.0,
    ) -> None:
        if image_size < 32 or batch_size < 1 or workers < 0:
            raise ValueError("invalid fusion image size, batch size or worker count")
        if not 0 <= modality_dropout_probability < 1:
            raise ValueError("modality dropout probability must be in [0, 1)")
        require_active_source(input_manifest.dataset_id)
        authorization = require_training_authorization(
            registry,
            input_manifest,
            task_id=task_id,
            candidate_manifest_paths={input_manifest.dataset_id: candidate_manifest_path},
            authorization_records=authorization_records,
            dataset_root=root,
            training_targets_manifest=target_manifest,
            required_scope="local_training" if split == "train" else "local_evaluation",
        )
        validate(registry, (input_manifest, target_manifest), root, verify_files=True)
        input_by_id = {sample.sample_id: sample for sample in input_manifest.samples}
        target_by_id = {sample.sample_id: sample for sample in target_manifest.samples}
        if input_by_id.keys() != target_by_id.keys():
            raise ValueError("fusion input and target sample identifiers differ")
        pairs: dict[str, dict[str, Sample]] = {}
        for sample in input_manifest.samples:
            if sample.pair_id is None or sample.modality not in {"image", "thermal"}:
                raise ValueError("fusion requires explicit RGB/thermal pair identifiers")
            pair = pairs.setdefault(sample.pair_id, {})
            if sample.modality in pair:
                raise ValueError("fusion pair contains duplicate modalities")
            pair[sample.modality] = sample
        if not pairs or any(set(pair) != {"image", "thermal"} for pair in pairs.values()):
            raise ValueError("each fusion pair requires exactly one RGB and one thermal sample")
        dataset_info = next(
            dataset
            for dataset in registry.datasets
            if (dataset.dataset_id, dataset.version)
            == (input_manifest.dataset_id, input_manifest.dataset_version)
        )
        labels = tuple(sorted(dataset_info.label_definitions))
        self.label_indices = {label: index for index, label in enumerate(labels)}
        self.rows: list[tuple[Sample, Sample, Sample]] = []
        for pair in pairs.values():
            rgb, thermal = pair["image"], pair["thermal"]
            if (rgb.split, rgb.source_ref) != (thermal.split, thermal.source_ref):
                raise ValueError(
                    "fusion modalities do not share an authorized partition and source"
                )
            for sample in (rgb, thermal):
                target = target_by_id[sample.sample_id]
                if target.split != sample.split or target.annotation is None:
                    raise ValueError("fusion target lineage or annotation is missing")
                if len(target.annotation.labels) != 1:
                    raise ValueError("fusion classification requires one target label per modality")
            rgb_annotation = target_by_id[rgb.sample_id].annotation
            thermal_annotation = target_by_id[thermal.sample_id].annotation
            if rgb_annotation is None or thermal_annotation is None:
                raise ValueError("fusion target annotation is missing")
            if rgb_annotation.labels != thermal_annotation.labels:
                raise ValueError("paired modalities have conflicting targets")
            self.rows.append((rgb, thermal, target_by_id[rgb.sample_id]))
        if split == "train":
            allowed = {
                sample.sample_id
                for batch in approved_training(
                    registry,
                    (input_manifest,),
                    root,
                    task_id=task_id,
                    candidate_manifest_paths={input_manifest.dataset_id: candidate_manifest_path},
                    authorization_records=authorization_records,
                    training_targets_manifest=target_manifest,
                )
                for sample in batch
            }
        else:
            allowed = {
                sample.sample_id
                for sample in input_manifest.samples
                if sample.split == "validation"
            }
        self.rows = [
            row
            for row in self.rows
            if row[0].split == split and row[1].split == split and row[0].sample_id in allowed
        ]
        if not self.rows:
            raise ValueError(f"authorized {split} fusion partition is empty")
        self.root = root.resolve()
        self.image_size = image_size
        self.batch_size = batch_size
        self.workers = workers
        self.task_id = task_id
        self.authorization_id = authorization.authorization_id
        self.manifest_sha256 = authorization.training_manifest_sha256
        self.target_manifest_sha256 = authorization.training_targets_manifest_sha256
        self.candidate_manifest_sha256 = authorization.candidate_manifest_sha256
        self.split = split
        self.modality_dropout_probability = (
            modality_dropout_probability if split == "train" else 0.0
        )
        self.normalization: dict[str, tuple[Tensor, Tensor]] | None = None

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> tuple[Any, Tensor]:
        rgb, thermal, target = self.rows[index]
        if rgb.asset is None or thermal.asset is None or target.annotation is None:
            raise ValueError("fusion release is missing a source or target asset")
        values = {
            "image": _image_tensor(
                _safe_asset(self.root, rgb.asset.path),
                "RGB",
                (self.image_size, self.image_size),
            ),
            "thermal": _image_tensor(
                _safe_asset(self.root, thermal.asset.path),
                "L",
                (self.image_size, self.image_size),
            ),
        }
        if self.normalization is not None:
            values = {
                name: (value - mean.reshape(-1, 1, 1)) / scale.reshape(-1, 1, 1)
                for name, value in values.items()
                for mean, scale in (self.normalization[name],)
            }
        available = {name: True for name in values}
        for name in values:
            if random.random() < self.modality_dropout_probability:
                available[name] = False
        if not any(available.values()):
            available[random.choice(tuple(available))] = True
        annotation = target.annotation
        label = annotation.labels[0]
        if label not in self.label_indices:
            raise ValueError("fusion target label is outside the registered taxonomy")
        return {
            "values": values,
            "available": {
                name: torch.tensor(flag, dtype=torch.bool) for name, flag in available.items()
            },
        }, torch.tensor(self.label_indices[label], dtype=torch.int64)

    def set_normalization(self, values: Mapping[str, tuple[Tensor, Tensor]]) -> None:
        if self.normalization is not None or set(values) != {"image", "thermal"}:
            raise ValueError("fusion normalization must define each modality exactly once")
        for name, channels in (("image", 3), ("thermal", 1)):
            mean, scale = values[name]
            if (
                mean.shape != (channels,)
                or scale.shape != (channels,)
                or not torch.isfinite(mean).all()
                or not torch.isfinite(scale).all()
                or (scale <= 0).any()
            ):
                raise ValueError("fusion normalization statistics are invalid")
        self.normalization = {
            name: (mean.detach().clone(), scale.detach().clone())
            for name, (mean, scale) in values.items()
        }


def build_task_dataloader(
    dataset: AuthorizedTaskDataset | AuthorizedFusionDataset,
    *,
    seed: int,
    device: torch.device,
) -> DataLoader[Any]:
    generator = torch.Generator()
    generator.manual_seed(seed)
    if isinstance(dataset, AuthorizedTaskDataset):
        detection = dataset._config.task == "object_detection"
        sensor = dataset._config.task.startswith("sensor_")
        batch_size = dataset._config.batch_size
        workers = dataset._config.workers
    else:
        detection = False
        sensor = False
        batch_size = dataset.batch_size
        workers = dataset.workers
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=dataset.split == "train",
        num_workers=workers,
        pin_memory=device.type == "cuda",
        worker_init_fn=_seed_worker,
        generator=generator,
        collate_fn=partial(
            _collate_task,
            detection=detection,
            sensor=sensor,
            fusion=isinstance(dataset, AuthorizedFusionDataset),
        ),
    )


def fit_training_channel_stats(dataset: AuthorizedTaskDataset) -> tuple[Tensor, Tensor]:
    if dataset.split != "train":
        raise ValueError("normalization statistics may only be fitted on training samples")
    if dataset.normalization is not None:
        raise ValueError("fit normalization before applying it to the training dataset")
    augmentation = dataset.augmentation_enabled
    dataset.augmentation_enabled = False
    try:
        return _fit_channel_stream(dataset[index][0] for index in range(len(dataset)))
    finally:
        dataset.augmentation_enabled = augmentation


def fit_fusion_channel_stats(
    dataset: AuthorizedFusionDataset,
) -> dict[str, tuple[Tensor, Tensor]]:
    if dataset.split != "train" or dataset.normalization is not None:
        raise ValueError("fusion statistics require an unnormalized training partition")
    dropout = dataset.modality_dropout_probability
    dataset.modality_dropout_probability = 0.0
    try:
        return {
            name: _fit_channel_stream(
                dataset[index][0]["values"][name] for index in range(len(dataset))
            )
            for name in ("image", "thermal")
        }
    finally:
        dataset.modality_dropout_probability = dropout


def _fit_channel_stream(features: Any) -> tuple[Tensor, Tensor]:
    count = 0
    mean: Tensor | None = None
    squared: Tensor | None = None
    for feature in features:
        if not isinstance(feature, Tensor) or feature.ndim != 3:
            raise ValueError("channel statistics require [channels,height,width] tensors")
        flattened = feature.to(torch.float64).reshape(feature.shape[0], -1)
        batch_mean = flattened.mean(dim=1)
        batch_squared = (flattened - batch_mean[:, None]).square().sum(dim=1)
        if mean is None:
            mean = torch.zeros_like(batch_mean)
            squared = torch.zeros_like(batch_squared)
        if mean is None or squared is None or mean.shape != batch_mean.shape:
            raise ValueError("input modality or channel count changed while fitting statistics")
        batch_count = flattened.shape[1]
        old_count = count
        count += batch_count
        delta = batch_mean - mean
        mean += delta * (batch_count / count)
        squared += batch_squared + delta.square() * (old_count * batch_count / count)
    if mean is None or squared is None or count == 0:
        raise ValueError("training partition contains no features")
    scale = (squared / count).sqrt().clamp_min(1.0e-8)
    return mean.to(torch.float32), scale.to(torch.float32)


def fit_sensor_normalization(dataset: AuthorizedTaskDataset) -> tuple[Tensor, Tensor]:
    if dataset.split != "train" or not dataset._config.task.startswith("sensor_"):
        raise ValueError("sensor normalization requires an authorized sensor training partition")
    if dataset.normalization is not None:
        raise ValueError("fit normalization before applying it to the training dataset")
    feature_count = len(dataset.rows[0].sensor_feature_names)
    sums = torch.zeros(feature_count, dtype=torch.float64)
    sums_squared = torch.zeros_like(sums)
    counts = torch.zeros(feature_count, dtype=torch.int64)
    for index in range(len(dataset)):
        features, _ = dataset[index]
        if not isinstance(features, dict):
            raise TypeError("sensor loader did not return typed values and availability")
        values = features["values"].to(torch.float64)
        available = features["available"]
        sums += torch.where(available, values, torch.zeros_like(values)).sum(dim=0)
        sums_squared += torch.where(available, values.square(), torch.zeros_like(values)).sum(dim=0)
        counts += available.sum(dim=0)
    if (counts == 0).any():
        raise ValueError("cannot normalize a sensor feature with no training measurements")
    mean = sums / counts
    variance = (sums_squared / counts) - mean.square()
    scale = variance.clamp_min(1.0e-16).sqrt()
    return mean.to(torch.float32), scale.to(torch.float32)


def _image_tensor(path: Path, mode: str, size: tuple[int, int]) -> Tensor:
    with Image.open(path) as source:
        image = (
            ImageOps.exif_transpose(source).convert(mode).resize(size, Image.Resampling.BILINEAR)
        )
        channels = 1 if mode == "L" else 3
        raw = bytearray(image.tobytes())
    return (
        torch.frombuffer(raw, dtype=torch.uint8)
        .reshape(size[1], size[0], channels)
        .permute(2, 0, 1)
        .to(torch.float32)
        .div_(255.0)
    )


def _mask_tensor(
    path: Path,
    size: tuple[int, int],
    value_to_label: Mapping[int, str],
    label_indices: Mapping[str, int],
) -> Tensor:
    with Image.open(path) as source:
        mask = source.resize(size, Image.Resampling.NEAREST)
        values = torch.tensor(list(mask.getdata()), dtype=torch.int64).reshape(size[1], size[0])
    output = torch.full_like(values, fill_value=255)
    for value, label in value_to_label.items():
        output[values == value] = label_indices[label]
    if (output == 255).any():
        raise ValueError("mask contains pixel values without source-verified class mappings")
    return output


def _sensor_window(path: Path, sample: Sample) -> tuple[Tensor, Tensor]:
    return _sensor_window_from_index(_sensor_source_index(path), sample)


def _sensor_window_from_index(
    rows_by_line: Mapping[int, Mapping[str, float]], sample: Sample
) -> tuple[Tensor, Tensor]:
    selected_rows = set(sample.source_rows)
    rows_seen = selected_rows.intersection(rows_by_line)
    if rows_seen != selected_rows:
        raise ValueError("sensor window source rows are missing")
    values: list[list[float]] = []
    available: list[list[bool]] = []
    for line in sample.source_rows:
        row = rows_by_line.get(line, {})
        values.append([row.get(name, 0.0) for name in sample.sensor_feature_names])
        available.append([name in row for name in sample.sensor_feature_names])
    return torch.tensor(values, dtype=torch.float32), torch.tensor(available, dtype=torch.bool)


def _sensor_source_index(path: Path) -> Mapping[int, Mapping[str, float]]:
    source = path.resolve()
    stat = source.stat()
    return _cached_sensor_source_index(str(source), stat.st_size, stat.st_mtime_ns)


@lru_cache(maxsize=4)
def _cached_sensor_source_index(
    path: str, size: int, modified_ns: int
) -> Mapping[int, Mapping[str, float]]:
    del size, modified_ns
    result: dict[int, dict[str, float]] = {}
    source_rows = importlib.import_module("evaluation.data.preprocessing").sensor_rows(Path(path))
    for row in source_rows:
        line = int(row["line"])
        measurements = result.setdefault(line, {})
        value = row["standardized"]
        if value is not None:
            measurements[str(row["measurement"])] = float(value)
    return result


def _collate_task(
    batch: Sequence[tuple[Any, Any]], *, detection: bool, sensor: bool, fusion: bool
) -> tuple[Any, Any]:
    features, targets = zip(*batch, strict=True)
    if detection:
        return list(features), list(targets)
    if sensor:
        sensor_features = cast(Sequence[Mapping[str, Tensor]], features)
        return {
            name: torch.stack([row[name] for row in sensor_features])
            for name in ("values", "available")
        }, torch.stack(list(cast(Sequence[Tensor], targets)))
    if fusion:
        fusion_features = cast(Sequence[Mapping[str, Any]], features)
        values = {
            modality: torch.stack([row["values"][modality] for row in fusion_features])
            for modality in ("image", "thermal")
        }
        availability = {
            modality: torch.stack([row["available"][modality] for row in fusion_features])
            for modality in ("image", "thermal")
        }
        return {"values": values, "available": availability}, torch.stack(
            list(cast(Sequence[Tensor], targets))
        )
    return cast(tuple[Any, Any], torch.utils.data.default_collate(list(batch)))


def _seed_worker(worker_id: int) -> None:
    seed = torch.initial_seed() % (2**32)
    random.seed(seed + worker_id)
    if importlib.util.find_spec("numpy") is not None:
        import numpy as np

        np.random.seed(seed + worker_id)


def _safe_asset(root: Path, reference: str) -> Path:
    path = (root / reference).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("authorized asset is missing or escapes the dataset root")
    return path
