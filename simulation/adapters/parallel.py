from typing import TYPE_CHECKING, ClassVar

import numpy as np
from gymnasium.spaces import Box, Discrete
from numpy.typing import NDArray
from pettingzoo import ParallelEnv  # type: ignore[import-untyped]

from simulation.core.configuration import Scenario
from simulation.core.engine import Engine

if TYPE_CHECKING:
    from simulation.visualization.renderer import Renderer

Vectors = dict[str, NDArray[np.int32]]
Infos = dict[str, dict[str, object]]


class RescueEnv(ParallelEnv):  # type: ignore[misc]
    metadata: ClassVar[dict[str, object]] = {
        "name": "swarm_aid_v1",
        "render_modes": ["human"],
        "is_parallelizable": True,
    }

    def __init__(self, config: Scenario, render_mode: str | None = None) -> None:
        self.engine = Engine(config)
        self.render_mode = render_mode
        self.possible_agents = list(self.engine.drones)
        self.agents = self.engine.active
        self.action_spaces = {a: Discrete(10) for a in self.possible_agents}
        self.observation_spaces = {
            a: Box(
                -1,
                max(config.width, config.height, 100, config.radius * config.radius * 100 + 100),
                shape=(4,),
                dtype=np.int32,
            )
            for a in self.possible_agents
        }
        self.screen: Renderer | None = None

    def observation_space(self, agent: str) -> Box:
        return self.observation_spaces[agent]

    def action_space(self, agent: str) -> Discrete:
        return self.action_spaces[agent]

    def obs(self, agent: str) -> NDArray[np.int32]:
        p = self.engine.views[agent]
        cell = p.frame.cell
        return np.array(
            [
                cell.x if cell else -1,
                cell.y if cell else -1,
                round(100 * p.frame.battery_fraction),
                sum(r.value == "possible_human" for r in p.readings),
            ],
            dtype=np.int32,
        )

    def reset(
        self, seed: int | None = None, options: dict[str, object] | None = None
    ) -> tuple[Vectors, Infos]:
        self.engine.reset(self.engine.config.seed if seed is None else seed)
        self.agents = self.engine.active
        return {a: self.obs(a) for a in self.agents}, {a: {} for a in self.agents}

    def step(
        self, actions: dict[str, int]
    ) -> tuple[Vectors, dict[str, float], dict[str, bool], dict[str, bool], Infos]:
        previous = self.agents.copy()
        if previous:
            self.engine.step(actions)
        terms = {a: not self.engine.drones[a].active for a in previous}
        trunc = {a: self.engine.reason == "horizon" and not terms[a] for a in previous}
        self.agents = [a for a in previous if not terms[a] and not trunc[a]]
        return (
            {a: self.obs(a) for a in previous},
            {a: 0.0 for a in previous},
            terms,
            trunc,
            {a: {} for a in previous},
        )

    def render(self) -> None:
        if self.render_mode == "human":
            from simulation.visualization.renderer import Renderer

            if self.screen is None:
                self.screen = Renderer()
            self.screen.draw(self.engine, None)

    def close(self) -> None:
        if self.screen:
            self.screen.close()
            self.screen = None
