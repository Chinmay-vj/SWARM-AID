from dataclasses import dataclass

from simulation.environments.base import Point


@dataclass
class Person:
    entity_id: str
    position: Point
    visible: bool
    moving: bool
    scenario_role: str = "search_subject"


@dataclass
class Hazard:
    entity_id: str
    position: Point
    category: str
    severity: int = 1
    visible: bool = True
