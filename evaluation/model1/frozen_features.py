"""Frozen adapters for already authorized, strictly restored encoders; no checkpoint I/O."""
from collections.abc import Callable
from typing import Any, Literal, Self

import torch
from pydantic import Field
from torch import Tensor, nn

from agents.shared.domain import Record
from evaluation.data.release_authorization import Digest

DIMENSIONS = {"audio": 128, "sensor": 128, "flood": 960, "fire": 576, "damage": 960}


class FeatureProvenance(Record):
    schema_version: Literal["frozen-features-1"] = "frozen-features-1"
    component: Literal["audio", "sensor", "flood", "fire", "damage"]
    checkpoint_sha256: Digest
    preprocessing_sha256: Digest
    authorization_id: str = Field(min_length=1)
    source_manifest_sha256: Digest
    extraction_revision: Literal["prehead-pooled-2"] = "prehead-pooled-2"


class FrozenFeatureAdapter(nn.Module):
    """Inject the existing authorized preprocessing and restored model unchanged.

    Caller retains checkpoint/source authorization responsibility. No raw-data
    loader, inferred normalization, pairing, checkpoint mutation or download.
    """
    def __init__(self, model: nn.Module, preprocess: Callable[[Any], Any],
                 provenance: FeatureProvenance) -> None:
        super().__init__()
        self.model = model
        self.preprocess = preprocess
        self.provenance = provenance
        self.output_dim = DIMENSIONS[provenance.component]
        self.model.requires_grad_(False)
        self.model.eval()

    def train(self, mode: bool = True) -> Self:
        super().train(False)
        self.model.eval()
        return self

    @torch.no_grad()
    def forward(self, source: Any) -> tuple[Tensor, Tensor]:
        self.model.eval()
        value = self.preprocess(source)
        model: Any = self.model
        name = self.provenance.component
        if name == "sensor":
            # Reuse validation, availability cleaning and GRU execution in the model.
            captured: list[Tensor] = []
            def hook(module: nn.Module, args: Any, output: Any) -> None:
                captured.append(output[0][:, -1])
            handle = model.encoder.register_forward_hook(hook)
            try:
                _, valid = model(value["values"], value["available"])
            finally:
                handle.remove()
            features = torch.where(valid[:, None], captured[0], torch.zeros_like(captured[0]))
        else:
            encoded = model.backbone(value)["out"] if name in {"flood", "damage"} else model.features(value)
            features = encoded.mean(dim=tuple(range(2, encoded.ndim)))
            valid = torch.ones(features.shape[0], dtype=torch.bool, device=features.device)
        if features.ndim != 2 or features.shape[1] != self.output_dim or not torch.isfinite(features).all():
            raise ValueError("frozen encoder feature contract mismatch")
        return features.detach(), valid.detach()
