"""Explicit CE/Dice objective and bounded, dataset-level segmentation validation."""

import math

import torch
from torch import Tensor


def segmentation_terms(
    logits: Tensor, targets: Tensor, ignore_index: int
) -> tuple[Tensor, Tensor, Tensor, Tensor]:
    if logits.ndim != 4 or targets.shape != (logits.shape[0], *logits.shape[2:]):
        raise ValueError("segmentation logits and target shapes differ")
    classes = logits.shape[1]
    valid = targets != ignore_index
    selected = targets[valid]
    if selected.numel() and (selected.min() < 0 or selected.max() >= classes):
        raise ValueError("segmentation target outside taxonomy")
    safe = targets.masked_fill(~valid, 0)
    log_probabilities = logits.float().log_softmax(1)
    probabilities = log_probabilities.exp() * valid[:, None]
    predicted_mass = probabilities.sum((0, 2, 3))
    target_mass = torch.bincount(selected, minlength=classes).float()
    intersection = torch.zeros(classes, device=logits.device).scatter_add(
        0, safe.reshape(-1), probabilities.gather(1, safe[:, None]).reshape(-1)
    )
    # Avoid CUDA NLL's nondeterministic reduction; preserve FP32 pixel counts
    # even when logits use BF16. Ignored targets are never gathered out of range.
    ce = -(log_probabilities.gather(1, safe[:, None]).squeeze(1) * valid).sum()
    return ce, predicted_mass, target_mass, intersection


def segmentation_loss(
    logits: Tensor, targets: Tensor, ignore_index: int, dice_weight: float
) -> Tensor:
    ce, predicted, expected, intersection = segmentation_terms(logits, targets, ignore_index)
    present = expected > 0
    if not present.any():
        return logits.sum() * 0
    dice = (
        (2 * intersection[present] + 1e-6) / (predicted[present] + expected[present] + 1e-6)
    ).mean()
    return ce / expected.sum() + dice_weight * (1 - dice)


class StreamingSegmentation:
    """O(classes squared) state; no retained images or full-resolution logits."""

    def __init__(self, classes: int, device: torch.device, ignore_index: int = 255) -> None:
        if classes < 1:
            raise ValueError("classes must be positive")
        self.classes, self.ignore_index = classes, ignore_index
        self.confusion = torch.zeros((classes, classes), dtype=torch.int64, device=device)
        self.ce = torch.zeros((), dtype=torch.float64, device=device)
        self.predicted = torch.zeros(classes, dtype=torch.float64, device=device)
        self.expected = torch.zeros_like(self.predicted)
        self.intersection = torch.zeros_like(self.predicted)

    def update(self, logits: Tensor, targets: Tensor) -> None:
        if logits.shape[1] != self.classes:
            raise ValueError("validation taxonomy changed")
        ce, predicted, expected, intersection = segmentation_terms(
            logits, targets, self.ignore_index
        )
        self.ce += ce.detach()
        self.predicted += predicted.detach()
        self.expected += expected.detach()
        self.intersection += intersection.detach()
        valid = targets != self.ignore_index
        indices = targets[valid] * self.classes + logits.argmax(1)[valid]
        self.confusion += torch.bincount(indices, minlength=self.classes**2).reshape(
            self.classes, self.classes
        )

    def metrics(self, dice_weight: float = 0.0) -> dict[str, float]:
        matrix = self.confusion.double().cpu()
        if matrix.sum() == 0:
            raise ValueError("validation contains no valid pixels")
        tp = matrix.diag()
        total = matrix.sum(0) + matrix.sum(1)
        union = total - tp
        present = union > 0
        iou = tp / union.clamp_min(1)
        dice = 2 * tp / total.clamp_min(1)
        supported = self.expected > 0
        soft_dice = (
            (2 * self.intersection[supported] + 1e-6)
            / (self.predicted[supported] + self.expected[supported] + 1e-6)
        ).mean()
        result = {
            "macro_iou": float(iou[present].mean()),
            "macro_dice": float(dice[present].mean()),
            "pixel_accuracy": float(tp.sum() / matrix.sum()),
            "validation_loss": float(self.ce / self.expected.sum() + dice_weight * (1 - soft_dice)),
        }
        for c in range(self.classes):
            result.update(
                {
                    f"class_{c}_iou": float(iou[c]),
                    f"class_{c}_dice": float(dice[c]),
                    f"class_{c}_present": float(present[c]),
                    f"class_{c}_pixels": float(matrix[c].sum()),
                    f"class_{c}_pixel_fraction": float(matrix[c].sum() / matrix.sum()),
                }
            )
            for other in range(self.classes):
                result[f"confusion_{c}_{other}"] = float(matrix[c, other])
        if not all(math.isfinite(value) for value in result.values()):
            raise ValueError("nonfinite segmentation metrics")
        return result
