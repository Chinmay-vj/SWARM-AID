from collections import deque
from typing import Literal
from uuid import UUID, uuid5

from pydantic import PositiveInt

from agents.shared.domain import Cell, DroneState, Finding, Id, Record, Score
from simulation.sensors.mock import Packet, Reading


class Settings(Record):
    agent_id: Id = "template"
    modalities: tuple[str, ...] = ("image", "thermal", "environment", "gps", "imu", "text", "video")
    perception: Literal["mock"] = "mock"
    fusion: Literal["mock"] = "mock"
    reasoning: Literal["rules"] = "rules"
    planning: Literal["bounded"] = "bounded"
    communication: Literal["memory"] = "memory"
    capacity: PositiveInt = 128
    ttl_ms: PositiveInt = 3000
    reserve: Score = 0.22
    logging: bool = True
    movement: bool = False


class Input(Record):
    version: Literal["1"] = "1"
    mission_id: UUID
    agent_id: Id
    representation: Literal["symbolic", "fixture", "media"] = "symbolic"
    coordinates: Literal["mission_grid"] = "mission_grid"
    units: str = "grid cells"
    reading: Reading


class Inputs:
    def __init__(self) -> None:
        self.current: dict[UUID, Input] = {}

    def ingest(self, p: Packet, a: str, mission: UUID, now: int, c: Settings) -> None:
        self.current.clear()
        if p.frame.agent_id != a or not 0 <= now - p.frame.tick_ms <= c.ttl_ms:
            raise ValueError("foreign or stale frame")
        refs = {e.evidence_id: e for e in p.frame.samples}
        for r in p.readings:
            e = r.evidence
            if refs.get(e.evidence_id) != e or e.origin != a or not 0 <= r.confidence <= 1:
                raise ValueError("invalid reading")
            if e.modality in c.modalities and now - e.captured_ms <= c.ttl_ms:
                normalized = Input(mission_id=mission, agent_id=a, reading=r)
                previous = self.current.setdefault(e.evidence_id, normalized)
                if previous != normalized:
                    raise ValueError("conflicting evidence ID")


class MemoryImage(Record):
    owner: Id
    mission: UUID
    findings: tuple[Finding, ...]


class Memory:
    def __init__(self, owner: str, mission: UUID, settings: Settings):
        self.owner = owner
        self.mission = mission
        self.settings = settings
        self.items: dict[UUID, Finding] = {}

    def remember(self, observation: Finding) -> None:
        self.items.setdefault(observation.observation.observation_id, observation)
        while len(self.items) > self.settings.capacity:
            del self.items[next(iter(self.items))]

    def recent(self, since_ms: int) -> tuple[Finding, ...]:
        return tuple(f for f in self.items.values() if f.observation.observed_ms >= since_ms)

    def expire(self, now: int) -> None:
        self.items = {
            f.observation.observation_id: f for f in self.recent(now - self.settings.ttl_ms)
        }

    def snapshot(self) -> str:
        return MemoryImage(
            owner=self.owner, mission=self.mission, findings=tuple(self.items.values())
        ).model_dump_json()

    def restore(self, data: str) -> None:
        image = MemoryImage.model_validate_json(data)
        if (image.owner, image.mission) != (self.owner, self.mission):
            raise ValueError("wrong memory scope")
        self.items.clear()
        for f in image.findings:
            self.remember(f)


class World:
    def __init__(self, memory: Memory):
        self.memory = memory

    def at(self, cell: Cell) -> tuple[Finding, ...]:
        return tuple(f for f in self.memory.items.values() if f.observation.cell == cell)

    def snapshot(self) -> str:
        return self.memory.snapshot()


class Lifecycle:
    def __init__(self, mission: UUID, owner: str, capacity: int):
        self.state = DroneState.REGISTERING
        self.history: deque[dict[str, object]] = deque(maxlen=capacity)
        self.scope = uuid5(mission, owner)

    def change(self, state: DroneState, now: int, reason: str) -> None:
        if self.state == state:
            return
        allowed = {
            DroneState.REGISTERING: {DroneState.READY},
            DroneState.READY: {DroneState.ACTIVE, DroneState.HOLD},
            DroneState.ACTIVE: {DroneState.HOLD, DroneState.READY},
            DroneState.HOLD: {DroneState.READY},
        }
        if (
            self.state == DroneState.ENDED
            or state != DroneState.ENDED
            and state not in allowed.get(self.state, set())
        ):
            raise ValueError("invalid lifecycle transition")
        self.history.append(
            {
                "event_id": str(uuid5(self.scope, f"{now}/{self.state}/{state}")),
                "previous": self.state,
                "new": state,
                "time_ms": now,
                "reason": reason,
            }
        )
        self.state = state


class Health:
    def __init__(self) -> None:
        self.battery_fraction: float | None = None
        self.online = False
        self.memory_entries = 0
        self.missing_modalities: tuple[str, ...] = ()
        self.invalid_inputs = 0
        self.provider_errors = 0
        self.invalid_actions = 0
        self.last_success_ms: int | None = None
        self.status = "healthy"
