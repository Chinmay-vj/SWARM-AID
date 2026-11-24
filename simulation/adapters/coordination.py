from dataclasses import dataclass
from typing import Literal
from uuid import UUID, uuid5

from agents.shared.coordination import MissionContext
from agents.shared.domain import Action, Cell, Intent, Observation
from communication.messages import (
    AgentHealth,
    EnvironmentalObservation,
    HazardDetection,
    MissionInstruction,
    PossibleHumanDetection,
    TaskStatus,
)
from interfaces.providers import CoordinationPolicy
from simulation.adapters.communications import SimulationNetwork
from simulation.adapters.task_registry import SurveyTask, TaskState

PolicyName = Literal["independent", "fixed_sector", "shared_information"]


def sector_cells(mission: MissionContext, member: str) -> list[Cell]:
    index = mission.members.index(member)
    cells = [Cell(x=x, y=y) for x in range(mission.width) for y in range(mission.height)]
    sector = [
        c
        for i, c in enumerate(cells)
        if i * len(mission.members) // len(cells) == index and c not in mission.restricted
    ]
    if member in dict(mission.sectors):
        sector = [c for c in dict(mission.sectors)[member] if c not in mission.restricted]
    return sector


@dataclass(frozen=True)
class Baseline:
    name: PolicyName

    def target(
        self, mission: MissionContext, member: str, round_index: int, reported: frozenset[Cell]
    ) -> Cell | None:
        if self.name == "independent":
            return None
        sector = sector_cells(mission, member)
        candidates = (
            [c for c in sector if c not in reported]
            if self.name == "shared_information"
            else sector
        )
        return candidates[round_index % len(candidates)] if candidates else None


