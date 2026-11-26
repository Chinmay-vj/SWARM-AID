"""Randomly initialized Model 1 task models; no pretrained weights are loaded."""

from typing import Literal, cast

import torch
from torch import Tensor, nn

from agents.shared.domain import Record
from evaluation.model1.vision import (
    deeplabv3_mobilenet_v3_large,
    fasterrcnn_mobilenet_v3_large_fpn,
    mobilenet_v3_small,
)

TaskKind = Literal[
    "image_classification",
    "thermal_classification",
    "object_detection",
    "semantic_segmentation",
    "audio_classification",
    "sensor_classification",
    "sensor_regression",
]


class ModelConfig(Record):
    task: TaskKind
    num_classes: int
    input_channels: int = 3
    sensor_features: int = 1
    hidden_dim: int = 128
    dropout: float = 0.1
    image_size: int = 224


class AudioClassifier(nn.Module):
    def __init__(self, num_classes: int, dropout: float = 0.1) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(1, 32, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(32),
            nn.SiLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(32, 64, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(64),
            nn.SiLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(64, 128, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(128),
            nn.SiLU(),
            nn.AdaptiveAvgPool2d(1),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(), nn.Dropout(dropout), nn.Linear(128, num_classes)
        )

    def forward(self, log_mel: Tensor) -> Tensor:
        if log_mel.ndim != 4 or log_mel.shape[1] != 1:
            raise ValueError("audio input must have shape [batch, 1, time, mel_bins]")
        return cast(Tensor, self.classifier(self.features(log_mel)))


class SensorSequenceModel(nn.Module):
    """GRU with explicit per-value availability; all-missing rows are abstentions."""

    def __init__(
        self, feature_count: int, output_count: int, hidden_dim: int = 128, dropout: float = 0.1
    ) -> None:
        super().__init__()
        self.feature_count = feature_count
        self.encoder = nn.GRU(
            input_size=feature_count * 2,
            hidden_size=hidden_dim,
            batch_first=True,
        )
        self.dropout = nn.Dropout(dropout)
        self.head = nn.Linear(hidden_dim, output_count)

    def forward(self, values: Tensor, available: Tensor) -> tuple[Tensor, Tensor]:
        if values.ndim != 3 or available.shape != values.shape:
            raise ValueError(
                "sensor values and availability must have matching [batch,time,feature] shapes"
            )
        if values.shape[2] != self.feature_count or available.dtype != torch.bool:
            raise ValueError("sensor feature count or availability dtype mismatch")
        cleaned = torch.where(available, values, torch.zeros_like(values))
        encoded, _ = self.encoder(torch.cat((cleaned, available.to(values.dtype)), dim=2))
        valid = available.any(dim=(1, 2))
        logits = self.head(self.dropout(encoded[:, -1]))
        return logits, valid


class MissingAwareFusion(nn.Module):
    """Attention fusion that returns a validity mask and zeros for all-missing inputs."""

    def __init__(self, input_dimensions: dict[str, int], hidden_dim: int = 128) -> None:
        super().__init__()
        if not input_dimensions or any(
            not name or size < 1 for name, size in input_dimensions.items()
        ):
            raise ValueError("fusion requires named modalities with positive feature sizes")
        self.modalities = tuple(sorted(input_dimensions))
        self.projections = nn.ModuleDict(
            {name: nn.Linear(input_dimensions[name], hidden_dim) for name in self.modalities}
        )
        self.scorers = nn.ModuleDict({name: nn.Linear(hidden_dim, 1) for name in self.modalities})

    def forward(
        self, values: dict[str, Tensor], available: dict[str, Tensor]
    ) -> tuple[Tensor, Tensor]:
        if set(values) != set(self.modalities) or set(available) != set(self.modalities):
            raise ValueError("fusion inputs must contain the configured modalities exactly")
        projected: list[Tensor] = []
        scores: list[Tensor] = []
        masks: list[Tensor] = []
        for name in self.modalities:
            value = values[name]
            mask = available[name]
            if value.ndim != 2 or mask.shape != value.shape[:1] or mask.dtype != torch.bool:
                raise ValueError(
                    "each modality requires [batch,features] values and a boolean mask"
                )
            projected.append(torch.tanh(self.projections[name](value)))
            scores.append(self.scorers[name](projected[-1]).squeeze(-1))
            masks.append(mask)
        states = torch.stack(projected, dim=1)
        mask_stack = torch.stack(masks, dim=1)
        score_stack = torch.stack(scores, dim=1).masked_fill(~mask_stack, -1.0e9)
        valid = mask_stack.any(dim=1)
        weights = torch.softmax(score_stack, dim=1) * mask_stack.to(states.dtype)
        weights = weights / weights.sum(dim=1, keepdim=True).clamp_min(1.0e-12)
        fused = (states * weights.unsqueeze(-1)).sum(dim=1)
        return torch.where(valid.unsqueeze(-1), fused, torch.zeros_like(fused)), valid


class MultimodalFusionClassifier(nn.Module):
    """Encodes explicitly paired modalities before learned missingness-aware fusion."""

    def __init__(
        self,
        encoders: dict[str, nn.Module],
        feature_dimensions: dict[str, int],
        num_classes: int,
        hidden_dim: int = 128,
    ) -> None:
        super().__init__()
        if set(encoders) != set(feature_dimensions) or num_classes < 1:
            raise ValueError("fusion encoders and feature dimensions must match")
        self.encoders = nn.ModuleDict(encoders)
        self.fusion = MissingAwareFusion(feature_dimensions, hidden_dim)
        self.classifier = nn.Linear(hidden_dim, num_classes)

    def forward(
        self, values: dict[str, Tensor], available: dict[str, Tensor]
    ) -> tuple[Tensor, Tensor]:
        if set(values) != set(self.encoders):
            raise ValueError("fusion input modalities differ from configured encoders")
        features: dict[str, Tensor] = {}
        for name, encoder in self.encoders.items():
            output = encoder(values[name])
            if not isinstance(output, Tensor) or output.ndim != 2:
                raise ValueError("each modality encoder must return [batch,features]")
            features[name] = output
        fused, valid = self.fusion(features, available)
        return self.classifier(fused), valid


class MobileNetFeatureEncoder(nn.Module):
    def __init__(self, input_channels: int = 3) -> None:
        super().__init__()
        if input_channels not in {1, 3}:
            raise ValueError("MobileNet feature encoder supports one or three channels")
        model = mobilenet_v3_small()
        if input_channels == 1:
            stem = cast(nn.Sequential, model.features[0])
            first = stem[0]
            if not isinstance(first, nn.Conv2d):
                raise RuntimeError("unexpected TorchVision MobileNet stem")
            stem[0] = nn.Conv2d(
                1,
                first.out_channels,
                kernel_size=3,
                stride=2,
                padding=1,
                bias=False,
            )
        self.features = model.features
        self.pool = model.avgpool
        self.projection = nn.Sequential(*list(model.classifier.children())[:-1])
        self.output_dim = cast(nn.Linear, model.classifier[-1]).in_features

    def forward(self, image: Tensor) -> Tensor:
        features = cast(Tensor, self.pool(self.features(image)))
        return cast(Tensor, self.projection(torch.flatten(features, 1)))


def build_model(config: ModelConfig) -> nn.Module:
    if config.num_classes < 1 or config.hidden_dim < 1 or config.image_size < 32:
        raise ValueError("invalid model dimensions")
    if not 0 <= config.dropout < 1:
        raise ValueError("dropout must be in [0, 1)")
    if config.task == "audio_classification":
        return AudioClassifier(config.num_classes, config.dropout)
    if config.task in {"sensor_classification", "sensor_regression"}:
        return SensorSequenceModel(
            config.sensor_features,
            config.num_classes,
            config.hidden_dim,
            config.dropout,
        )
    if config.task == "object_detection":
        if config.num_classes < 2:
            raise ValueError("detection requires background plus at least one foreground class")
        return fasterrcnn_mobilenet_v3_large_fpn(
            num_classes=config.num_classes,
            min_size=config.image_size,
            max_size=config.image_size,
        )
    if config.task == "semantic_segmentation":
        return deeplabv3_mobilenet_v3_large(num_classes=config.num_classes)
    if config.task in {"image_classification", "thermal_classification"}:
        channels = 1 if config.task == "thermal_classification" else config.input_channels
        if channels not in {1, 3}:
            raise ValueError("visual classification supports one or three input channels")
        model = mobilenet_v3_small()
        if channels != 3:
            stem = cast(nn.Sequential, model.features[0])
            first = stem[0]
            if not isinstance(first, nn.Conv2d):
                raise RuntimeError("unexpected TorchVision MobileNet stem")
            stem[0] = nn.Conv2d(
                channels,
                first.out_channels,
                kernel_size=3,
                stride=2,
                padding=1,
                bias=False,
            )
        last = cast(nn.Linear, model.classifier[-1])
        model.classifier[-1] = nn.Linear(last.in_features, config.num_classes)
        return model
    raise ValueError(f"unsupported task: {config.task}")
