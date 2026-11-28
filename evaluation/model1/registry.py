"""Runtime registry for the selected Phase 11 models: verified, lazy and frozen.

Paths are relative to the data root so a verified copy can be moved to another drive.
A checkpoint that is missing or fails verification is never replaced by random weights.
"""

import hashlib
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any, Literal

import torch
from pydantic import Field
from torch import nn

from agents.shared.domain import Record
from evaluation.model1.environment_fusion import EnvironmentalFusion
from evaluation.model1.models import ModelConfig, build_model
from evaluation.model1.phase11i_tasks import AudioMobileNet

State = Literal["READY", "EXPERIMENTAL", "UNAVAILABLE", "EXCLUDED"]
Precision = Literal["fp32", "fp16", "bf16"]
EXCLUDED_MODELS = frozenset({"wisard-thermal"})


class ModelEntry(Record):
    model_id: str
    task: str
    state: State
    reason: str = ""
    architecture: str = ""
    checkpoint: str | None = None
    sha256: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    modality: str = ""
    preprocessing: str = ""
    labels: tuple[str, ...] = ()
    units: str = ""
    metric: str = ""
    metric_value: float | None = None
    authorization_id: str | None = None
    release_manifest_sha256: str | None = None
    limitations: tuple[str, ...] = ()
    devices: tuple[str, ...] = ("cpu", "cuda")
    precisions: tuple[str, ...] = ("fp32", "fp16", "bf16")


class ModelUnavailable(RuntimeError):
    pass


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _build(entry: ModelEntry) -> nn.Module:
    config = entry.config
    if entry.architecture == "deeplabv3_mobilenet_v3_large":
        return build_model(ModelConfig(task="semantic_segmentation",
                                       num_classes=len(entry.labels), image_size=512))
    if entry.architecture == "mobilenet_v3_small":
        return build_model(ModelConfig(task="image_classification", num_classes=2))
    if entry.architecture == "mobilenet_v3_small_logmel":
        return AudioMobileNet(len(entry.labels))
    if entry.architecture == "gru_sensor_regression":
        return build_model(ModelConfig(
            task="sensor_regression", num_classes=1, sensor_features=8,
            hidden_dim=int(config["hidden_dim"]), dropout=float(config["dropout"])))
    if entry.architecture == "fasterrcnn_mobilenet_v3_large_fpn":
        return build_model(ModelConfig(task="object_detection", num_classes=2, image_size=512))
    if entry.architecture == "EnvironmentalFusion":
        return EnvironmentalFusion()
    raise ModelUnavailable(f"unsupported architecture: {entry.architecture}")


def resolve_device(device: str) -> torch.device:
    """'auto' and unavailable CUDA fall back to CPU."""
    wanted = "cuda" if device == "auto" else device
    if wanted.startswith("cuda") and not torch.cuda.is_available():
        wanted = "cpu"
    return torch.device(wanted)


class ModelRegistry:
    """Shared by every simulated agent; holds no agent state. Not thread-safe."""

    def __init__(
        self,
        entries: dict[str, ModelEntry],
        data_root: Path,
        *,
        device: str = "auto",
        precision: Precision = "fp32",
        max_resident: int = 2,
    ) -> None:
        if max_resident < 1 or precision not in ("fp32", "fp16", "bf16"):
            raise ValueError("invalid residency bound or precision")
        self.entries, self.data_root = dict(entries), data_root
        self.device = resolve_device(device)
        self.precision: Precision = "fp32" if self.device.type == "cpu" else precision
        self.max_resident = max_resident
        self.resident: OrderedDict[str, nn.Module] = OrderedDict()
        self.loads: dict[str, int] = {}
        self._verified: dict[str, tuple[int, int]] = {}

    @classmethod
    def from_config(cls, path: Path, data_root: Path, config: Path) -> "ModelRegistry":
        """Apply a hardware runtime file such as configs/rtx2060_runtime.json."""
        settings = json.loads(config.read_bytes())
        return cls.from_file(path, data_root, device=settings["device"],
                             precision=settings["precision"],
                             max_resident=settings["max_resident"])

    @classmethod
    def from_file(cls, path: Path, data_root: Path, **options: Any) -> "ModelRegistry":
        payload = json.loads(path.read_bytes())
        rows = [ModelEntry.model_validate(row) for row in payload["models"]]
        return cls({row.model_id: row for row in rows}, data_root, **options)

    def state(self, model_id: str) -> State:
        if model_id in EXCLUDED_MODELS:
            return "EXCLUDED"
        entry = self.entries.get(model_id)
        return entry.state if entry else "UNAVAILABLE"

    def get(self, model_id: str) -> nn.Module:
        state = self.state(model_id)
        if state in ("EXCLUDED", "UNAVAILABLE"):
            raise ModelUnavailable(f"{model_id} is {state}")
        if model_id in self.resident:
            self.resident.move_to_end(model_id)
            return self.resident[model_id]
        model = self._load(self.entries[model_id])
        while len(self.resident) >= self.max_resident:
            self.resident.popitem(last=False)
            if self.device.type == "cuda":
                torch.cuda.empty_cache()
        model.to(self.device)
        self.resident[model_id] = model
        self.loads[model_id] = self.loads.get(model_id, 0) + 1
        return model

    def _load(self, entry: ModelEntry) -> nn.Module:
        if entry.checkpoint is None or entry.sha256 is None:
            raise ModelUnavailable(f"{entry.model_id} has no registered checkpoint")
        path = self.data_root / entry.checkpoint
        if not path.is_file():
            raise ModelUnavailable(f"{entry.model_id} checkpoint is missing")
        stamp = (path.stat().st_size, path.stat().st_mtime_ns)
        if self._verified.get(entry.model_id) != stamp:
            if file_sha256(path) != entry.sha256:
                raise ModelUnavailable(f"{entry.model_id} checkpoint checksum mismatch")
            self._verified[entry.model_id] = stamp
        try:
            # Checkpoints also hold optimizer and loop state several times the model's size.
            # Mapping the file avoids reading them; load_state_dict copies the weights out.
            payload = torch.load(path, map_location="cpu", weights_only=True, mmap=True)
            weights = payload["model_state"]
            if entry.architecture == "deeplabv3_mobilenet_v3_large":
                # Phase 11I training wrapped the network; drop only that prefix.
                weights = {k.removeprefix("inner."): v for k, v in weights.items()}
            model = _build(entry)
            model.load_state_dict(weights, strict=True)
        except (KeyError, RuntimeError, ValueError, OSError) as exc:
            raise ModelUnavailable(f"{entry.model_id} failed strict loading") from exc
        model.eval()
        model.requires_grad_(False)
        return model

    def release(self) -> None:
        self.resident.clear()
        if self.device.type == "cuda":
            torch.cuda.empty_cache()
