from pathlib import Path
from typing import Literal, Self

from pydantic import Field, NonNegativeInt, PositiveInt, model_validator

from agents.shared.domain import Cell, Record, Score
from communication.network import Conditions


class Event(Record):
    step: PositiveInt
    cell: Cell
    terrain: str


class Scenario(Record):
    version: Literal["1"] = "1"
    scenario_id: str
    disaster: str
    width: PositiveInt = 12
    height: PositiveInt = 10
    seed: int = 42
    agents: PositiveInt = 6
    people: NonNegativeInt = 3
    hazards: NonNegativeInt = 2
    horizon: PositiveInt = 30
    tick_ms: PositiveInt = 100
    radius: NonNegativeInt = 2
    miss: Score = 0.1
    noise: Score = 0
    false_positive: Score = 0
    dropout: Score = 0
    latency: NonNegativeInt = 0
    modalities: tuple[Literal["image", "thermal", "gps", "imu", "environment", "text"], ...] = (
        "image",
        "thermal",
        "gps",
        "imu",
        "environment",
        "text",
    )
    unavailable: tuple[int, ...] = ()
    hidden_people: bool = False
    moving_people: bool = False
    radio_range: NonNegativeInt = 5
    loss: Score = 0
    delay: PositiveInt = 1
    outage_steps: tuple[int, ...] = ()
    network: Conditions = Conditions()
    partition: bool = False
    terrain: dict[str, tuple[Cell, ...]] = Field(default_factory=dict)
    events: tuple[Event, ...] = ()
    render: bool = False
    logging: bool = False

    @model_validator(mode="after")
    def geometry(self) -> Self:
        from simulation.environments.base import REGISTRY

        if self.disaster not in REGISTRY:
            raise ValueError("unknown disaster profile")
        cells = [c for group in self.terrain.values() for c in group]
        if any(
            c.x >= self.width or c.y >= self.height for c in cells + [e.cell for e in self.events]
        ):
            raise ValueError("cell outside grid")
        if len(set(cells)) != len(cells) or any(
            i < 0 or i >= self.agents for i in self.unavailable
        ):
            raise ValueError("overlapping terrain or unknown agent")
        blocked = sum(
            len(self.terrain.get(k, ()))
            for k in ("restricted", "building", "obstacle", "blocked", "debris", "damaged")
        )
        if max(self.people, self.agents, self.hazards) > self.width * self.height - blocked:
            raise ValueError("insufficient free cells")
        return self


def load(name: str) -> Scenario:
    path = Path(name)
    if not path.is_file():
        path = Path(__file__).resolve().parents[2] / "configs" / "scenarios" / (name + ".json")
    return Scenario.model_validate_json(path.read_bytes())
