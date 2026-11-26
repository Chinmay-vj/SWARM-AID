"""Typed boundaries around the optional TorchVision Python package."""

import importlib
from collections.abc import Callable
from typing import cast

from torch import Tensor, nn


class MobileNetV3Small(nn.Module):
    features: nn.Sequential
    avgpool: nn.Module
    classifier: nn.Sequential


def mobilenet_v3_small() -> MobileNetV3Small:
    constructor = cast(
        Callable[..., nn.Module],
        vars(importlib.import_module("torchvision.models"))["mobilenet_v3_small"],
    )
    return cast(MobileNetV3Small, constructor(weights=None))


def fasterrcnn_mobilenet_v3_large_fpn(
    *, num_classes: int, min_size: int, max_size: int
) -> nn.Module:
    constructor = cast(
        Callable[..., nn.Module],
        vars(importlib.import_module("torchvision.models.detection"))[
            "fasterrcnn_mobilenet_v3_large_fpn"
        ],
    )
    return constructor(
        weights=None,
        weights_backbone=None,
        num_classes=num_classes,
        min_size=min_size,
        max_size=max_size,
    )


def deeplabv3_mobilenet_v3_large(*, num_classes: int) -> nn.Module:
    constructor = cast(
        Callable[..., nn.Module],
        vars(importlib.import_module("torchvision.models.segmentation"))[
            "deeplabv3_mobilenet_v3_large"
        ],
    )
    return constructor(weights=None, weights_backbone=None, num_classes=num_classes, aux_loss=False)


def nms(boxes: Tensor, scores: Tensor, threshold: float) -> Tensor:
    operation = cast(
        Callable[[Tensor, Tensor, float], Tensor],
        vars(importlib.import_module("torchvision.ops"))["nms"],
    )
    return operation(boxes, scores, threshold)
