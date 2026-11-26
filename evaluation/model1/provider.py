"""Explicit, agent-scoped classifier integration for the existing perception port."""

import io
from collections.abc import Mapping
from typing import Literal, Protocol, Self
from uuid import uuid5

import torch
from PIL import Image, ImageOps
from pydantic import model_validator
from torch import Tensor, nn

from agents.shared.domain import Evidence, Finding, Observation, Record, Score, SensorFrame


class PerceptionPrediction(Record):
    kind: Literal["environment", "hazard", "possible_human"]
    label: str | None = None
    confidence: Score

    @model_validator(mode="after")
    def preserve_human_uncertainty(self) -> Self:
        if (self.kind == "possible_human") != (self.label is None):
            raise ValueError("possible-human predictions cannot assert a label or distress")
        if self.label and self.label.casefold() in {"human_confirmed", "confirmed_distress"}:
            raise ValueError("perception cannot issue human confirmation or a distress decision")
        return self


class MediaResolver(Protocol):
    def resolve(self, agent_id: str, evidence: Evidence) -> bytes: ...


class Classifier:
    """Image classifier with explicit class-to-Finding semantics and no implicit labels."""

    def __init__(
        self,
        model: nn.Module,
        class_predictions: Mapping[int, PerceptionPrediction],
        *,
        image_size: int = 224,
        max_artifact_bytes: int = 64 * 1024 * 1024,
    ) -> None:
        if (
            image_size < 32
            or max_artifact_bytes < 1
            or not class_predictions
            or any(index < 0 for index in class_predictions)
        ):
            raise ValueError("classifier requires mapped classes and a supported image size")
        self.model = model
        self.class_predictions = dict(class_predictions)
        self.image_size = image_size
        self.max_artifact_bytes = max_artifact_bytes
        self.model.eval()

    def predict(self, artifact: bytes, modality: str) -> PerceptionPrediction:
        if modality not in {"image", "thermal", "video"}:
            raise ValueError("classifier only accepts image, thermal or video frame evidence")
        if not artifact or len(artifact) > self.max_artifact_bytes:
            raise ValueError("media artifact is empty or exceeds the configured byte limit")
        mode = "L" if modality == "thermal" else "RGB"
        with Image.open(io.BytesIO(artifact)) as source:
            image = (
                ImageOps.exif_transpose(source)
                .convert(mode)
                .resize((self.image_size, self.image_size), Image.Resampling.BILINEAR)
            )
            channels = 1 if mode == "L" else 3
            tensor = (
                torch.frombuffer(bytearray(image.tobytes()), dtype=torch.uint8)
                .reshape(self.image_size, self.image_size, channels)
                .permute(2, 0, 1)
                .to(torch.float32)
                .div_(255.0)
                .unsqueeze(0)
            )
        parameter = next(self.model.parameters(), None)
        if parameter is not None:
            tensor = tensor.to(parameter.device)
        with torch.inference_mode():
            output = self.model(tensor)
            if not isinstance(output, Tensor) or output.ndim != 2 or output.shape[0] != 1:
                raise ValueError("perception classifier must return [1, classes] logits")
            probabilities = output.softmax(dim=1)[0]
            class_id = int(probabilities.argmax())
            prediction = self.class_predictions.get(class_id)
            if prediction is None:
                raise ValueError("predicted class has no explicit Finding mapping")
            return PerceptionPrediction(
                kind=prediction.kind,
                label=prediction.label,
                confidence=float(probabilities[class_id]),
            )


class TrainedPerceptionProvider:
    """Uses only agent-owned evidence references and preserves their original lineage."""

    def __init__(
        self,
        agent_id: str,
        resolver: MediaResolver,
        classifier: Classifier,
        *,
        provider_id: str,
        task_id: str,
    ) -> None:
        if not agent_id.strip() or not provider_id.strip() or not task_id.strip():
            raise ValueError("agent, provider and task identifiers are required")
        self.agent_id = agent_id
        self.resolver = resolver
        self.classifier = classifier
        self.provider_id = provider_id
        self.task_id = task_id

    def perceive(self, frame: SensorFrame) -> tuple[Finding, ...]:
        if frame.agent_id != self.agent_id:
            raise ValueError("perception frame belongs to a different agent")
        findings: list[Finding] = []
        for evidence in frame.samples:
            if evidence.modality not in {"image", "thermal", "video"}:
                continue
            if evidence.origin != self.agent_id:
                raise ValueError("evidence origin does not match the provider owner")
            artifact = self.resolver.resolve(self.agent_id, evidence)
            prediction = self.classifier.predict(artifact, evidence.modality)
            findings.append(
                Finding(
                    observation=Observation(
                        observation_id=uuid5(
                            evidence.evidence_id,
                            f"{self.provider_id}/{self.task_id}/{evidence.modality}",
                        ),
                        cell=frame.cell,
                        observed_ms=frame.tick_ms,
                        confidence=prediction.confidence,
                        evidence=(evidence,),
                    ),
                    kind=prediction.kind,
                    label=prediction.label,
                )
            )
        return tuple(findings)
