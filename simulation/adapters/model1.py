from pathlib import Path

from agents.drone_agent.agent import DroneAgent
from agents.drone_agent.components import Settings
from agents.shared.coordination import MissionContext
from agents.shared.domain import Cell, DroneState
from interfaces.providers import CoordinationPolicy
from simulation.adapters.communications import SimulationNetwork
from simulation.adapters.coordination import (
    AssignmentFixture,
    Baseline,
    PolicyName,
)
from simulation.core.engine import Engine, Move


class Fleet:
    """Trusted adapter. Only packets, public constraints and local link status enter agents."""

    def __init__(
        self,
        e: Engine,
        path: Path | None = None,
        *,
        communication: bool = False,
        coordination: PolicyName | None = None,
        policy: CoordinationPolicy | None = None,
    ):
        self.network = (
            SimulationNetwork(e, share_peers=coordination not in ("fixed_sector", "independent"))
            if communication or coordination or policy
            else None
        )
        settings = Settings.model_validate_json(
            (path or Path(__file__).resolve().parents[2] / "configs" / "model1.json").read_bytes()
        )
        self.assignments = None
        if coordination or policy:
            self.assignments = AssignmentFixture(
                MissionContext(
                    e.mission_id,
                    tuple(e.drones),
                    e.config.width,
                    e.config.height,
                    frozenset(e.config.terrain.get("restricted", ())),
                    e.config.horizon * e.config.tick_ms,
                    disaster=e.config.disaster,
                    objective=e.config.mission_objective,
                    sectors=tuple(e.config.sectors.items()),
                ),
                policy or Baseline(coordination or "independent"),
                e.config.assignment_ticks * e.config.tick_ms,
            )
            if path is None:
                settings = settings.model_copy(update={"movement": True})
        self.agents = {
            a: DroneAgent(
                a,
                e.mission_id,
                settings,
                (e.config.width, e.config.height),
                frozenset(e.config.terrain.get("restricted", ())),
                mailbox=self.network.mail[a] if self.network else None,
                base=Cell(x=e.base[0], y=e.base[1]),
            )
            for a in e.drones
        }

        for a in self.agents.keys() - set(e.active):
            self.agents[a].health.status = "unavailable"
            self.agents[a].life.change(DroneState.ENDED, 0, "unavailable at reset")

    def advance(self, e: Engine) -> None:
        now = e.t * e.config.tick_ms
        before = {a: e.drones[a].position for a in e.active}
        if self.network:
            self.network.tick(e, self.agents)
            if self.assignments:
                self.assignments.advance(self.network, now)
        moves = {
            a: self.agents[a].cycle(
                e.views[a], now, self.network.connected(a) if self.network else e.online(a)
            )
            for a in e.active
        }
        e.step({a: int(move) for a, move in moves.items()}, report_hook=self.network is None)
        for a, move in moves.items():
            agent = self.agents[a]
            blocked = (
                move in (Move.NORTH, Move.SOUTH, Move.EAST, Move.WEST, Move.RETURN)
                and before[a] == e.drones[a].position
            )
            if agent.settings.logging and agent.logs:
                agent.logs[-1]["outcome"] = "blocked" if blocked else "applied"
            if not e.drones[a].active or e.reason != "running":
                agent.life.change(DroneState.ENDED, e.t * e.config.tick_ms, e.reason)

        if self.assignments and e.reason != "running":
            self.assignments.expire(e.t * e.config.tick_ms)
            if self.assignments.transitions[-1][1] not in {"aborted", "completed"}:
                self.assignments.transition(e.t * e.config.tick_ms, "completed")
