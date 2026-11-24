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

    def draw(
        self,
        e: Engine,
        agent: str | None,
        targets: dict[str, tuple[int, int]] | None = None,
        *,
        sectors: dict[str, tuple[tuple[int, int], ...]] | None = None,
        status: tuple[str, ...] = (),
    ) -> None:
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
        if agent is None and sectors:
            for index, cells in enumerate(sectors.values()):
                area = set(cells)
                color = ("pink", "lime", "yellow", "violet")[index % 4]
                for x, y in cells:
                    for dx, dy, start, end in (
                        (-1, 0, (x, y), (x, y + 1)),
                        (1, 0, (x + 1, y), (x + 1, y + 1)),
                        (0, -1, (x, y), (x + 1, y)),
                        (0, 1, (x, y + 1), (x + 1, y + 1)),
                    ):
                        if (x + dx, y + dy) not in area:
                            pygame.draw.line(
                                self.surface,
                                color,
                                (start[0] * size, start[1] * size),
                                (end[0] * size, end[1] * size),
                                2,
                            )
        for member, (x, y) in (targets or {}).items():
            if agent is None:
                pygame.draw.rect(self.surface, "orange", (x * size, y * size, size, size), 2)
                self.surface.blit(self.font.render(member, True, "black"), (x * size, y * size))
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
        if agent is None:
            for index, line in enumerate(status[:3]):
                self.surface.blit(self.font.render(line, True, "white"), (5, 533 + index * 20))
        pygame.display.flip()

    def close(self) -> None:
        pygame.quit()
