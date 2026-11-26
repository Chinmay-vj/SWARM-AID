"""Shared temporal weights with explicitly owned, bounded per-agent inference state."""

from dataclasses import dataclass

import torch
from torch import Tensor, nn


@dataclass(frozen=True)
class TemporalPrediction:
    logits: Tensor
    entropy: Tensor
    valid: Tensor


class TemporalHead(nn.Module):
    def __init__(self, features: int, hidden: int, classes: int) -> None:
        super().__init__()
        if min(features, hidden, classes) < 1:
            raise ValueError("temporal dimensions must be positive")
        self.features = features
        self.hidden = hidden
        self.cell = nn.GRUCell(features, hidden)
        self.head = nn.Linear(hidden, classes)

    def forward(self, values: Tensor, available: Tensor, state: Tensor) -> tuple[Tensor, Tensor]:
        if (
            values.ndim != 2
            or values.shape[1] != self.features
            or available.shape != values.shape[:1]
            or available.dtype != torch.bool
            or state.shape != (values.shape[0], self.hidden)
        ):
            raise ValueError("invalid temporal feature, mask or state shape")
        if not torch.isfinite(values[available]).all() or not torch.isfinite(state).all():
            raise ValueError("available temporal values and state must be finite")
        cleaned = torch.where(available[:, None], values, torch.zeros_like(values))
        proposed = self.cell(cleaned, state)
        updated = torch.where(available[:, None], proposed, state)
        logits = self.head(updated)
        return torch.where(available[:, None], logits, torch.zeros_like(logits)), updated


class AgentTemporalContext:
    """One instance per agent/run; weights may be shared, hidden tensors never are."""

    def __init__(self, agent_id: str, model: TemporalHead) -> None:
        if not agent_id.strip():
            raise ValueError("agent identity is required")
        self.agent_id = agent_id
        self.model = model
        self._state: Tensor | None = None
        self._tick = -1

    def reset(self) -> None:
        self._state = None
        self._tick = -1

    def observe(
        self, agent_id: str, tick: int, features: Tensor, available: bool
    ) -> TemporalPrediction:
        if agent_id != self.agent_id or tick <= self._tick:
            raise ValueError("temporal owner mismatch or non-increasing mission tick")
        if features.shape != (1, self.model.features):
            raise ValueError("agent context accepts one local feature vector")
        if self.model.training:
            raise ValueError("agent context requires inference-mode weights")
        state = self._state
        if state is None:
            state = features.new_zeros((1, self.model.hidden))
        mask = torch.tensor([available], device=features.device, dtype=torch.bool)
        with torch.inference_mode():
            logits, updated = self.model(features, mask, state)
            probabilities = logits.float().softmax(-1)
            entropy = -(probabilities * probabilities.clamp_min(1e-12).log()).sum(-1)
        self._state = updated.detach().clone()
        self._tick = tick
        return TemporalPrediction(logits, entropy, mask)
