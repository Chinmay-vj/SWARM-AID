import argparse
import json
from pathlib import Path

from evaluation.results import export, metrics
from simulation.adapters.coordination import sector_cells
from simulation.adapters.model1 import Fleet
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
        "--policy", choices=["stationary", "random", "waypoint", "model1"], default="stationary"
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--agent-config", type=Path)
    parser.add_argument(
        "--communication", action="store_true", help="run Model 1 with deterministic transport"
    )
    parser.add_argument(
        "--coordination", choices=["independent", "fixed_sector", "shared_information"]
    )
    args = parser.parse_args()
    data = load(args.scenario).model_dump()
    for key in ("agents", "seed"):
        if getattr(args, key) is not None:
            data[key] = getattr(args, key)
    e = Engine(Scenario.model_validate(data))

    fleet = (
        Fleet(
            e, args.agent_config, communication=args.communication, coordination=args.coordination
        )
        if args.policy == "model1" or args.communication or args.coordination
        else None
    )

    def advance() -> None:
        if fleet:
            fleet.advance(e)
            return
        e.step({a: choose(args.policy, e.views[a], e.t, e.seed + 1) for a in e.active})

    if args.render or e.config.render and not args.headless:
        import pygame

        from simulation.visualization.renderer import Renderer

        view = Renderer()
        try:
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
                            if fleet:
                                fleet = Fleet(
                                    e,
                                    args.agent_config,
                                    communication=args.communication,
                                    coordination=args.coordination,
                                )
                        if event.key == pygame.K_TAB:
                            selected = (selected + 1) % (len(e.drones) + 1)
                        if event.key == pygame.K_UP:
                            speed = min(60, speed + 1)
                        if event.key == pygame.K_DOWN:
                            speed = max(1, speed - 1)
                if (single or not paused) and e.reason == "running":
                    advance()
                selected_agent = ([None] + list(e.drones))[selected]
                if fleet and fleet.assignments and selected_agent is None:
                    fixture = fleet.assignments
                    view.draw(
                        e,
                        None,
                        {
                            a: (t.target.x, t.target.y)
                            for a, t in fleet.assignments.current.items()
                            if t.history[-1].state in ("assigned", "in_progress")
                        },
                        sectors={
                            a: tuple((c.x, c.y) for c in sector_cells(fixture.mission, a))
                            for a in fixture.mission.members
                        }
                        if args.coordination != "independent"
                        else None,
                        status=(
                            f"Mission {fixture.transitions[-1][1]} | Survey tasks {fixture.issued} | Reported cells {len(fixture.reported)}",
                            "Health "
                            + " ".join(f"{a} {state}" for a, state in fixture.availability.items()),
                            f"Review events {len(fixture.conflicts)} | Latest: {fixture.conflicts[-1][2] if fixture.conflicts else 'none'}",
                        ),
                    )
                else:
                    view.draw(e, selected_agent)
                clock.tick(speed)
        finally:
            view.close()
    else:
        while e.reason == "running":
            advance()
    if fleet:
        for agent in fleet.agents.values():
            if agent.logs:
                print(json.dumps(agent.logs[-1]))
    print(json.dumps(metrics(e)))
    if fleet and fleet.network:
        print(json.dumps(fleet.network.router.metrics()))
    if args.output or e.config.logging:
        path = export(e, args.output or Path("runs"))
        if fleet and fleet.network:
            fleet.network.export(path)
        if fleet and fleet.assignments:
            path.with_suffix(".coordination.json").write_text(
                json.dumps(
                    {
                        "policy": args.coordination,
                        "version": "1",
                        "command": fleet.assignments.command_snapshot(),
                        "settings": next(iter(fleet.agents.values())).settings.model_dump(
                            mode="json"
                        ),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        print(path)


if __name__ == "__main__":
    main()
