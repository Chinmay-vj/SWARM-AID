"""PettingZoo adapter over the existing Fleet: same engine, network, memory and safety gate.

`coordination=None` is the learning mode: policy actions pass through the existing
`authorize` gate, standing in for a command movement lease, and the engine vetoes them
again. With a coordination baseline the Fleet behaves exactly as before and actions are
ignored. All observations are symbolic; no perception network runs here.
"""

from typing import Any, ClassVar
from uuid import uuid5

import numpy as np
from gymnasium.spaces import Box, Discrete
from numpy.typing import NDArray
from pettingzoo import ParallelEnv  # type: ignore[import-untyped]

from agents.drone_agent.safety import authorize
from agents.shared.domain import Action, Cell, Intent, TaskLease
from simulation.adapters import marl_contract as contract
from simulation.adapters.coordination import PolicyName
from simulation.adapters.model1 import Fleet
from simulation.core.configuration import Scenario
from simulation.core.engine import Engine, Move

SPATIAL = ("image", "thermal", "environment")
Observations = dict[str, NDArray[np.float32]]
Infos = dict[str, dict[str, Any]]


class SearchEnv(ParallelEnv):  # type: ignore[misc]
    metadata: ClassVar[dict[str, object]] = {"name": "swarm_aid_search_v1",
                                             "is_parallelizable": True}

    def __init__(
        self,
        scenario: Scenario,
        *,
        coordination: PolicyName | None = None,
        reward: contract.RewardConfig | None = None,
    ) -> None:
        self.scenario = scenario
        self.coordination = coordination
        self.rewards = reward or contract.RewardConfig()
        self.possible_agents = [f"d{i}" for i in range(scenario.agents)]
        self.agents: list[str] = []
        self.action_spaces = {a: Discrete(len(contract.ACTIONS)) for a in self.possible_agents}
        self.observation_spaces = {
            a: Box(-1.0, 1.0, (contract.SIZE,), np.float32) for a in self.possible_agents
        }
        self._engine: Engine | None = None

    def observation_space(self, agent: str) -> Box:
        return self.observation_spaces[agent]

    def action_space(self, agent: str) -> Discrete:
        return self.action_spaces[agent]

    @property
    def engine(self) -> Engine:
        """Evaluator-only access. Policies receive observations, never this object."""
        if self._engine is None:
            raise RuntimeError("reset(seed=...) is required first")
        return self._engine

    def reset(
        self, seed: int | None = None, options: dict[str, object] | None = None
    ) -> tuple[Observations, Infos]:
        if seed is None:
            raise ValueError("an explicit development or validation seed is required")
        self.split = contract.require_open_seed(seed)
        config = Scenario.model_validate(self.scenario.model_dump() | {"seed": seed})
        self._engine = e = Engine(config)
        self.fleet = Fleet(e, coordination=self.coordination, communication=True)
        self.restricted = frozenset(config.terrain.get("restricted", ()))
        self.bounds = (config.width, config.height)
        self.settings = next(iter(self.fleet.agents.values())).settings.model_copy(
            update={"movement": True})
        self.agents = list(e.active)
        self.searched: dict[str, set[tuple[int, int]]] = {a: set() for a in self.possible_agents}
        self.corroborated: set[tuple[int, int]] = set()
        self.unclear: set[tuple[int, int]] = set()
        self.resolved: set[tuple[int, int]] = set()
        self.visited = {a: {d.position} for a, d in e.drones.items()}
        self.totals = dict.fromkeys(self._component_names(), 0.0)
        self.counts = {"footprint": 0, "redundant_footprint": 0, "rejected_actions": 0,
                       "invalid_ids": 0}
        self._sense(set())
        return self._observe(self.agents), {a: self._info(a) for a in self.agents}

    @staticmethod
    def _component_names() -> tuple[str, ...]:
        return ("new_cell", "redundant", "corroborated", "resolved_uncertainty",
                "rejected_action")

    def _link(self, agent: str) -> bool:
        assert self.fleet.network is not None
        return self.engine.drones[agent].active and self.fleet.network.connected(agent)

    def _info(self, agent: str) -> dict[str, Any]:
        mask = contract.action_mask(self.engine.views[agent], self.bounds, self.restricted,
                                    self._link(agent), self.settings)
        return {"action_mask": mask, "split": self.split, "evidence_kind": "symbolic",
                "available": self.engine.drones[agent].active}

    def _observe(self, agents: list[str]) -> Observations:
        e = self.engine
        now = e.t * e.config.tick_ms
        return {
            a: contract.encode(
                self.fleet.agents[a], e.views[a], self.searched[a], self.bounds,
                self.restricted, self._link(a), e.t / e.config.horizon, now, self.settings)
            for a in agents
        }

    def _sense(self, covered_before: set[tuple[int, int]]) -> dict[str, dict[str, float]]:
        """Evidence-based reward terms from each agent's current symbolic packet."""
        e = self.engine
        terms: dict[str, dict[str, float]] = {}
        for a in e.active:
            modes: dict[tuple[int, int], set[str]] = {}
            unclear: set[tuple[int, int]] = set()
            clear: set[tuple[int, int]] = set()
            for reading in e.views[a].readings:
                if reading.cell is None or reading.evidence.modality not in SPATIAL:
                    continue
                key = (reading.cell.x, reading.cell.y)
                modes.setdefault(key, set()).add(reading.evidence.modality)
                (unclear if reading.value == "indistinct" else clear).add(key)
            corroborated = {k for k, v in modes.items() if len(v) > 1} - self.corroborated
            resolved = (clear - unclear) & (self.unclear - self.resolved)
            self.corroborated |= corroborated
            self.resolved |= resolved
            self.unclear |= unclear
            repeated = len(set(modes) & covered_before)
            terms[a] = {"corroborated": len(corroborated), "resolved": len(resolved),
                        "footprint": len(modes), "repeated": repeated}
        return terms

    def _gate(self, actions: dict[str, int], wanted: dict[str, Move],
              rejected: set[str]) -> Any:
        def override(agent_id: str, own: Move) -> Move:
            e, agent = self.engine, self.fleet.agents[agent_id]
            raw = actions.get(agent_id, Move.HOLD)
            if isinstance(raw, bool) or int(raw) not in [int(m) for m in contract.ACTIONS]:
                self.counts["invalid_ids"] += 1
                rejected.add(agent_id)
                return own
            move = Move(int(raw))
            if move == Move.HOLD or own == Move.INACTIVE:
                return own
            packet = e.views[agent_id]
            cell = packet.frame.cell
            if cell is None:
                rejected.add(agent_id)
                return Move.HOLD
            x, y = cell.x + contract.OFFSETS[move][0], cell.y + contract.OFFSETS[move][1]
            if x < 0 or y < 0:
                rejected.add(agent_id)
                return Move.HOLD
            now = e.t * e.config.tick_ms
            proposal = Action(intent=Intent.SURVEY, target=Cell(x=x, y=y))
            lease = TaskLease(task_id=uuid5(e.mission_id, f"policy/{agent_id}/{now}"),
                              action=proposal, expires_ms=now + e.config.tick_ms)
            allowed, status, _ = authorize(
                proposal, own, packet.frame, now, lease, self.settings, agent.life.state,
                agent.override, self._link(agent_id), self.bounds, self.restricted)
            if status != "approved":
                rejected.add(agent_id)
            else:
                wanted[agent_id] = allowed
            return allowed

        return override

    def step(
        self, actions: dict[str, int]
    ) -> tuple[Observations, dict[str, float], dict[str, bool], dict[str, bool], Infos]:
        previous = self.agents.copy()
        if not previous:
            return {}, {}, {}, {}, {}
        e = self.engine
        covered = set(e.covered)
        own_covered = {a: set(v) for a, v in e.covered_by_agent.items()}
        positions = {a: d.position for a, d in e.drones.items()}
        wanted: dict[str, Move] = {}
        rejected: set[str] = set()
        override = None if self.coordination else self._gate(actions, wanted, rejected)
        self.fleet.advance(e, override=override)
        for a in wanted:
            if e.drones[a].position == positions[a]:
                rejected.add(a)  # unseen obstacle, collision or simulator constraint
        sensed = self._sense(covered)
        first: dict[tuple[int, int], list[str]] = {}
        for a in previous:
            for cell in e.covered_by_agent[a] - own_covered[a] - covered:
                first.setdefault(cell, []).append(a)
        rewards: dict[str, float] = {}
        infos: Infos = {}
        w = self.rewards
        for a in previous:
            terms = sensed.get(a, {})
            footprint = terms.get("footprint", 0)
            self.counts["footprint"] += int(footprint)
            self.counts["redundant_footprint"] += int(terms.get("repeated", 0))
            self.counts["rejected_actions"] += a in rejected
            position = e.drones[a].position
            revisit = position != positions[a] and position in self.visited[a]
            self.visited[a].add(position)
            repeated = (float(revisit) if w.version == "reward-2"
                        else terms.get("repeated", 0) / footprint if footprint else 0.0)
            parts = {
                "new_cell": w.new_cell * sum(1 / len(v) for v in first.values() if a in v),
                "redundant": w.redundant * repeated,
                "corroborated": w.corroborated * terms.get("corroborated", 0),
                "resolved_uncertainty": w.resolved_uncertainty * terms.get("resolved", 0),
                "rejected_action": w.rejected_action * (a in rejected),
            }
            for name, value in parts.items():
                self.totals[name] += value
            rewards[a] = float(sum(parts.values()))
            infos[a] = {**self._info(a), "reward_components": parts, "rejected": a in rejected}
        terminated = {a: not e.drones[a].active for a in previous}
        truncated = {a: e.reason == "horizon" and not terminated[a] for a in previous}
        self.agents = [a for a in previous if not terminated[a] and not truncated[a]]
        return self._observe(previous), rewards, terminated, truncated, infos

    def episode_metrics(self) -> dict[str, Any]:
        """Evaluator-only, using the simulator's own definitions."""
        e = self.engine
        assert self.fleet.network is not None
        network = self.fleet.network.router.metrics()
        reported = {
            m.payload.observation.observation_id
            for m in self.fleet.network.history["command"]
            if hasattr(m.payload, "observation")
        }
        return {
            "steps": e.t,
            "reason": e.reason,
            "coverage": len(e.covered) / len(e.world.tiles),
            "unique_cells": len(e.covered),
            "cross_agent_duplicate_cells":
                sum(map(len, e.covered_by_agent.values())) - len(e.covered),
            "redundant_footprint_fraction":
                self.counts["redundant_footprint"] / max(self.counts["footprint"], 1),
            "observations_captured": e.count,
            "observations_reported": len(reported),
            "people_observed": len(e.seen),
            "network_bytes": network["bytes"],
            "delivery_ratio": network["delivery_ratio"],
            "safety_interventions":
                sum(a.health.invalid_actions for a in self.fleet.agents.values()),
            "engine_invalid": e.invalid,
            "policy_rejected_actions": self.counts["rejected_actions"],
            "battery_used": sum(100 - d.battery for d in e.drones.values()),
            "reward_total": float(sum(self.totals.values())),
            **{f"reward_{k}": v for k, v in self.totals.items()},
        }
