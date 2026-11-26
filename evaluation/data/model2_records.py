"""Offline command dataset v1. All operational values precede the decision cutoff."""

from typing import Literal, Self
from uuid import UUID, uuid5

from pydantic import Field, model_validator

from agents.shared.domain import (
    Category,
    Id,
    Incident,
    Recommendation,
    Record,
    ReportedFinding,
    Tick,
)
from evaluation.data.contracts import Modality, Split

Variant = Literal["native", "repeat", "relay", "stale", "conflict", "spurious"]
Relation = Literal["single", "duplicate", "corroborating", "conflicting", "related"]
Urgency = Literal["review_required", "elevated", "potentially_urgent"]


class Receipt(Record):
    report: ReportedFinding
    sender: Id
    session_id: UUID
    sent_ms: Tick
    received_ms: Tick

    @model_validator(mode="after")
    def chronology(self) -> Self:
        if not self.report.finding.observation.observed_ms <= self.sent_ms <= self.received_ms:
            raise ValueError("invalid report chronology")
        return self


def relation(current: Receipt, context: tuple[Receipt, ...]) -> Relation:
    f = current.report.finding
    obs = f.observation
    ids = {e.evidence_id for e in obs.evidence}
    origins = {e.origin for e in obs.evidence}
    corroborated = duplicate = False
    for receipt in context:
        other = receipt.report.finding
        old = other.observation
        if old.observation_id == obs.observation_id and other != f:
            return "conflicting"
        if other.kind == f.kind and old.cell == obs.cell and obs.cell is not None:
            if old.observed_ms == obs.observed_ms and other.label != f.label:
                return "conflicting"
            if other.label == f.label and origins.isdisjoint(e.origin for e in old.evidence):
                corroborated = True
        duplicate |= old.observation_id == obs.observation_id or bool(
            ids.intersection(e.evidence_id for e in old.evidence)
        )
    if duplicate:
        return "duplicate"
    if corroborated:
        return "corroborating"
    return "related" if context else "single"


class Input(Record):
    schema_version: Literal["1.0"] = "1.0"
    dataset_id: Literal["swarm-model2-symbolic"] = "swarm-model2-symbolic"
    episode_id: UUID
    mission_id: UUID
    scenario_id: Id
    seed: Tick
    agents: int = Field(gt=0)
    split: Split
    sample_id: UUID
    variant: Variant = "native"
    parent_id: UUID | None = None
    receipt: Receipt
    context: tuple[Receipt, ...]
    disabled_modalities: tuple[Modality, ...]
    communication: Literal["command_received", "controlled"]

    @property
    def age_ms(self) -> int:
        return self.receipt.received_ms - self.receipt.report.finding.observation.observed_ms

    @property
    def evidence_ids(self) -> set[UUID]:
        return {
            e.evidence_id
            for r in (*self.context, self.receipt)
            for e in r.report.finding.observation.evidence
        }

    @model_validator(mode="after")
    def boundary(self) -> Self:
        if self.seed in range(42, 47) and self.split != "test":
            raise ValueError("reserved seed")
        if any(r.received_ms > self.receipt.received_ms for r in self.context):
            raise ValueError("future context")
        if self.variant == "native":
            if self.parent_id or self.communication != "command_received":
                raise ValueError("invalid native source")
        elif not self.parent_id or self.communication != "controlled":
            raise ValueError("missing transformation provenance")
        source = self.parent_id or self.receipt.report.message_id
        if self.sample_id != uuid5(self.episode_id, f"{source}/{self.variant}"):
            raise ValueError("invalid sample identity")
        return self


class Features(Record):
    """Only the receipt history and time available at assessment are predictive inputs."""

    sample_id: UUID
    receipt: Receipt
    context: tuple[Receipt, ...]
    age_ms: Tick

    @classmethod
    def from_input(cls, row: Input) -> Self:
        return cls(
            sample_id=row.sample_id, receipt=row.receipt, context=row.context, age_ms=row.age_ms
        )


class Target(Record):
    label_version: Literal["1.0"] = "1.0"
    sample_id: UUID
    provenance: Literal["rule_derived", "unresolved", "human_reviewed"]
    relationship: Relation | None = None
    assessment: Category | None = None
    baseline_incident: Incident | None = None
    urgency: Urgency | None = None
    recommendation: Recommendation | None = None
    supporting: tuple[UUID, ...] = ()
    conflicting: tuple[UUID, ...] = ()
    uncertainty: tuple[Id, ...] = ()
    missing_information: tuple[Id, ...] = ()
    review_required: bool | None = None
    reviewer: Id | None = None
    revision: Tick = 0
    status: Literal["pending", "reviewed", "ambiguous"] = "pending"

    def check(self, sample: Input) -> None:
        if self.sample_id != sample.sample_id:
            raise ValueError("target source mismatch")
        if self.assessment == Category.CONFIRMED:
            raise ValueError("pilot lacks authorized human confirmation")
        refs = set(self.supporting) | set(self.conflicting)
        if refs - sample.evidence_ids or set(self.supporting) & set(self.conflicting):
            raise ValueError("invalid evidence attribution")
        rec = self.recommendation
        inc = self.baseline_incident
        if inc and (
            self.provenance != "rule_derived"
            or inc.category != self.assessment
            or not set(inc.reports)
            <= {r.report.message_id for r in (*sample.context, sample.receipt)}
        ):
            raise ValueError("invalid baseline incident")
        if (
            inc
            and rec
            and (inc.revision != rec.incident_revision or inc.incident_id != rec.incident_id)
        ):
            raise ValueError("recommendation targets wrong revision")
        if rec and (
            not set(rec.evidence_ids) <= set(self.supporting)
            or rec.expires_ms <= sample.receipt.received_ms
            or self.review_required is not True
        ):
            raise ValueError("unsupported or expired recommendation")
        if self.provenance == "human_reviewed":
            if not self.reviewer or not self.revision or self.status == "pending":
                raise ValueError("missing review provenance")
            if not (refs or self.uncertainty or self.missing_information):
                raise ValueError("review requires attribution or reason for abstaining")
        elif self.reviewer or self.revision or self.status != "pending":
            raise ValueError("spurious review provenance")
        if self.provenance == "unresolved" and (
            self.assessment or self.urgency or rec or self.supporting or self.conflicting
        ):
            raise ValueError("unresolved target asserts an assessment")
