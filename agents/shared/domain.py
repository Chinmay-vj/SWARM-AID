"""Provider-neutral values. All coordinates use the mission's synthetic grid."""

from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Id = Annotated[str, StringConstraints(min_length=1, max_length=100, pattern=r"\S")]
Tick = Annotated[int, Field(strict=True, ge=0)]
Score = Annotated[float, Field(strict=True, ge=0, le=1)]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Category(StrEnum):
    ROUTINE = "routine"
    HAZARD = "hazard"
    POSSIBLE = "possible_human"
    UNCERTAIN = "uncertain_need"
    SUSPECTED = "suspected_emergency"
    CONFIRMED = "human_confirmed"


class DroneState(StrEnum):
    REGISTERING = "registering"
    READY = "ready"
    ACTIVE = "active"
    OFFLINE = "offline"
    SYNCING = "syncing"
    HOLD = "hold"
    ENDED = "ended"


class Cell(Record):
    x: Tick
    y: Tick


class Evidence(Record):
    evidence_id: UUID
    origin: Id
    captured_ms: Tick
    modality: Literal["image", "video", "thermal", "text", "gps", "imu", "environment", "peer"]
    artifact_key: Id


class Observation(Record):
    observation_id: UUID
    cell: Cell | None = None
    observed_ms: Tick
    confidence: Score
    evidence: Annotated[tuple[Evidence, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def check_lineage(self) -> Self:
        if any(item.captured_ms > self.observed_ms for item in self.evidence):
            raise ValueError("observation precedes its evidence")
        if len({item.evidence_id for item in self.evidence}) != len(self.evidence):
            raise ValueError("duplicate evidence reference")
        return self


class Finding(Record):
    """Agent-local meaning retained across perception, fusion, memory and assessment."""

    observation: Observation
    kind: Literal["environment", "hazard", "possible_human"]
    label: Id | None = None

    @model_validator(mode="after")
    def check_label(self) -> Self:
        if (self.kind == "possible_human") != (self.label is None):
            raise ValueError("environment and hazard findings require a feature or hazard label")
        return self


class ReportedFinding(Record):
    message_id: UUID
    finding: Finding


class SensorFrame(Record):
    agent_id: Id
    tick_ms: Tick
    samples: tuple[Evidence, ...]
    cell: Cell | None
    battery_fraction: Score

    @model_validator(mode="after")
    def check_samples(self) -> Self:
        if any(
            item.captured_ms > self.tick_ms or item.origin != self.agent_id for item in self.samples
        ):
            raise ValueError("frame requires current or earlier own-sensor samples")
        return self


class LocalView(Record):
    agent_id: Id
    tick_ms: Tick
    cell: Cell | None
    observations: tuple[Finding, ...]
    battery_fraction: Score


class Intent(StrEnum):
    SURVEY = "survey"
    REVISIT = "revisit"
    HOLD = "hold"
    END = "end"


class Action(Record):
    intent: Intent
    target: Cell | None = None

    @model_validator(mode="after")
    def check_target(self) -> Self:
        if (self.intent in (Intent.SURVEY, Intent.REVISIT)) != (self.target is not None):
            raise ValueError("survey and revisit require a target; hold and end take none")
        return self


class TaskLease(Record):
    task_id: UUID
    action: Action
    expires_ms: Tick


class SafetyContext(Record):
    state: DroneState
    lease: TaskLease | None
    offline_deadline_ms: Tick | None
    battery_reserve: Score
    prohibited_cells: tuple[Cell, ...]
    measured_frame: SensorFrame


class Incident(Record):
    incident_id: UUID
    revision: Annotated[int, Field(strict=True, ge=1)]
    category: Category
    reports: Annotated[tuple[UUID, ...], Field(min_length=1)]
    uncertainties: tuple[Id, ...]
    confirmation_id: UUID | None = None

    @model_validator(mode="after")
    def check_confirmation(self) -> Self:
        if (self.category == Category.CONFIRMED) != (self.confirmation_id is not None):
            raise ValueError("human-confirmed revisions require a human decision reference")
        return self


class Recommendation(Record):
    recommendation_id: UUID
    incident_id: UUID
    incident_revision: Annotated[int, Field(strict=True, ge=1)]
    request: Literal["inspect_evidence", "request_observation", "review_rescue_need"]
    evidence_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    unknowns: tuple[Id, ...]
    expires_ms: Tick
