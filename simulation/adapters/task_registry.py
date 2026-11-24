"""Episode-scoped task history, owned by the mock command endpoint."""

from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from agents.shared.domain import Cell

TaskState = Literal[
    "created",
    "available",
    "assigned",
    "in_progress",
    "completed",
    "expired",
    "requires_review",
    "failed",
    "cancelled",
]
TERMINAL = {"completed", "expired", "failed", "cancelled"}


@dataclass(frozen=True)
class TaskEvent:
    time_ms: int
    state: TaskState
    reason: str
    evidence: UUID | None = None


@dataclass
class SurveyTask:
    task_id: UUID
    mission_id: UUID
    member: str
    target: Cell
    created_ms: int
    expires_ms: int
    category: str = "search_sector"
    priority: int = 0
    version: str = "1"
    observation_refs: tuple[UUID, ...] = ()
    history: list[TaskEvent] = field(init=False)

    def __post_init__(self) -> None:
        if self.created_ms >= self.expires_ms:
            raise ValueError("empty task validity interval")
        self.history = [
            TaskEvent(self.created_ms, "created", "survey request"),
            TaskEvent(self.created_ms, "available", "authorized for assignment"),
            TaskEvent(self.created_ms, "assigned", "command issued lease"),
        ]

    def update(
        self, member: str, now: int, state: TaskState, reason: str, evidence: UUID | None = None
    ) -> None:
        previous = self.history[-1]
        if member != self.member or now < previous.time_ms:
            raise ValueError("unauthorized or stale update")
        if state == previous.state:
            return
        if (
            previous.state in TERMINAL
            or state in {"created", "available", "assigned"}
            or (state == "completed" and previous.state != "in_progress")
        ):
            raise ValueError("invalid task transition")
        if state == "expired" and now < self.expires_ms:
            raise ValueError("task is still valid")
        if now >= self.expires_ms and state != "expired":
            raise ValueError("expired task")
        if state == "completed" and evidence is None:
            raise ValueError("completion requires evidence")
        self.history.append(TaskEvent(now, state, reason, evidence))
