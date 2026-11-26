"""Bounded synthetic component profiling; never opens dataset assets."""

import argparse
import gc
import json
import time
from pathlib import Path
from typing import Any, cast

import torch
from torch import nn

from evaluation.model1.models import MissingAwareFusion, ModelConfig, build_model
from evaluation.model1.temporal import TemporalHead
from evaluation.model1.training import (
    ClassificationTask,
    DetectionTask,
    GradientScaler,
    RegressionTask,
    SegmentationTask,
    TaskAdapter,
    make_gradient_scaler,
)


def component(
    name: str, batch: int, device: torch.device
) -> tuple[nn.Module, Any, Any, TaskAdapter]:
    if name == "fusion":

        class FusionProbe(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.fusion = MissingAwareFusion(
                    {"rgb": 128, "thermal": 128, "audio": 128, "sensor": 32}
                )
                self.head = nn.Linear(128, 4)

            def forward(
                self, values: dict[str, torch.Tensor], available: dict[str, torch.Tensor]
            ) -> tuple[torch.Tensor, torch.Tensor]:
                features, valid = self.fusion(values, available)
                return self.head(features), valid

        values = {
            n: torch.randn(batch, d, device=device)
            for n, d in {"rgb": 128, "thermal": 128, "audio": 128, "sensor": 32}.items()
        }
        masks = {n: torch.ones(batch, device=device, dtype=torch.bool) for n in values}
        masks["thermal"][::2] = False
        return (
            FusionProbe().to(device),
            {"values": values, "available": masks},
            torch.arange(batch, device=device) % 4,
            ClassificationTask(),
        )
    if name == "temporal":

        class TemporalProbe(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.temporal = TemporalHead(128, 64, 4)

            def forward(self, values: torch.Tensor) -> torch.Tensor:
                mask = torch.ones(len(values), device=values.device, dtype=torch.bool)
                logits, _ = self.temporal(values, mask, values.new_zeros(len(values), 64))
                return cast(torch.Tensor, logits)

        return (
            TemporalProbe().to(device),
            torch.randn(batch, 128, device=device),
            torch.arange(batch, device=device) % 4,
            ClassificationTask(),
        )
    config = ModelConfig(task=name, num_classes=4, image_size=128, sensor_features=6)
    model = build_model(config).to(device)
    labels = torch.arange(batch, device=device) % 4
    if name.startswith("sensor_"):
        sensor_values = torch.randn(batch, 24, 6, device=device)
        sensor_masks = torch.ones_like(sensor_values, dtype=torch.bool)
        if name == "sensor_regression":
            return (
                model,
                {"values": sensor_values, "available": sensor_masks},
                torch.randn(batch, 4, device=device),
                RegressionTask(),
            )
        return (
            model,
            {"values": sensor_values, "available": sensor_masks},
            labels,
            ClassificationTask(),
        )
    if name == "audio_classification":
        return model, torch.randn(batch, 1, 128, 64, device=device), labels, ClassificationTask()
    channels = 1 if name == "thermal_classification" else 3
    images = torch.rand(batch, channels, 128, 128, device=device)
    if name == "semantic_segmentation":
        return model, images, torch.randint(4, (batch, 128, 128), device=device), SegmentationTask()
    if name == "object_detection":
        targets = [
            {
                "boxes": torch.tensor([[8.0, 8.0, 60.0, 60.0]], device=device),
                "labels": torch.tensor([1], device=device),
            }
            for _ in range(batch)
        ]
        return model, list(images), targets, DetectionTask()
    return model, images, labels, ClassificationTask()


def _step(
    model: nn.Module,
    optimizer: torch.optim.Optimizer,
    adapter: TaskAdapter,
    scaler: GradientScaler,
    features: Any,
    targets: Any,
    dtype: torch.dtype,
    precision: str,
) -> float:
    optimizer.zero_grad(set_to_none=True)
    with torch.autocast("cuda", dtype=dtype, enabled=precision != "float32"):
        loss = adapter.loss(model, features, targets)
    if not torch.isfinite(loss):
        raise ValueError("nonfinite synthetic loss")
    torch.autograd.backward(scaler.scale(loss))
    scaler.unscale_(optimizer)
    nn.utils.clip_grad_norm_(model.parameters(), 1.0, error_if_nonfinite=True)
    scaler.step(optimizer)
    scaler.update()
    return float(loss.detach())


def profile(output: Path, batches: tuple[int, ...] = (2, 8), steps: int = 2) -> dict[str, Any]:
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA required for measured GPU profiling")
    if steps < 1 or steps > 10 or any(b < 2 or b > 16 for b in batches):
        raise ValueError("bounded profile requires batches 2-16 and steps 1-10")
    if output.resolve().drive.upper() != "D:":
        raise ValueError("profile outputs must remain on D:")
    device = torch.device("cuda:0")
    torch.manual_seed(2025)
    torch.set_num_threads(2)
    total = torch.cuda.get_device_properties(device).total_memory
    torch.cuda.set_per_process_memory_fraction(min(0.5, 8 * 1024**3 / total), device)
    result: dict[str, Any] = {
        "synthetic_only": True,
        "gpu": torch.cuda.get_device_name(),
        "torch": str(torch.__version__),
        "cuda": torch.version.cuda,
        "total_memory_bytes": total,
        "allocator_limit_bytes": min(total // 2, 8 * 1024**3),
        "image_size": 128,
        "warmup_steps": 1,
        "measured_steps": steps,
        "rows": [],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    names = (
        "image_classification",
        "thermal_classification",
        "audio_classification",
        "sensor_classification",
        "sensor_regression",
        "semantic_segmentation",
        "object_detection",
        "fusion",
        "temporal",
    )
    for name in names:
        for batch in batches:
            for precision in ("float32", "bfloat16", "float16"):
                row: dict[str, Any] = {"component": name, "batch": batch, "precision": precision}
                model = optimizer = features = targets = adapter = scaler = None
                try:
                    if precision == "bfloat16" and not torch.cuda.is_bf16_supported():
                        raise RuntimeError("bfloat16 not supported by this device")
                    model, features, targets, adapter = component(name, batch, device)
                    model.train()
                    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
                    scaler = make_gradient_scaler(enabled=precision == "float16")
                    dtype = torch.float16 if precision == "float16" else torch.bfloat16
                    _step(model, optimizer, adapter, scaler, features, targets, dtype, precision)
                    torch.cuda.synchronize()
                    torch.cuda.reset_peak_memory_stats()
                    start = time.perf_counter()
                    for _ in range(steps):
                        loss = _step(
                            model, optimizer, adapter, scaler, features, targets, dtype, precision
                        )
                    torch.cuda.synchronize()
                    seconds = time.perf_counter() - start
                    row.update(
                        status="PASS",
                        loss=loss,
                        seconds=seconds,
                        examples_per_second=batch * steps / seconds,
                        peak_allocated_bytes=torch.cuda.max_memory_allocated(),
                        peak_reserved_bytes=torch.cuda.max_memory_reserved(),
                    )
                except (RuntimeError, ValueError) as error:
                    row.update(status="UNSUPPORTED_OR_FAILED", reason=str(error)[:400])
                finally:
                    del model, optimizer, features, targets, adapter, scaler
                    gc.collect()
                    torch.cuda.empty_cache()
                result["rows"].append(row)
                output.write_text(json.dumps(result, indent=2), encoding="utf8")
        print(name, "profiled", flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("D:/SWARM-AID/runs/phase11/gpu.json"))
    args = parser.parse_args()
    profile(args.output)
