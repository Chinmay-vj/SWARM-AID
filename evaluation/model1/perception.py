"""Unified inference over the registry, with task-specific semantics.

Segmentation pixel shares, class probabilities, detection scores and regression values
are different quantities and are reported as such. Flag thresholds are engineering
defaults for simulation and have not been validated.
"""

import io
from collections.abc import Mapping
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Literal, Protocol
from uuid import uuid5

import numpy as np
import torch
from PIL import Image, ImageOps
from pydantic import Field
from torch import Tensor

from agents.drone_agent.evidence import (
    Availability,
    Basis,
    EvidenceLedger,
    Status,
    StructuredEvidence,
)
from agents.shared.domain import Evidence, Finding, Observation, Record, Score, SensorFrame
from evaluation.model1.registry import ModelEntry, ModelRegistry, ModelUnavailable

FLAG_SHARE = 0.05
MIN_CONFIDENCE = 0.5
# Segmentation class -> simulator hazard vocabulary.
FLAGGED = {
    "rescuenet": {"building_major_damage": "damaged", "building_total_destruction": "damaged",
                  "building_minor_damage": "damaged", "road_blocked": "blocked"},
    "floodnet": {"building_flooded": "water", "road_flooded": "water"},
}


class Inference(Record):
    model_id: str
    model_version: str
    availability: Availability
    status: Status
    kind: Literal["environment", "hazard", "possible_human"] | None = None
    category: str | None = None
    quantity: float | None = None
    units: str | None = None
    confidence: Score | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    limitations: tuple[str, ...] = ()
    device: str = "none"
    precision: str = "none"


class ImageReuse:
    """Decoded forms of one artifact, shared by the models that consume it and then dropped.

    The tensors are shared: consumers must not modify them in place.
    """

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.decoded: Image.Image | None = None
        self.sized: dict[int, Tensor] = {}


def _decode(payload: bytes) -> Image.Image:
    if not payload or len(payload) > 64 * 1024 * 1024:
        raise ValueError("image is empty or too large")
    with Image.open(io.BytesIO(payload)) as source:
        return ImageOps.exif_transpose(source).convert("RGB")


def _image(payload: bytes, size: int, reuse: ImageReuse | None = None) -> Tensor:
    if reuse is not None and reuse.payload is not payload:
        raise ValueError("reuse belongs to a different artifact")
    if reuse is not None and size in reuse.sized:
        return reuse.sized[size]
    decoded = reuse.decoded if reuse is not None else None
    if decoded is None:
        decoded = _decode(payload)
    image = decoded.resize((size, size), Image.Resampling.BILINEAR)
    data = torch.frombuffer(bytearray(image.tobytes()), dtype=torch.uint8)
    result = data.reshape(size, size, 3).permute(2, 0, 1).float().div(255)
    if reuse is not None:
        reuse.decoded, reuse.sized[size] = decoded, result
    return result


def _normalized(image: Tensor, config: Mapping[str, Any]) -> Tensor:
    mean = torch.tensor(config["normalization_mean"]).reshape(3, 1, 1)
    scale = torch.tensor(config["normalization_scale"]).reshape(3, 1, 1)
    return ((image - mean) / scale).unsqueeze(0)


