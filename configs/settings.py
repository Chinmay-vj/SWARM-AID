"""Load and validate an explicit experiment configuration."""

import tomllib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from agents.shared.domain import Record, Score, Tick


class Settings(Record):
    schema_version: Literal["1.0"]
    seed: Tick
    tick_ms: Annotated[int, Field(strict=True, gt=0)]
    offline_budget_ms: Tick
    battery_reserve: Score
    scenario: Literal["flood", "forest_fire", "earthquake", "landslide", "cyclone"]


def load_settings(path: Path) -> Settings:
    with path.open("rb") as stream:
        return Settings.model_validate(tomllib.load(stream))


if __name__ == "__main__":
    print(load_settings(Path(__file__).with_name("default.toml")).model_dump_json(indent=2))
