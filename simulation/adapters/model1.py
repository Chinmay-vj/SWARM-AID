from collections.abc import Callable
from pathlib import Path

from agents.command_agent.agent import CommandAgent
from agents.command_agent.agent import Settings as CommandSettings
from agents.drone_agent.agent import DroneAgent
from agents.drone_agent.components import Settings
from agents.shared.coordination import MissionContext
from agents.shared.domain import Cell, DroneState
from communication.messages import (
    CommandAlert,
    HumanApproval,
    HumanOverride,
    IncidentUpdate,
    MissionUpdate,
)
from interfaces.providers import CoordinationPolicy, PerceptionProvider
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
        command: CommandSettings | None = None,
        coordination: PolicyName | None = None,
        policy: CoordinationPolicy | None = None,
        perception_factory: Callable[[str], PerceptionProvider] | None = None,
    ):
        self.network = (
            SimulationNetwork(e, share_peers=coordination not in ("fixed_sector", "independent"))
            if communication or coordination or policy or command
            else None
        )
        self.command = CommandAgent(e.mission_id, frozenset(e.drones), command) if command else None
        self.command_cursor = 0
        self.command_revision = 0
        settings = Settings.model_validate_json(
            (path or Path(__file__).resolve().parents[2] / "configs" / "model1.json").read_bytes()
        )
        self.assignments = None
        if coordination or policy or command:
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
            if path is None and (coordination or policy):
                settings = settings.model_copy(update={"movement": True})
        self.agents: dict[str, DroneAgent] = {}
        provider_ids: set[int] = set()
        for a in e.drones:
            perception = perception_factory(a) if perception_factory is not None else None
            if perception is not None and id(perception) in provider_ids:
                raise ValueError("perception factory must create independent per-agent providers")
            if perception is not None:
                provider_ids.add(id(perception))
            self.agents[a] = DroneAgent(
                a,
                e.mission_id,
                settings,
                (e.config.width, e.config.height),
                frozenset(e.config.terrain.get("restricted", ())),
                mailbox=self.network.mail[a] if self.network else None,
                base=Cell(x=e.base[0], y=e.base[1]),
                perception=perception,
            )

        for a in self.agents.keys() - set(e.active):
            self.agents[a].health.status = "unavailable"
            self.agents[a].life.change(DroneState.ENDED, 0, "unavailable at reset")

    def advance(self, e: Engine) -> None:
        now = e.t * e.config.tick_ms
        before = {a: e.drones[a].position for a in e.active}
        if self.network:
            self.network.tick(e, self.agents)
            if self.command:
                state = (
                    "active"
                    if self.network.router.endpoints["command"].state.value == "connected"
                    else "offline"
                )
                if self.command.state != state:
                    self.command.event(now, "recovered" if state == "active" else "offline")
                    self.command.state = state
                if state == "active":
                    inbox = self.network.history["command"]
                    for msg in inbox[self.command_cursor :]:
                        # Router already verified the source against its registered session.
                        if isinstance(msg.payload, HumanOverride):
                            valid = (
                                msg.source == "operator"
                                and self.assignments is not None
                                and self.network.revisions.get(msg.message_id)
                                == self.command_revision
                            )
                            target = {"pause": "paused", "end": "aborted", "resume": "active"}[
                                msg.payload.action
                            ]
                            if valid and self.assignments:
                                try:
                                    self.assignments.transition(now, target)
                                except ValueError:
                                    valid = False
                            if valid:
                                self.command_revision += 1
                                self.command.event(
                                    now, "operator_" + msg.payload.action, msg.message_id
                                )
                                self.network.mail["command"].publish(
                                    MissionUpdate(
                                        message_type="mission_update",
                                        revision=self.command_revision,
                                        status="paused"
                                        if target == "paused"
                                        else "ended"
                                        if target == "aborted"
                                        else "active",
                                        summary=msg.payload.reason,
                                    ),
                                    now,
                                    "operator",
                                )
                            else:
                                self.command.event(now, "invalid_override", msg.message_id)
                            continue
                        update = self.command.consume(msg, msg.source, now)
                        if update:
                            if isinstance(update, IncidentUpdate):
                                priority = self.command.priorities[update.incident.incident_id]
                                first_report = next(
                                    r
                                    for r in self.command.findings.values()
                                    if r.message_id == update.incident.reports[0]
                                )
                                publication = CommandAlert(
                                    message_type="command_alert",
                                    update=update,
                                    priority=priority.level,
                                    priority_reason=priority.reason,
                                    supporting_evidence=priority.evidence,
                                    location=first_report.finding.observation.cell,
                                    review_state=self.command.dispositions[
                                        update.incident.incident_id
                                    ],
                                )
                            self.network.mail["command"].publish(
                                publication if isinstance(update, IncidentUpdate) else update,
                                now,
                                "operator",
                                expires_ms=update.recommendation.expires_ms
                                if isinstance(update, IncidentUpdate) and update.recommendation
                                else now + self.command.settings.review_ms,
                            )
                            if isinstance(msg.payload, HumanApproval):
                                self.command_revision += 1
                                self.network.mail["command"].publish(
                                    MissionUpdate(
                                        message_type="mission_update",
                                        revision=self.command_revision,
                                        status="paused"
                                        if self.assignments
                                        and self.assignments.transitions[-1][1] == "paused"
                                        else "ended"
                                        if self.assignments
                                        and self.assignments.transitions[-1][1] == "aborted"
                                        else "active",
                                        summary=f"Operator recorded {msg.payload.decision} for incident {msg.payload.incident_id}",
                                    ),
                                    now,
                                    "operator",
                                )
                    self.command_cursor = len(inbox)
                    self.command.expire(now)
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

        if self.command and e.reason != "running":
            self.command.expire(e.t * e.config.tick_ms)
            self.command.event(e.t * e.config.tick_ms, "ended")
            self.command.state = "ended"
