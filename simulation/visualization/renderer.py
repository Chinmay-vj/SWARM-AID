import pygame

from simulation.core.engine import Engine

COLORS = {
    "water": "steelblue",
    "fire": "orange",
    "smoke": "gray",
    "forest": "forestgreen",
    "debris": "brown",
    "restricted": "purple",
    "base": "white",
    "building": "sienna",
    "road": "gray",
    "blocked": "black",
    "obstacle": "black",
    "damaged": "brown",
    "weak_radio": "khaki",
}


class Renderer:
    def __init__(self) -> None:
        pygame.init()
        self.surface = pygame.display.set_mode((800, 600))
        self.font = pygame.font.Font(None, 20)

    def draw(self, e: Engine, agent: str | None) -> None:
        size = max(1, min(780 // e.config.width, 490 // e.config.height))
        self.surface.fill("black")
        packet = e.views.get(agent) if agent else None
        tiles = (
            e.world.tiles
            if agent is None
            else {
                (r.cell.x, r.cell.y): r.value
                for r in packet.readings
                if r.cell and r.value in COLORS.keys() | {"dry"}
            }
            if packet
            else {}
        )
        people = (
            list(e.people)
            if agent is None
            else [
                (r.cell.x, r.cell.y)
                for r in packet.readings
                if r.cell and r.value == "possible_human"
            ]
            if packet
            else []
        )
        for (x, y), tile in tiles.items():
            pygame.draw.rect(
                self.surface, COLORS.get(tile, "tan"), (x * size, y * size, size - 1, size - 1)
            )
            if agent is None and (x, y) in e.covered:
                pygame.draw.rect(self.surface, "cyan", (x * size, y * size, size, size), 1)
        for x, y in people:
            pygame.draw.circle(
                self.surface, "red", (x * size + size // 2, y * size + size // 2), max(1, size // 5)
            )
        locations = (
            {a: (d.position, d.battery) for a, d in e.drones.items()}
            if agent is None
            else {
                agent: (
                    (packet.frame.cell.x, packet.frame.cell.y),
                    round(packet.frame.battery_fraction * 100),
                )
            }
            if packet and packet.frame.cell
            else {}
        )
        for a, ((x, y), battery) in locations.items():
            self.surface.blit(
                self.font.render(f"{a} {battery}", True, "blue"), (x * size, y * size)
            )
        title = (
            f"DEBUG TRUTH  step {e.t}  coverage {len(e.covered) / len(e.world.tiles):.0%}  {e.events[-2:]}"
            if agent is None
            else f"AGENT {agent}  sample ms {packet.frame.tick_ms if packet else 'unavailable'}"
        )
        self.surface.blit(self.font.render(title, True, "white"), (5, 510))
        pygame.display.flip()

    def close(self) -> None:
        pygame.quit()
