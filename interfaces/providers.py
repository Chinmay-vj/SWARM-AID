"""Ports injected by the runner. An environment view is scoped to one drone."""

from typing import Protocol

from agents.shared.domain import (
    Action,
    Finding,
    Incident,
    Intent,
    LocalView,
    Recommendation,
    ReportedFinding,
    SafetyContext,
    SensorFrame,
    TaskLease,
)
from communication.messages import Envelope


class PerceptionProvider(Protocol):
    def perceive(self, frame: SensorFrame) -> tuple[Finding, ...]: ...


class SensorFusionProvider(Protocol):
    def fuse(self, frame: SensorFrame, reports: tuple[Finding, ...]) -> LocalView: ...


class ReasoningProvider(Protocol):
    def select_intent(self, view: LocalView) -> Intent: ...


class PlanningProvider(Protocol):
    def plan(self, view: LocalView, intent: Intent, lease: TaskLease | None) -> Action: ...


class CommunicationProvider(Protocol):
    async def send(self, message: Envelope) -> None: ...
    async def receive(self) -> Envelope: ...


class MemoryProvider(Protocol):
    def remember(self, observation: Finding) -> None: ...
    def recent(self, since_ms: int) -> tuple[Finding, ...]: ...


class EnvironmentProvider(Protocol):
    def observe(self) -> SensorFrame: ...
    def submit(self, allowed_action: Action) -> None: ...


class SafetyPolicy(Protocol):
    def constrain(self, proposed: Action, context: SafetyContext) -> Action: ...


class IncidentAssessmentProvider(Protocol):
    def assess(
        self, previous: Incident | None, reports: tuple[ReportedFinding, ...]
    ) -> Incident: ...


class RescueRecommendationProvider(Protocol):
    def recommend(
        self, incident: Incident, reports: tuple[ReportedFinding, ...]
    ) -> Recommendation: ...
