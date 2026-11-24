from dataclasses import dataclass
from uuid import UUID

from agents.shared.domain import Cell


@dataclass(frozen=True)
class MissionContext:
    mission_id: UUID
    members: tuple[str, ...]
    width: int
    height: int
    restricted: frozenset[Cell]
    end_ms: int
    disaster: str = "flood"
    objective: str = "Survey authorized cells and report synthetic evidence"
    version: str = "1"
    start_ms: int = 0
    sectors: tuple[tuple[str, tuple[Cell, ...]], ...] = ()
    priorities: tuple[Cell, ...] = ()
    known_references: tuple[UUID, ...] = ()
