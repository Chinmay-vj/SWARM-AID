"""Atomic, checksum-verified checkpoints with isolated synthetic and real releases."""

import hashlib
import importlib.metadata
import importlib.util
import io
import math
import os
import platform
import random
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import torch
from torch import nn
from torch.optim import Optimizer
from torch.optim.lr_scheduler import LRScheduler, ReduceLROnPlateau

from evaluation.model1.training import GradientScaler, TrainingContext

CheckpointScheduler = LRScheduler | ReduceLROnPlateau
CHECKPOINT_SCHEMA = "phase11-model1-checkpoint-1.0"


@dataclass(frozen=True)
class CheckpointInfo:
    path: Path
    sha256: str
    epoch: int
    global_step: int
    best_validation_metric: float
    artifact_kind: str
    authorization_id: str | None
    loop_state: dict[str, Any] = field(default_factory=dict)


def save_checkpoint(
    root: Path,
    filename: str,
    model: nn.Module,
    optimizer: Optimizer,
    scheduler: CheckpointScheduler | None,
    scaler: GradientScaler,
    *,
    epoch: int,
    global_step: int,
    best_validation_metric: float,
    model_config: dict[str, Any],
    training_config: dict[str, Any],
    context: TrainingContext,
    loop_state: dict[str, Any] | None = None,
) -> CheckpointInfo:
    if not _safe_filename(filename) or epoch < 1 or global_step < 0:
        raise ValueError("invalid checkpoint filename or training position")
    if not math.isfinite(best_validation_metric):
        raise ValueError("best validation metric must be finite")
    if (
        context.artifact_kind in {"authorized_training", "authorized_symbolic_training"}
        and not context.authorization_id
    ):
        raise ValueError("real checkpoint requires explicit task authorization")
    destination_dir = root.resolve() / _artifact_folder(context)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / filename
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite checkpoint: {destination}")
    payload: dict[str, Any] = {
        "schema_version": CHECKPOINT_SCHEMA,
        "artifact_kind": context.artifact_kind,
        "task_id": context.task_id,
        "release_manifest_sha256": context.release_manifest_sha256,
        "authorization_id": context.authorization_id,
        "candidate_manifest_sha256": context.candidate_manifest_sha256,
        "training_targets_manifest_sha256": context.training_targets_manifest_sha256,
        "epoch": epoch,
        "global_step": global_step,
        "best_validation_metric": best_validation_metric,
        "model_config": model_config,
        "training_config": training_config,
        "environment": _environment(),
        "model_state": model.state_dict(),
        "optimizer_state": optimizer.state_dict(),
        "scheduler_state": scheduler.state_dict() if scheduler is not None else None,
        "amp_state": scaler.state_dict(),
        "rng_state": _rng_state(),
        "loop_state": loop_state or {},
    }
    buffer = io.BytesIO()
    torch.save(payload, buffer)
    content = buffer.getvalue()
    checksum = hashlib.sha256(content).hexdigest()
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{filename}.",
            suffix=".tmp",
            dir=destination_dir,
            delete=False,
        ) as stream:
            temporary = stream.name
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except OSError:
        if temporary is not None and Path(temporary).exists():
            Path(temporary).unlink()
        raise
    return CheckpointInfo(
        destination,
        checksum,
        epoch,
        global_step,
        best_validation_metric,
        context.artifact_kind,
        context.authorization_id,
    )


