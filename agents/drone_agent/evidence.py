"""Torch-free structured evidence and deterministic symbolic environmental fusion.

Wire contracts are unchanged. A ledger keyed by the original evidence ID carries model
identity and limitations beside the Findings that travel to Model 2.
"""

from collections import deque
from collections.abc import Iterable
from typing import Literal
from uuid import UUID

from agents.shared.domain import Cell, Finding, Id, Record, Score, SensorFrame
from interfaces.providers import PerceptionProvider

Basis = Literal[
    "model_inference", "symbolic_simulator", "synthetic_fixture", "approved_development_input"
]
Availability = Literal["available", "missing", "invalid", "unavailable", "excluded"]
Status = Literal["accepted", "abstained", "conflict", "not_assessed"]


class StructuredEvidence(Record):
    """One observed or model-estimated item. Never a confirmation of need or safety."""

    evidence_id: UUID | None
    agent_id: Id
    episode_id: UUID
    observed_ms: int
    basis: Basis
    modality: Id
    model_id: Id
    model_version: Id
    availability: Availability
    status: Status
    category: Id | None = None
    quantity: float | None = None
    units: Id | None = None
    confidence: Score | None = None
    limitations: tuple[Id, ...] = ()
    provenance: Id


class EvidenceLedger:
    """Bounded, agent-owned and episode-scoped."""

    def __init__(self, agent_id: str, episode_id: UUID, capacity: int = 512) -> None:
        self.agent_id, self.episode_id = agent_id, episode_id
        self.items: deque[StructuredEvidence] = deque(maxlen=capacity)
        self.assessments: deque[CellAssessment] = deque(maxlen=capacity)

    def add(self, item: StructuredEvidence) -> None:
        if (item.agent_id, item.episode_id) != (self.agent_id, self.episode_id):
            raise ValueError("evidence belongs to another agent or episode")
        if item not in self.items:
            self.items.append(item)

    def lookup(self, evidence_id: UUID) -> tuple[StructuredEvidence, ...]:
        return tuple(i for i in self.items if i.evidence_id == evidence_id)

    def reset(self, episode_id: UUID) -> None:
        self.items.clear()
        self.assessments.clear()
        self.episode_id = episode_id


class RecordingPerception:
    """Wraps the symbolic provider and records its output as symbolic, not model, evidence."""

    def __init__(self, inner: PerceptionProvider, ledger: EvidenceLedger) -> None:
        self.inner, self.ledger = inner, ledger

    def perceive(self, frame: SensorFrame) -> tuple[Finding, ...]:
        findings = self.inner.perceive(frame)
        # Deterministic fusion annotates the evidence; it never changes the findings.
        self.ledger.assessments.extend(fuse_environment(findings))
        for finding in findings:
            observation = finding.observation
            for source in observation.evidence:
                self.ledger.add(
                    StructuredEvidence(
                        evidence_id=source.evidence_id,
                        agent_id=self.ledger.agent_id,
                        episode_id=self.ledger.episode_id,
                        observed_ms=observation.observed_ms,
                        basis="symbolic_simulator",
                        modality=source.modality,
                        model_id="mock-symbolic",
                        model_version="1",
                        availability="available",
                        status="accepted",
                        category=finding.label or finding.kind,
                        confidence=observation.confidence,
                        limitations=("synthetic uncalibrated score",),
                        provenance=f"simulator/{source.artifact_key}",
                    )
                )
        return findings


# Parity with evaluation.model1.environment_fusion is tested. "routine" means other known
# reference terrain, never a declaration of safety.
ROUTINE = ("base", "dry", "forest", "road", "trail", "building", "obstacle", "restricted",
           "weak_radio", "burned", "silt", "slope")
CATEGORIES = {
    **dict.fromkeys(ROUTINE, "routine"), "water": "water", "fire": "fire", "smoke": "fire",
    "thermal_anomaly": "fire", "damaged": "damage", "debris": "damage", "blocked": "damage",
}
ENVIRONMENT_MODES = ("image", "thermal", "environment")
STRONG_SHARE, STRONG_CONFIDENCE = 0.8, 0.5


class CellAssessment(Record):
    """Inferred from observations at one cell and time; separate from the observations."""

    cell: Cell
    observed_ms: int
    status: Status
    category: Literal["routine", "water", "fire", "damage"] | None
    confidence: Score | None
    modalities: tuple[Id, ...]
    missing_modalities: tuple[Id, ...]
    evidence_ids: tuple[UUID, ...]
    basis: Literal["deterministic_inference"] = "deterministic_inference"


def fuse_environment(findings: Iterable[Finding]) -> tuple[CellAssessment, ...]:
    """Majority vote per modality; abstain on conflict or no known evidence."""
    groups: dict[tuple[int, int, int], list[Finding]] = {}
    for finding in findings:
        o = finding.observation
        if o.cell is not None and finding.kind != "possible_human":
            groups.setdefault((o.cell.x, o.cell.y, o.observed_ms), []).append(finding)
    results = []
    for (x, y, observed_ms), group in sorted(groups.items()):
        votes: dict[str, dict[str, float]] = {}
        counts: dict[str, int] = {}
        scores: dict[str, float] = {}
        identifiers: dict[UUID, None] = {}
        seen: set[UUID] = set()
        for finding in group:
            o = finding.observation
            category = CATEGORIES.get(finding.label or "")
            mode: str = o.evidence[0].modality
            if category is None or mode not in ENVIRONMENT_MODES or o.observation_id in seen:
                continue
            seen.add(o.observation_id)
            identifiers.update(dict.fromkeys(e.evidence_id for e in o.evidence))
            tally = votes.setdefault(mode, {})
            tally[category] = tally.get(category, 0.0) + o.confidence
            counts[mode] = counts.get(mode, 0) + 1
            scores[mode] = scores.get(mode, 0.0) + o.confidence
        strong = set()
        totals: dict[str, float] = {}
        for mode, tally in votes.items():
            mass = sum(tally.values())
            winner = max(tally, key=lambda k: tally[k])
            confidence = scores[mode] / counts[mode]
            if mass > 0 and tally[winner] >= STRONG_SHARE * mass and confidence >= STRONG_CONFIDENCE:
                strong.add(winner)
            for category, value in tally.items():
                totals[category] = totals.get(category, 0.0) + value / counts[mode]
        usable = any(v > 0 for v in totals.values())
        status: Status = (
            "conflict" if len(strong) > 1 else "accepted" if usable else "abstained"
        )
        chosen = max(totals, key=lambda k: totals[k]) if status == "accepted" else None
        results.append(
            CellAssessment.model_validate({
                "cell": Cell(x=x, y=y),
                "observed_ms": observed_ms,
                "status": status,
                "category": chosen,
                "confidence": min(1.0, totals[chosen] / sum(totals.values())) if chosen else None,
                "modalities": tuple(sorted(votes)),
                "missing_modalities": tuple(m for m in ENVIRONMENT_MODES if m not in votes),
                "evidence_ids": tuple(identifiers),
            })
        )
    return tuple(results)
