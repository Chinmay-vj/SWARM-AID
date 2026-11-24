from typing import ClassVar

from simulation.core.configuration import Scenario

Point = tuple[int, int]
BLOCKED = {"restricted", "obstacle", "building", "blocked", "damaged", "debris"}


class Disaster:
    ground: ClassVar[str] = "dry"
    hazard: ClassVar[str] = "water"

    def __init__(self, config: Scenario):
        self.tiles = {
            (x, y): self.ground for x in range(config.width) for y in range(config.height)
        }
        for kind, cells in config.terrain.items():
            self.tiles.update({(c.x, c.y): kind for c in cells})


class Flood(Disaster):
    pass


class Wildfire(Disaster):
    ground = "forest"
    hazard = "fire"


class Earthquake(Disaster):
    ground = "road"
    hazard = "debris"


REGISTRY: dict[str, type[Disaster]] = {
    "flood": Flood,
    "wildfire": Wildfire,
    "earthquake": Earthquake,
}
