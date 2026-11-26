"""Versioned dataset metadata; independent of mission wire protocol versions."""

from datetime import date
from pathlib import PureWindowsPath
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AfterValidator, AwareDatetime, Field, HttpUrl, model_validator

from agents.shared.domain import Evidence, Id, Record, Tick

Modality = Literal[
    "image", "video", "thermal", "audio", "text", "gps", "imu", "environment", "peer"
]
Split = Literal["train", "validation", "test"]
Origin = Literal["real", "synthetic"]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Positive = Annotated[int, Field(strict=True, gt=0)]
Status = Literal["unverified", "verified", "rejected"]


def relative_path(value: str) -> str:
    parts = value.split("/")
    if any(
        not part
        or part in {".", ".."}
        or part.endswith((" ", "."))
        or PureWindowsPath(part).is_reserved()
        or any(ord(c) < 32 or c in '<>:"\\|?*' for c in part)
        for part in parts
    ):
        raise ValueError("expected portable relative path using forward slashes")
    return value


Reference = Annotated[str, AfterValidator(relative_path)]


class Dataset(Record):
    dataset_id: Id
    name: Id
    origin: Origin
    version: Id | None = None
    source_organization: Id | None = None
    official_url: HttpUrl | None = None
    citation: str | None = None
    licence: Id | None = None
    licence_status: Status = "unverified"
    privacy_status: Literal["pending", "approved", "rejected"] = "pending"
    verification: Status = "unverified"
    privacy_considerations: str
    modalities: tuple[Modality, ...]
    annotation_types: tuple[Id, ...]
    tasks: tuple[Id, ...]
    label_definitions: dict[Id, str] = Field(default_factory=dict)
    sample_count: Tick | None = None
    file_formats: tuple[Id, ...] = ()
    estimated_bytes: Tick | None = None
    downloaded_bytes: Tick | None = None
    sha256: Digest | None = None
    download_status: Literal["not_downloaded", "partial", "available"] = "not_downloaded"
    limitations: str

    @model_validator(mode="after")
    def review(self) -> Self:
        if self.licence_status == "verified" and not self.licence:
            raise ValueError("verified licence requires a licence reference")
        return self


class Registry(Record):
    schema_version: Literal["1.0"]
    datasets: tuple[Dataset, ...]

    @model_validator(mode="after")
    def unique(self) -> Self:
        keys = [(d.dataset_id, d.version) for d in self.datasets]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate dataset id and version")
        return self


class Storage(Record):
    root: Annotated[str, Field(min_length=1, pattern=r"\S")]
    schema_version: Literal["1.0"]


class Asset(Record):
    path: Reference
    sha256: Digest
    availability: Literal["available", "missing", "unverified"]


class Annotation(Record):
    format: Literal["coco", "yolo", "voc", "mask", "csv", "json", "jsonl"]
    asset: Asset
    labels: tuple[Id, ...] = Field(min_length=1)
    label_schema_version: Id
    label_source: Id
    review_status: Literal["source", "unreviewed", "human_reviewed", "evaluator_truth"]
    review_ref: Id | None = None
    # Optional normalized index entries use source image pixel coordinates (x,y,w,h).
    boxes: tuple[tuple[float, float, float, float], ...] = ()
    box_labels: tuple[Id, ...] = ()
    numeric_targets: tuple[float, ...] = ()
    target_names: tuple[Id, ...] = ()
    target_units: tuple[Id, ...] = ()

    @model_validator(mode="after")
    def reviewed(self) -> Self:
        if self.review_status == "human_reviewed" and self.review_ref is None:
            raise ValueError("human review requires a decision or adjudication reference")
        if self.box_labels and len(self.box_labels) != len(self.boxes):
            raise ValueError("each detection box requires exactly one class label")
        if not (len(self.numeric_targets) == len(self.target_names) == len(self.target_units)):
            raise ValueError("numeric targets require matching names and units")
        return self