class PerceptionRuntime:
    def __init__(self, registry: ModelRegistry) -> None:
        self.registry = registry

    def _result(self, model_id: str, availability: Availability, status: Status = "not_assessed",
                **values: Any) -> Inference:
        entry = self.registry.entries.get(model_id)
        return Inference(
            model_id=model_id,
            model_version=(entry.sha256 or "none") if entry else "none",
            availability=availability,
            status=status,
            limitations=entry.limitations if entry else (),
            **values,
        )

    def infer(self, model_id: str, payload: Any) -> Inference:
        """Missing is never zero confidence; failures become explicit statuses."""
        state = self.registry.state(model_id)
        if state == "EXCLUDED":
            return self._result(model_id, "excluded")
        if state == "UNAVAILABLE":
            return self._result(model_id, "unavailable")
        if payload is None:
            return self._result(model_id, "missing")
        entry = self.registry.entries[model_id]
        try:
            inputs = self._prepare(entry, payload)
        except (ValueError, TypeError, OSError, KeyError) as exc:
            return self._result(model_id, "invalid", details={"error": type(exc).__name__})
        try:
            model: Any = self.registry.get(model_id)
        except ModelUnavailable as exc:
            return self._result(model_id, "unavailable", details={"error": str(exc)})
        device, precision = self.registry.device, self.registry.precision
        context = (
            torch.autocast("cuda", dtype=torch.float16 if precision == "fp16" else torch.bfloat16)
            if precision != "fp32" else nullcontext()
        )
        inputs = tuple(x.to(device) for x in inputs)
        with torch.inference_mode(), context:
            output = (model([inputs[0]]) if entry.task == "object_detection"
                      else model(*inputs))
        values = self._interpret(entry, output)
        return self._result(model_id, "available", device=device.type, precision=precision, **values)

    def _prepare(self, entry: ModelEntry, payload: Any) -> tuple[Tensor, ...]:
        task, config = entry.task, entry.config
        reuse = payload if isinstance(payload, ImageReuse) else None
        if reuse is not None:
            payload = reuse.payload
        if task in ("semantic_segmentation", "image_classification"):
            size = int(config["image_size"])
            return (_normalized(_image(payload, size, reuse), config),)
        if task == "object_detection":
            return (_image(payload, 512, reuse),)
        if task == "audio_classification":
            if isinstance(payload, Path):
                from evaluation.data.preprocessing import audio

                payload = audio(payload)["log_mel"]
            mel = torch.as_tensor(np.asarray(payload), dtype=torch.float32)
            if mel.ndim != 2 or min(mel.shape) < 16 or not torch.isfinite(mel).all():
                raise ValueError("audio requires a finite [time, mel] array")
            return (mel[None, None],)
        if task == "sensor_regression":
            raw = torch.as_tensor(np.asarray(payload, dtype=np.float32))
            if raw.ndim != 2 or raw.shape[1] != 8 or len(raw) != int(config["window"]):
                raise ValueError("sensor window has the wrong shape")
            available = torch.isfinite(raw) & (raw != -200)
            if not available.any():
                raise ValueError("sensor window has no measurements")
            mean = torch.tensor(config["normalization_mean"])
            scale = torch.tensor(config["normalization_scale"])
            values = torch.where(available, (raw - mean) / scale, torch.zeros_like(raw))
            return values[None], available[None]
        if task == "environment_fusion":
            features, available = payload
            return (torch.as_tensor(features, dtype=torch.float32)[None],
                    torch.as_tensor(available, dtype=torch.bool)[None])
        raise ValueError(f"unsupported task: {task}")

    def _interpret(self, entry: ModelEntry, output: Any) -> dict[str, Any]:
        task, labels = entry.task, entry.labels
        if task == "semantic_segmentation":
            probabilities = output["out"][0].float().softmax(0)
            best, winner = probabilities.max(0)
            # Count every class on the device, then synchronize once instead of per class.
            counts = torch.stack([(winner == i).sum() for i in range(len(labels))])
            shares = dict(zip(labels, (counts.float() / winner.numel()).tolist(), strict=True))
            hazards: dict[str, float] = {}
            for name, hazard in FLAGGED[entry.model_id].items():
                hazards[hazard] = hazards.get(hazard, 0.0) + shares.get(name, 0.0)
            top = max(hazards, key=lambda k: hazards[k])
            details: dict[str, Any] = {"pixel_share": shares,
                                       "meaning": "estimated scene categories"}
            if hazards[top] < FLAG_SHARE:
                return {"status": "accepted", "kind": "environment",
                        "category": "no_flagged_class", "confidence": float(best.mean()),
                        "details": details}
            selected = torch.zeros_like(winner, dtype=torch.bool)
            for i, name in enumerate(labels):
                if FLAGGED[entry.model_id].get(name) == top:
                    selected |= winner == i
            confidence = float(best[selected].mean())
            return {"status": "accepted" if confidence >= MIN_CONFIDENCE else "abstained",
                    "kind": "hazard", "category": top, "confidence": confidence,
                    "quantity": hazards[top], "units": "pixel_fraction", "details": details}
        if task in ("image_classification", "audio_classification"):
            probabilities = output[0].float().softmax(0)
            index = int(probabilities.argmax())
            confidence = float(probabilities[index])
            status = "accepted" if confidence >= MIN_CONFIDENCE else "abstained"
            if task == "audio_classification":
                # A sound class never establishes human presence or distress.
                return {"status": status, "kind": "environment",
                        "category": f"sound:{labels[index]}", "confidence": confidence}
            fire = labels[index] == "Fire"
            return {"status": status, "kind": "hazard" if fire else "environment",
                    "category": "fire" if fire else "no_fire_predicted", "confidence": confidence}
        if task == "sensor_regression":
            prediction, _ = output
            return {"status": "accepted", "kind": "environment", "category": "co_forecast",
                    "quantity": float(prediction[0, 0]), "units": entry.units}
        if task == "object_detection":
            scores = output[0]["scores"].float()
            kept = scores[scores >= MIN_CONFIDENCE]
            details = {"detections": len(kept), "meaning": "no detection never means clear"}
            if not len(kept):
                return {"status": "abstained", "details": details}
            return {"status": "accepted", "kind": "possible_human",
                    "confidence": float(kept.max()), "details": details}
        logits, valid = output
        if not bool(valid[0]):
            return {"status": "abstained"}
        probabilities = logits[0].float().softmax(0)
        index = int(probabilities.argmax())
        return {"status": "accepted", "kind": "environment", "category": labels[index],
                "confidence": float(probabilities[index])}


