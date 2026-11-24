import argparse
import json
from pathlib import Path

from evaluation.results import export, metrics
from simulation.core.configuration import Scenario, load
from simulation.core.engine import Engine
from simulation.policies import choose


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="flood_basic")
    parser.add_argument("--agents", type=int)
    parser.add_argument("--seed", type=int)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headless", action="store_true")
    mode.add_argument("--render", action="store_true")
    parser.add_argument(
        "--policy", choices=["stationary", "random", "waypoint"], default="stationary"
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = load(args.scenario).model_dump()
    for key in ("agents", "seed"):
        if getattr(args, key) is not None:
            data[key] = getattr(args, key)
    e = Engine(Scenario.model_validate(data))

    def advance() -> None:
        e.step({a: choose(args.policy, e.views[a], e.t, e.seed + 1) for a in e.active})

    if args.render or e.config.render and not args.headless:
        import pygame

        from simulation.visualization.renderer import Renderer

        view = Renderer()
        clock = pygame.time.Clock()
        paused = True
        selected = 0
        speed = 5
        running = True
        while running:
            single = False
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_SPACE:
                        paused = not paused
                    if event.key == pygame.K_n:
                        single = True
                    if event.key == pygame.K_r:
                        e.reset(e.seed)
                    if event.key == pygame.K_TAB:
                        selected = (selected + 1) % (len(e.drones) + 1)
                    if event.key == pygame.K_UP:
                        speed = min(60, speed + 1)
                    if event.key == pygame.K_DOWN:
                        speed = max(1, speed - 1)
            if (single or not paused) and e.reason == "running":
                advance()
            view.draw(e, ([None] + list(e.drones))[selected])
            clock.tick(speed)
        view.close()
    else:
        while e.reason == "running":
            advance()
    print(json.dumps(metrics(e)))
    if args.output or e.config.logging:
        print(export(e, args.output or Path("runs")))


if __name__ == "__main__":
    main()