class AssignmentFixture:
    """Issue finite survey leases using public geometry and admitted command reports."""

    def __init__(self, mission: MissionContext, policy: CoordinationPolicy, period_ms: int):
        if period_ms <= 0:
            raise ValueError("assignment period must be positive")
        self.mission = mission
        self.policy = policy
        self.period = period_ms
        self.transitions: list[tuple[int, str]] = [
            (0, "created"),
            (0, "initializing"),
            (0, "active"),
        ]
        self.issued = 0
        self.tasks: dict[UUID, SurveyTask] = {}
        self.current: dict[str, SurveyTask] = {}
        self.conflicts: list[tuple[int, UUID, str]] = []
        self.observations: dict[UUID, Observation] = {}
        self.repeated_reports = 0
        self.labels: dict[tuple[Cell, int], set[str]] = {}
        self.status_time: dict[UUID, tuple[int, int]] = {}
        self.last_health: dict[str, int] = {}
        self.availability: dict[str, str] = {member: "unknown" for member in mission.members}
        self.availability_history: list[tuple[int, str, str]] = []
        self.cursor = 0
        self.reported: set[Cell] = set()

    def command_snapshot(self) -> dict[str, object]:
        """Copy command-visible evidence and task dispositions for a future consumer."""
        return {
            "mission_id": str(self.mission.mission_id),
            "objective": self.mission.objective,
            "status": self.transitions[-1][1],
            "availability": dict(self.availability),
            "reported_cells": sorted((c.x, c.y) for c in self.reported),
            "observations": [o.model_dump(mode="json") for o in self.observations.values()],
            "task_states": {str(k): v.history[-1].state for k, v in self.tasks.items()},
            "conflicts": [(now, str(mid), reason) for now, mid, reason in self.conflicts],
        }

    def transition(self, now: int, state: str) -> None:
        allowed = {
            "active": {"paused", "degraded", "completed", "aborted"},
            "paused": {"active", "aborted", "completed"},
            "degraded": {"active", "paused", "completed", "aborted"},
        }
        tick, previous = self.transitions[-1]
        if now < tick or state not in allowed.get(previous, set()):
            raise ValueError("invalid mission transition")
        self.transitions.append((now, state))

    def advance(self, network: SimulationNetwork, now: int) -> None:
        state = self.transitions[-1][1]
        if state in {"active", "degraded"}:
            desired = (
                "active"
                if network.router.endpoints["command"].state.value == "connected"
                else "degraded"
            )
            if desired != state:
                self.transition(now, desired)
        history = network.history["command"]
        for envelope in history[self.cursor :]:
            payload = envelope.payload
            if isinstance(
                payload, (EnvironmentalObservation, HazardDetection, PossibleHumanDetection)
            ):
                observation = payload.observation
                original = self.observations.get(observation.observation_id)
                if original is not None:
                    self.repeated_reports += 1
                    if original != observation:
                        self.conflicts.append(
                            (now, envelope.message_id, "conflicting observation identity")
                        )
                        continue
                else:
                    self.observations[observation.observation_id] = observation
                if payload.observation.cell is None:
                    continue
                self.reported.add(payload.observation.cell)
                if isinstance(payload, EnvironmentalObservation):
                    labels = self.labels.setdefault(
                        (payload.observation.cell, observation.observed_ms), set()
                    )
                    if labels and payload.feature not in labels:
                        self.conflicts.append(
                            (now, envelope.message_id, "conflicting environmental reports")
                        )
                    labels.add(payload.feature)
            if isinstance(payload, AgentHealth):
                self.last_health[envelope.source] = max(
                    envelope.sent_ms, self.last_health.get(envelope.source, -1)
                )
            task = self.current.get(envelope.source)
            try:
                if isinstance(payload, TaskStatus):
                    task = self.tasks.get(payload.task_id)
                    if task is None:
                        raise ValueError("unknown task")
                    if task.member != envelope.source:
                        raise ValueError("foreign task status")
                    stamp = (envelope.sent_ms, envelope.sequence)
                    if stamp <= self.status_time.get(task.task_id, (-1, -1)):
                        raise ValueError("stale task status")
                    self.status_time[task.task_id] = stamp
                    next_state: TaskState = (
                        "in_progress"
                        if payload.status in ("accepted", "active")
                        else "requires_review"
                    )
                    if task.history[-1].state != "completed":
                        task.update(envelope.source, now, next_state, payload.status)
                elif (
                    isinstance(payload, AgentHealth)
                    and task
                    and task.history[-1].state == "in_progress"
                    and payload.cell == task.target
                    and envelope.sent_ms > task.created_ms
                ):
                    task.update(
                        envelope.source,
                        now,
                        "completed",
                        "reported at survey cell",
                        envelope.message_id,
                    )
            except ValueError as exc:
                self.conflicts.append((now, envelope.message_id, str(exc)))
        self.cursor = len(history)
        self.expire(now)
        for member in self.mission.members:
            last = self.last_health.get(member)
            availability = (
                "unknown"
                if last is None
                else "stale"
                if now - last >= network.router.config.heartbeat_ms
                else "available"
            )
            if availability != self.availability[member]:
                self.availability_history.append((now, member, availability))
                self.availability[member] = availability
                affected = self.current.get(member)
                if (
                    availability == "stale"
                    and affected
                    and affected.history[-1].state in {"assigned", "in_progress"}
                ):
                    affected.update(member, now, "requires_review", "status heartbeat stale")
        if (
            self.transitions[-1][1] != "active"
            or now % self.period
            or now >= self.mission.end_ms
            or network.router.endpoints["command"].state.value != "connected"
        ):
            return
        for member in self.mission.members:
            target = self.policy.target(
                self.mission, member, now // self.period, frozenset(self.reported)
            )
            if target is None:
                continue
            if (
                target in self.mission.restricted
                or target.x >= self.mission.width
                or target.y >= self.mission.height
            ):
                self.conflicts.append(
                    (
                        now,
                        uuid5(self.mission.mission_id, f"proposal/{member}/{now}"),
                        "unauthorized survey cell",
                    )
                )
                continue
            task_id = uuid5(self.mission.mission_id, f"survey/{member}/{now}")
            task = SurveyTask(
                task_id,
                self.mission.mission_id,
                member,
                target,
                now,
                min(now + self.period, self.mission.end_ms),
            )
            self.tasks[task_id] = self.current[member] = task
            network.issue(
                "command",
                MissionInstruction(
                    message_type="mission_instruction",
                    task_id=task_id,
                    action=Action(intent=Intent.SURVEY, target=target),
                ),
                member,
                min(now + self.period, self.mission.end_ms),
            )
            self.issued += 1

    def expire(self, now: int) -> None:
        for task in self.current.values():
            if now >= task.expires_ms and task.history[-1].state in {
                "assigned",
                "in_progress",
                "requires_review",
            }:
                task.update(task.member, now, "expired", "validity ended")
