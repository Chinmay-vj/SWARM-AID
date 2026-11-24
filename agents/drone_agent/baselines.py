from uuid import uuid5

from agents.drone_agent.components import Inputs
from agents.shared.domain import (
    Action,
    Finding,
    Intent,
    LocalView,
    Observation,
    SensorFrame,
    TaskLease,
)

HAZARDS = {
    "fire",
    "smoke",
    "water",
    "debris",
    "damaged",
    "obstacle",
    "blocked",
    "restricted",
    "building",
}


class Detection(Finding):
    provider: str = "mock-symbolic/1"
    confidence_basis: str = "synthetic uncalibrated score"
    location_uncertainty_cells: int | None = None


class MockPerception:
    def __init__(self, inputs: Inputs):
        self.inputs = inputs

    def perceive(self, frame: SensorFrame) -> tuple[Finding, ...]:
        out = []
        for e in frame.samples:
            item = self.inputs.current.get(e.evidence_id)
            if item is None or e.modality not in ("image", "thermal", "environment"):
                continue
            r = item.reading
            person = r.value == "possible_human"
            out.append(
                Detection(
                    kind="possible_human"
                    if person
                    else "hazard"
                    if r.value in HAZARDS
                    else "environment",
                    label=None if person else r.value,
                    observation=Observation(
                        observation_id=uuid5(e.evidence_id, "mock-v1"),
                        cell=r.cell,
                        observed_ms=e.captured_ms,
                        confidence=r.confidence,
                        evidence=(e,),
                    ),
                )
            )
        return tuple(out)


class Fusion:
    def fuse(self, frame: SensorFrame, reports: tuple[Finding, ...]) -> LocalView:
        groups: dict[tuple[object, ...], list[Finding]] = {}
        for f in reports:
            o = f.observation
            groups.setdefault((f.kind, f.label, o.cell, o.observed_ms), []).append(f)
        findings = []
        for group in groups.values():
            first = group[0]
            refs = {e.evidence_id: e for f in group for e in f.observation.evidence}
            obs = first.observation.model_copy(
                update={
                    "evidence": tuple(refs.values()),
                    "confidence": min(f.observation.confidence for f in group),
                }
            )
            findings.append(first.model_copy(update={"observation": obs}))
        return LocalView(
            agent_id=frame.agent_id,
            tick_ms=frame.tick_ms,
            cell=frame.cell,
            battery_fraction=frame.battery_fraction,
            observations=tuple(findings),
        )


class Rules:
    def select_intent(self, view: LocalView) -> Intent:
        return Intent.SURVEY if view.cell and view.observations else Intent.HOLD


class Planner:
    def plan(self, view: LocalView, intent: Intent, lease: TaskLease | None) -> Action:
        if lease and intent == Intent.SURVEY:
            return lease.action
        return Action(intent=Intent.HOLD)
