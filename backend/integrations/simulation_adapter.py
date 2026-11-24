"""Validated construction of seeded simulator, Model 1 fleet and Model 2 instances.

The backend only selects among existing scenario fixtures and whitelisted overrides. Client
input never becomes a filesystem path.
"""

import re
import threading
from functools import cache
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from agents.command_agent.agent import Settings as CommandSettings
from agents.shared.domain import Cell
from simulation.adapters.coordination import PolicyName, sector_cells
from simulation.adapters.model1 import Fleet
from simulation.core.configuration import Scenario
from simulation.core.engine import Engine

SCENARIO_DIR = Path(__file__).resolve().parents[2] / "configs" / "scenarios"
SCENARIO_NAME = re.compile(r"^[a-z0-9_]{1,64}$")


@cache
def available_scenarios() -> frozenset[str]:
    return frozenset(p.stem for p in SCENARIO_DIR.glob("*.json") if SCENARIO_NAME.match(p.stem))


class MissionConfig(BaseModel):
    """Whitelisted simulation configuration accepted from authorized clients."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    agents: int = Field(default=6, ge=1, le=20)
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    horizon: int | None = Field(default=None, ge=1, le=5000)
    coordination: PolicyName = "shared_information"
    command_mode: Literal["direct", "rules", "fusion"] = "fusion"
    outage_steps: tuple[int, ...] = Field(default=(), max_length=500)

    @field_validator("scenario_id")
    @classmethod
    def known_scenario(cls, value: str) -> str:
        if not SCENARIO_NAME.match(value) or value not in available_scenarios():
            raise ValueError("unknown scenario identifier")
        return value

    def scenario(self) -> Scenario:
        base = Scenario.model_validate_json(
            (SCENARIO_DIR / f"{self.scenario_id}.json").read_bytes()
        )
        overrides: dict[str, object] = {"agents": self.agents, "seed": self.seed}
        if self.horizon is not None:
            overrides["horizon"] = self.horizon
        if self.outage_steps:
            overrides["outage_steps"] = tuple(
                sorted(set(base.outage_steps) | set(self.outage_steps))
            )
        return Scenario.model_validate(base.model_dump() | overrides)

    def validated(self) -> Scenario:
        try:
            scenario = self.scenario()
            Engine(scenario)  # placement and geometry checks
        except (ValidationError, ValueError) as exc:
            raise ValueError(f"scenario configuration rejected: {exc}") from exc
        return scenario


class SimulationContext:
    """One mission execution: engine, Model 1 fleet with transport, and one Model 2 instance."""

    def __init__(self, config: MissionConfig) -> None:
        self.config = config
        self.scenario = config.validated()
        self.engine = Engine(self.scenario)
        self.fleet = Fleet(
            self.engine,
            communication=True,
            coordination=config.coordination,
            command=CommandSettings(mode=config.command_mode),
        )
        if self.fleet.network is None or self.fleet.command is None:
            raise RuntimeError("fleet integration requires transport and command")
        self.network = self.fleet.network
        self.command = self.fleet.command
        self.lock = threading.RLock()

    @property
    def sim_mission_id(self) -> UUID:
        return self.engine.mission_id

    @property
    def now_ms(self) -> int:
        return self.engine.t * self.scenario.tick_ms

    @property
    def finished(self) -> bool:
        return self.engine.reason != "running"

    def step(self) -> None:
        with self.lock:
            if not self.finished:
                self.fleet.advance(self.engine)

    def sectors(self) -> dict[str, list[Cell]]:
        fixture = self.fleet.assignments
        if fixture is None or self.config.coordination == "independent":
            return {}
        return {m: sector_cells(fixture.mission, m) for m in fixture.mission.members}

    def message_id(self, kind: str, *parts: object) -> UUID:
        return uuid5(self.sim_mission_id, "/".join([kind, *map(str, parts)]))