def restore_checkpoint(
    path: Path,
    expected_sha256: str,
    root: Path,
    model: nn.Module,
    optimizer: Optimizer,
    scheduler: CheckpointScheduler | None,
    scaler: GradientScaler,
    *,
    expected_model_config: dict[str, Any],
    expected_training_config: dict[str, Any],
    expected_context: TrainingContext,
    device: torch.device,
) -> CheckpointInfo:
    expected_folder = (root.resolve() / _artifact_folder(expected_context)).resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(expected_folder) or not resolved.is_file():
        raise ValueError("checkpoint is outside its artifact-kind directory or is missing")
    actual_sha256 = _sha256(resolved)
    if actual_sha256 != expected_sha256:
        raise ValueError("checkpoint checksum mismatch")
    payload = torch.load(resolved, map_location="cpu", weights_only=True)
    if not isinstance(payload, dict) or payload.get("schema_version") != CHECKPOINT_SCHEMA:
        raise ValueError("unsupported checkpoint schema")
    expected_context_values = {
        "artifact_kind": expected_context.artifact_kind,
        "task_id": expected_context.task_id,
        "release_manifest_sha256": expected_context.release_manifest_sha256,
        "authorization_id": expected_context.authorization_id,
        "candidate_manifest_sha256": expected_context.candidate_manifest_sha256,
        "training_targets_manifest_sha256": expected_context.training_targets_manifest_sha256,
    }
    if any(payload.get(name) != value for name, value in expected_context_values.items()):
        raise ValueError("checkpoint training provenance differs from the requested context")
    if payload.get("model_config") != expected_model_config:
        raise ValueError("checkpoint model configuration is incompatible")
    if payload.get("training_config") != expected_training_config:
        raise ValueError("checkpoint training configuration is incompatible")
    saved_environment = payload.get("environment")
    if not isinstance(saved_environment, dict) or not _compatible_environment(saved_environment):
        raise ValueError("checkpoint framework versions are incompatible")
    model_state = payload.get("model_state")
    optimizer_state = payload.get("optimizer_state")
    if not isinstance(model_state, dict) or not isinstance(optimizer_state, dict):
        raise TypeError("checkpoint model and optimizer states must be mappings")
    scheduler_state = payload.get("scheduler_state")
    if scheduler is not None:
        if not isinstance(scheduler_state, dict):
            raise ValueError("checkpoint does not contain the configured scheduler state")
    elif scheduler_state is not None:
        raise ValueError("checkpoint scheduler configuration differs")
    scaler_state = payload.get("amp_state")
    if not isinstance(scaler_state, dict):
        raise TypeError("checkpoint AMP state must be a mapping")
    rng_state = payload.get("rng_state")
    epoch, global_step = payload.get("epoch"), payload.get("global_step")
    best_metric = payload.get("best_validation_metric")
    if (
        not isinstance(epoch, int)
        or epoch < 1
        or not isinstance(global_step, int)
        or global_step < 0
        or not isinstance(best_metric, (int, float))
    ):
        raise ValueError("checkpoint progress metadata is invalid")
    if not math.isfinite(float(best_metric)):
        raise ValueError("checkpoint validation metric is nonfinite")
    current_state = model.state_dict()
    if set(current_state) != set(model_state) or any(
        current_state[name].shape != model_state[name].shape for name in current_state
    ):
        raise ValueError("checkpoint model weights are incompatible")
    if not isinstance(rng_state, dict):
        raise TypeError("checkpoint RNG state must be a mapping")
    model.load_state_dict(model_state, strict=True)
    optimizer.load_state_dict(optimizer_state)
    if scheduler is not None:
        scheduler.load_state_dict(cast(dict[str, Any], scheduler_state))
    scaler.load_state_dict(cast(dict[str, Any], scaler_state))
    _restore_rng(rng_state)
    return CheckpointInfo(
        resolved,
        actual_sha256,
        epoch,
        global_step,
        float(best_metric),
        expected_context.artifact_kind,
        expected_context.authorization_id,
        payload.get("loop_state", {}),
    )


def _safe_filename(value: str) -> bool:
    return (
        bool(value)
        and Path(value).name == value
        and value not in {".", ".."}
        and value.endswith(".pt")
    )


def _artifact_folder(context: TrainingContext) -> str:
    return (
        "synthetic"
        if context.artifact_kind == "synthetic_fixture"
        else "authorized-symbolic-training"
        if context.artifact_kind == "authorized_symbolic_training"
        else "authorized-training"
    )


def _environment() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for package in ("torch", "torchvision", "torchaudio"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "torch": versions["torch"],
        "torchvision": versions["torchvision"],
        "torchaudio": versions["torchaudio"],
        "git_commit": _git_commit(),
        "source_sha256": hashlib.sha256(
            b"".join(
                path.name.encode() + path.read_bytes()
                for path in sorted(Path(__file__).parent.glob("*.py"))
            )
        ).hexdigest(),
    }


def _compatible_environment(saved: dict[str, Any]) -> bool:
    for package in ("torch", "torchvision", "torchaudio"):
        try:
            current = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            return False
        previous = saved.get(package)
        if not isinstance(previous, str) or previous.split(".")[:2] != current.split(".")[:2]:
            return False
    return True


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _rng_state() -> dict[str, Any]:
    state: dict[str, Any] = {
        "python": random.getstate(),
        "torch_cpu": torch.get_rng_state(),
        "torch_cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else [],
    }
    if importlib.util.find_spec("numpy") is not None:
        import numpy as np

        name, keys, position, has_gauss, cached_gaussian = np.random.get_state()
        state["numpy"] = {
            "algorithm": name,
            "keys": keys.tolist(),
            "position": position,
            "has_gaussian": has_gauss,
            "cached_gaussian": cached_gaussian,
        }
    return state


def _restore_rng(state: Any) -> None:
    if not isinstance(state, dict) or "python" not in state or "torch_cpu" not in state:
        raise ValueError("checkpoint RNG state is incomplete")
    random.setstate(tuple(state["python"]))
    torch.set_rng_state(state["torch_cpu"])
    cuda_states = state.get("torch_cuda")
    if cuda_states and torch.cuda.is_available():
        if len(cuda_states) != torch.cuda.device_count():
            raise ValueError("checkpoint CUDA RNG state count differs from available devices")
        torch.cuda.set_rng_state_all(cuda_states)
    numpy_state = state.get("numpy")
    if numpy_state is not None:
        if importlib.util.find_spec("numpy") is None or not isinstance(numpy_state, dict):
            raise ValueError("checkpoint requires unavailable NumPy RNG support")
        import numpy as np

        np.random.set_state(
            (
                numpy_state["algorithm"],
                np.asarray(numpy_state["keys"], dtype=np.uint32),
                numpy_state["position"],
                numpy_state["has_gaussian"],
                numpy_state["cached_gaussian"],
            )
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