class Sample(Record):
    sample_id: Id
    source_ref: Id
    source_id: Id
    licence_ref: Id
    modality: Modality
    representation: Literal["physical", "symbolic"]
    split: Split
    asset: Asset | None = None
    evidence: tuple[Evidence, ...] = ()
    observation_id: UUID | None = None
    mission_id: UUID | None = None
    timestamp: AwareDatetime | None = None
    tick_ms: Tick | None = None
    retrieved_on: date | None = None
    scenario_id: Id | None = None
    seed: Tick | None = None
    sequence_id: Id | None = None
    location_group: Id | None = None
    event_id: Id | None = None
    incident_id: Id | None = None
    pair_id: Id | None = None
    missing_modalities: tuple[Modality, ...] = ()
    dimensions: tuple[Positive, Positive] | None = None
    sample_rate_hz: Positive | None = None
    source_rows: tuple[Positive, ...] = ()
    sensor_feature_names: tuple[Id, ...] = ()
    sensor_feature_units: tuple[Id, ...] = ()
    prediction_horizon: Positive | None = None
    prediction_horizon_unit: Literal["samples", "seconds", "minutes", "hours", "days"] | None = None
    annotation: Annotation | None = None

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if len(self.sensor_feature_names) != len(self.sensor_feature_units):
            raise ValueError("sensor features require units in the same order")
        if (self.prediction_horizon is None) != (self.prediction_horizon_unit is None):
            raise ValueError("prediction horizon requires a unit")
        if self.source_rows and tuple(sorted(set(self.source_rows))) != self.source_rows:
            raise ValueError("source rows must be unique and increasing")
        if (
            self.source_rows or self.sensor_feature_names or self.prediction_horizon is not None
        ) and self.modality != "environment":
            raise ValueError("sensor window metadata requires environmental samples")
        if self.modality in self.missing_modalities:
            raise ValueError("present modality also marked missing")
        if self.pair_id and {"image", "thermal"}.intersection(self.missing_modalities):
            raise ValueError("paired sample marks a partner missing")
        if self.representation == "symbolic":
            if self.asset or self.dimensions or self.sample_rate_hz:
                raise ValueError("symbolic evidence cannot describe physical media")
            if not self.evidence or self.tick_ms is None or not self.mission_id:
                raise ValueError("symbolic evidence requires mission, time and provenance")
            if len({e.evidence_id for e in self.evidence}) != len(self.evidence):
                raise ValueError("duplicate evidence identifier")
            if any(e.captured_ms > self.tick_ms for e in self.evidence):
                raise ValueError("evidence is newer than sample")
            if self.modality not in {e.modality for e in self.evidence}:
                raise ValueError("sample modality absent from evidence")
        elif self.asset is None:
            raise ValueError("physical sample requires an asset reference")
        if self.dimensions and self.modality not in {"image", "thermal", "video"}:
            raise ValueError("dimensions require a visual modality")
        if self.sample_rate_hz and self.modality != "audio":
            raise ValueError("sample rate requires audio")
        if self.annotation:
            if self.annotation.format == "mask" and not self.dimensions:
                raise ValueError("segmentation requires source dimensions")
            for x, y, w, h in self.annotation.boxes:
                if not self.dimensions or min(x, y) < 0 or min(w, h) <= 0:
                    raise ValueError("invalid bounding box")
                if x + w > self.dimensions[0] or y + h > self.dimensions[1]:
                    raise ValueError("bounding box outside image")
        return self


class Manifest(Record):
    schema_version: Literal["1.0", "1.1"]
    manifest_version: Id
    dataset_id: Id
    dataset_version: Id
    origin: Origin
    role: Literal["operational", "training_targets", "evaluator"]
    samples: tuple[Sample, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def boundary(self) -> Self:
        versioned_fields = any(
            sample.source_rows
            or sample.sensor_feature_names
            or sample.prediction_horizon is not None
            or sample.annotation is not None
            and (
                sample.annotation.box_labels
                or sample.annotation.numeric_targets
                or sample.annotation.target_names
                or sample.annotation.target_units
            )
            for sample in self.samples
        )
        if self.schema_version == "1.0" and versioned_fields:
            raise ValueError("new task target and sensor fields require manifest schema 1.1")
        for s in self.samples:
            if self.origin == "real":
                if s.representation != "physical" or not (s.sequence_id or s.location_group):
                    raise ValueError("real samples require physical data and location or sequence")
            elif s.scenario_id is None or s.seed is None:
                raise ValueError("synthetic samples require scenario and seed")
            if self.origin == "synthetic" and s.seed in range(42, 47) and s.split != "test":
                raise ValueError("reserved evaluation seed")
            if self.role == "operational" and s.annotation:
                raise ValueError("targets prohibited in operational manifests")
            if self.role != "operational" and s.annotation is None:
                raise ValueError("target manifests require annotations")
            if (
                s.annotation
                and s.annotation.review_status == "evaluator_truth"
                and self.role != "evaluator"
            ):
                raise ValueError("ground truth requires evaluator manifest")
        return self
