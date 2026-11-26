"""Synthetic GPU smoke test and peak-memory profiler."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch
from torch import Tensor, nn

from evaluation.model1.models import ModelConfig, build_model
from evaluation.model1.vision import nms


def gpu_smoke(device_name: str, batch_size: int, *, profile: bool = False) -> dict[str, Any]:
    if batch_size < 1:
        raise ValueError("batch size must be positive")
    device = torch.device(device_name)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA smoke test requested but CUDA is unavailable")
    if profile and device.type != "cuda":
        raise ValueError("GPU memory profiling requires a CUDA device")
    torch.manual_seed(42)
    model = build_model(ModelConfig(task="image_classification", num_classes=4, image_size=128)).to(
        device
    )
    model.train()
    optimizer = torch.optim.SGD(model.parameters(), lr=0.001)
    if device.type == "cuda":
        boxes = torch.tensor([[0, 0, 10, 10], [1, 1, 9, 9]], dtype=torch.float32, device=device)
        scores = torch.tensor([0.9, 0.8], device=device)
        if nms(boxes, scores, 0.5).tolist() != [0]:
            raise RuntimeError("TorchVision CUDA NMS verification failed")
    images = torch.rand(batch_size, 3, 128, 128, device=device)
    targets = torch.arange(batch_size, device=device) % 4
    if profile:
        torch.cuda.reset_peak_memory_stats(device)
    optimizer.zero_grad(set_to_none=True)
    logits = model(images)
    if not isinstance(logits, Tensor):
        raise TypeError("classification model returned a non-tensor output")
    loss = nn.functional.cross_entropy(logits, targets)
    if not torch.isfinite(loss):
        raise RuntimeError("synthetic smoke loss is nonfinite")
    torch.autograd.backward(loss)
    optimizer.step()
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    result: dict[str, Any] = {
        "schema_version": "phase11-gpu-smoke-1.0",
        "created_at": datetime.now(UTC).isoformat(),
        "device": str(device),
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "gpu_name": torch.cuda.get_device_name(device) if device.type == "cuda" else None,
        "batch_size": batch_size,
        "synthetic_optimizer_step": True,
        "loss": float(loss.detach()),
    }
    if profile:
        result["peak_allocated_bytes"] = torch.cuda.max_memory_allocated(device)
        result["peak_reserved_bytes"] = torch.cuda.max_memory_reserved(device)
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("smoke", "profile"))
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = gpu_smoke(args.device, args.batch_size, profile=args.command == "profile")
    output = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(output, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
        print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