class MediaResolver(Protocol):
    def resolve(self, agent_id: str, evidence: Evidence) -> bytes | None: ...


class MediaPerception:
    """Per-agent PerceptionProvider over a shared runtime. Thermal frames are never inferred."""

    def __init__(
        self,
        runtime: PerceptionRuntime,
        resolver: MediaResolver,
        models: tuple[str, ...],
        ledger: EvidenceLedger,
        basis: Basis,
    ) -> None:
        if basis == "symbolic_simulator":
            raise ValueError("symbolic observations are not model inputs")
        self.runtime, self.resolver, self.models = runtime, resolver, models
        self.ledger, self.basis = ledger, basis

    def record(self, result: Inference, observed_ms: int, modality: str,
               evidence: Evidence | None) -> None:
        self.ledger.add(StructuredEvidence(
            evidence_id=evidence.evidence_id if evidence else None,
            agent_id=self.ledger.agent_id,
            episode_id=self.ledger.episode_id,
            observed_ms=observed_ms,
            basis=self.basis,
            modality=modality,
            model_id=result.model_id,
            model_version=result.model_version,
            availability=result.availability,
            status=result.status,
            category=result.category or result.kind,
            quantity=result.quantity,
            units=result.units,
            confidence=result.confidence,
            limitations=result.limitations,
            provenance=f"{self.basis}/{evidence.artifact_key if evidence else 'none'}",
        ))

    def perceive(self, frame: SensorFrame) -> tuple[Finding, ...]:
        if frame.agent_id != self.ledger.agent_id:
            raise ValueError("perception frame belongs to a different agent")
        findings: list[Finding] = []
        for evidence in frame.samples:
            if evidence.modality == "thermal":
                self.record(self.runtime.infer("wisard-thermal", None), frame.tick_ms,
                            "thermal", evidence)
                continue
            if evidence.modality not in ("image", "video"):
                continue
            artifact = self.resolver.resolve(frame.agent_id, evidence)
            # Sharing only helps with several models; a single model keeps the two-argument call.
            shared = (ImageReuse(artifact)
                      if artifact is not None and len(self.models) > 1 else artifact)
            for model_id in self.models:
                result = self.runtime.infer(model_id, shared)
                self.record(result, evidence.captured_ms, evidence.modality, evidence)
                if (result.availability != "available" or result.status != "accepted"
                        or result.kind is None or result.confidence is None):
                    continue
                findings.append(Finding(
                    kind=result.kind,
                    label=None if result.kind == "possible_human" else result.category,
                    observation=Observation(
                        observation_id=uuid5(evidence.evidence_id,
                                             f"{model_id}/{result.model_version}"),
                        cell=frame.cell,
                        observed_ms=evidence.captured_ms,
                        confidence=result.confidence,
                        evidence=(evidence,),
                    ),
                ))
        return tuple(findings)
