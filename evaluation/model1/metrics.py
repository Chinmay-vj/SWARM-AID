"""Task metrics implemented without optional metric packages."""

import math
from collections.abc import Mapping, Sequence

import torch
from torch import Tensor


def classification_metrics(logits: Tensor, targets: Tensor) -> dict[str, float]:
    if logits.ndim != 2 or targets.ndim != 1 or logits.shape[0] != targets.shape[0]:
        raise ValueError("classification expects [batch,classes] logits and [batch] targets")
    if not targets.numel() or targets.min() < 0 or targets.max() >= logits.shape[1]:
        raise ValueError("classification targets must be nonempty and within the model taxonomy")
    predictions = logits.argmax(dim=1)
    class_count = logits.shape[1]
    confusion = torch.bincount(
        targets * class_count + predictions, minlength=class_count * class_count
    ).reshape(class_count, class_count)
    true_positive = confusion.diag().to(torch.float64)
    precision = true_positive / confusion.sum(dim=0).clamp_min(1)
    recall = true_positive / confusion.sum(dim=1).clamp_min(1)
    f1 = 2 * precision * recall / (precision + recall).clamp_min(1.0e-12)
    return {
        "accuracy": float((predictions == targets).float().mean()),
        "macro_precision": float(precision.mean()),
        "macro_recall": float(recall.mean()),
        "macro_f1": float(f1.mean()),
    }


def expected_calibration_error(logits: Tensor, targets: Tensor, bins: int = 15) -> float:
    if (
        bins < 1
        or logits.ndim != 2
        or targets.ndim != 1
        or logits.shape[0] != targets.shape[0]
        or not targets.numel()
    ):
        raise ValueError("invalid calibration inputs or bin count")
    probabilities = logits.softmax(dim=1)
    confidence, predicted = probabilities.max(dim=1)
    correct = predicted.eq(targets)
    edges = torch.linspace(0, 1, bins + 1, device=logits.device)
    error = torch.zeros((), dtype=logits.dtype, device=logits.device)
    for index in range(bins):
        selected = (confidence > edges[index]) & (confidence <= edges[index + 1])
        if selected.any():
            error += (
                selected.float().mean()
                * (confidence[selected].mean() - correct[selected].float().mean()).abs()
            )
    return float(error)


def segmentation_metrics(
    logits: Tensor, targets: Tensor, classes: int, ignore_index: int | None = None
) -> dict[str, float]:
    if logits.ndim != 4 or targets.ndim != 3 or logits.shape[0] != targets.shape[0]:
        raise ValueError("segmentation expects [batch,classes,height,width] logits")
    predicted = logits.argmax(dim=1).reshape(-1)
    expected = targets.reshape(-1)
    valid = torch.ones_like(expected, dtype=torch.bool)
    if ignore_index is not None:
        valid &= expected.ne(ignore_index)
    predicted, expected = predicted[valid], expected[valid]
    if expected.numel() == 0:
        raise ValueError("segmentation metrics require at least one valid pixel")
    confusion = torch.bincount(expected * classes + predicted, minlength=classes * classes).reshape(
        classes, classes
    )
    intersection = confusion.diag().to(torch.float64)
    union = confusion.sum(dim=0) + confusion.sum(dim=1) - intersection
    dice_denominator = confusion.sum(dim=0) + confusion.sum(dim=1)
    present = union > 0
    iou = intersection[present] / union[present]
    dice = (2 * intersection[present]) / dice_denominator[present].clamp_min(1)
    return {"macro_iou": float(iou.mean()), "macro_dice": float(dice.mean())}


def regression_metrics(predictions: Tensor, targets: Tensor) -> dict[str, float]:
    if predictions.shape != targets.shape or predictions.numel() == 0:
        raise ValueError("regression predictions and targets must have equal nonempty shapes")
    error = predictions.to(torch.float64) - targets.to(torch.float64)
    mae = error.abs().mean()
    rmse = error.square().mean().sqrt()
    variance = targets.to(torch.float64).var(unbiased=False)
    if variance == 0:
        raise ValueError("R-squared is undefined for a constant target")
    r_squared = float(1 - error.square().mean() / variance)
    if not math.isfinite(float(mae)) or not math.isfinite(float(rmse)):
        raise ValueError("nonfinite regression metric")
    return {"mae": float(mae), "rmse": float(rmse), "r_squared": r_squared}


def missing_modality_accuracy(
    logits: Tensor, targets: Tensor, availability: Mapping[str, Tensor]
) -> dict[str, float]:
    if not availability or logits.shape[0] != targets.shape[0]:
        raise ValueError("missing-modality evaluation needs aligned predictions and masks")
    results: dict[str, float] = {}
    missing = torch.zeros_like(targets, dtype=torch.bool)
    for name in sorted(availability):
        mask = availability[name]
        if mask.shape != targets.shape or mask.dtype != torch.bool:
            raise ValueError("modality availability masks must be boolean and batch aligned")
        missing |= ~mask
        selected = ~mask
        if selected.any():
            results[f"missing_{name}_accuracy"] = float(
                (logits[selected].argmax(dim=1) == targets[selected]).float().mean()
            )
    complete = ~missing
    if complete.any():
        results["complete_accuracy"] = float(
            (logits[complete].argmax(dim=1) == targets[complete]).float().mean()
        )
    if not results:
        raise ValueError("no complete or missing-modality examples to evaluate")
    return results


def detection_metrics(
    predictions: Sequence[Mapping[str, Tensor]],
    targets: Sequence[Mapping[str, Tensor]],
    iou_threshold: float = 0.5,
) -> dict[str, float]:
    if len(predictions) != len(targets) or not 0 < iou_threshold <= 1:
        raise ValueError("detection predictions, targets or IoU threshold are invalid")
    classes = sorted({int(label) for record in targets for label in record["labels"].tolist()})
    if not classes:
        raise ValueError("detection metrics require at least one target box")
    per_class: list[float] = []
    true_positives_total = 0
    false_positives_total = 0
    target_total = 0
    for class_id in classes:
        ground_truth: dict[int, Tensor] = {}
        matched: dict[int, Tensor] = {}
        candidates: list[tuple[float, int, Tensor]] = []
        class_targets = 0
        for image_index, target in enumerate(targets):
            selected = target["labels"] == class_id
            boxes = target["boxes"][selected]
            ground_truth[image_index] = boxes
            matched[image_index] = torch.zeros(boxes.shape[0], dtype=torch.bool)
            class_targets += boxes.shape[0]
        for image_index, prediction in enumerate(predictions):
            selected = prediction["labels"] == class_id
            for score, box in zip(prediction["scores"][selected], prediction["boxes"][selected]):
                candidates.append((float(score), image_index, box))
        candidates.sort(key=lambda candidate: candidate[0], reverse=True)
        true_positive: list[float] = []
        false_positive: list[float] = []
        for _, image_index, box in candidates:
            expected = ground_truth[image_index]
            if expected.numel() == 0:
                true_positive.append(0.0)
                false_positive.append(1.0)
                continue
            overlaps = _box_iou(box.unsqueeze(0), expected).squeeze(0)
            best_index = int(overlaps.argmax())
            is_match = (
                float(overlaps[best_index]) >= iou_threshold
                and not matched[image_index][best_index]
            )
            true_positive.append(float(is_match))
            false_positive.append(float(not is_match))
            if is_match:
                matched[image_index][best_index] = True
        tp = torch.tensor(true_positive, dtype=torch.float64).cumsum(0)
        fp = torch.tensor(false_positive, dtype=torch.float64).cumsum(0)
        recall = tp / max(class_targets, 1)
        precision = tp / (tp + fp).clamp_min(1)
        per_class.append(_average_precision(recall, precision))
        true_positives_total += int(tp[-1]) if tp.numel() else 0
        false_positives_total += int(fp[-1]) if fp.numel() else 0
        target_total += class_targets
    return {
        "precision": true_positives_total / max(true_positives_total + false_positives_total, 1),
        "recall": true_positives_total / max(target_total, 1),
        "map50": sum(per_class) / len(per_class),
    }


def _average_precision(recall: Tensor, precision: Tensor) -> float:
    if recall.numel() == 0:
        return 0.0
    recall = torch.cat(
        (torch.zeros(1, dtype=recall.dtype), recall, torch.ones(1, dtype=recall.dtype))
    )
    precision = torch.cat(
        (torch.zeros(1, dtype=precision.dtype), precision, torch.zeros(1, dtype=precision.dtype))
    )
    for index in range(precision.numel() - 2, -1, -1):
        precision[index] = torch.maximum(precision[index], precision[index + 1])
    changes = torch.where(recall[1:] != recall[:-1])[0]
    return float(((recall[changes + 1] - recall[changes]) * precision[changes + 1]).sum())


def _box_iou(first: Tensor, second: Tensor) -> Tensor:
    top_left = torch.maximum(first[:, None, :2], second[None, :, :2])
    bottom_right = torch.minimum(first[:, None, 2:], second[None, :, 2:])
    intersection = (bottom_right - top_left).clamp_min(0).prod(dim=2)
    first_area = (first[:, 2:] - first[:, :2]).clamp_min(0).prod(dim=1)
    second_area = (second[:, 2:] - second[:, :2]).clamp_min(0).prod(dim=1)
    union = first_area[:, None] + second_area[None, :] - intersection
    return intersection / union.clamp_min(torch.finfo(intersection.dtype).eps)
