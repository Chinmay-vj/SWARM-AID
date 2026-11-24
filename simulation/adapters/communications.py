import json
from functools import partial
from pathlib import Path
from uuid import UUID, uuid5

from agents.drone_agent.agent import DroneAgent
from agents.drone_agent.reporting import Mailbox
from agents.shared.domain import DroneState
from communication.messages import Acknowledgement, Envelope, HumanOverride, Payload
from communication.network import REPORTS, Router, State
from simulation.core.engine import Engine


class SimulationNetwork:
    def __init__(self, e: Engine):
        c = e.config
        self.router = Router(
            e.mission_id, c.network, e.seed, c.delay * c.tick_ms, c.loss, c.tick_ms
        )
        self.mail: dict[str, Mailbox] = {}
        self.revisions: dict[UUID, int] = {}
        self.history: dict[str, list[Envelope]] = {"command": [], "operator": []}
        for name, role in [
            ("command", "command"),
            ("operator", "human"),
            *((a, "drone") for a in e.drones),
        ]:
            self.router.register(name, role, uuid5(e.mission_id, name))
            self.mail[name] = Mailbox(
                name, e.mission_id, c.network.capacity, send=partial(self.router.submit, name)
            )
        self.authority_after: dict[str, int] = {a: 0 for a in e.drones}
        self.was_connected: dict[str, bool] = {a: True for a in e.drones}
        self.positions = {a: d.position for a, d in e.drones.items()}

        def link(a: str, b: str) -> bool:
            if a not in self.positions or b not in self.positions:
                return True
            x, y = self.positions[a]
            u, v = self.positions[b]
            return abs(x - u) + abs(y - v) <= c.radio_range and (
                not c.partition or (x < c.width // 2) == (u < c.width // 2)
            )

        self.router.link = link

    def issue(
        self,
        source: str,
        payload: Payload,
        destination: str,
        expires_ms: int,
        revision: int | None = None,
    ) -> None:
        if source not in self.history:
            raise ValueError("trusted fixture endpoint required")
        if isinstance(payload, HumanOverride) and revision is None:
            raise ValueError("expected revision required")
        self.mail[source].publish(payload, self.router.now, destination, expires_ms=expires_ms)
        if revision is not None:
            self.revisions[self.mail[source].sent[-1].message_id] = revision

    def tick(self, e: Engine, agents: dict[str, DroneAgent]) -> None:
        r = self.router
        now = e.t * e.config.tick_ms
        r.now = now
        self.positions.update({a: d.position for a, d in e.drones.items()})
        for name in r.endpoints:
            available = (
                e.online(name)
                if name in agents
                else name != "command"
                or e.t not in e.config.network.server_down + e.config.outage_steps
            )
            r.availability(
                name, available and e.t not in e.config.network.endpoint_down.get(name, ())
            )
        r.advance(now)
        for name in self.history:
            for msg in r.drain(name):
                self.history[name].append(msg)
                if name == "command" and msg.payload.message_type != "acknowledgement":
                    self.mail[name].publish(
                        Acknowledgement(
                            message_type="acknowledgement",
                            acknowledged_id=msg.message_id,
                            outcome="accepted",
                        ),
                        now,
                        msg.source,
                    )
        for name, agent in agents.items():
            connected = self.connected(name)
            if connected and not self.was_connected[name]:
                self.authority_after[name] = now
            self.was_connected[name] = connected
            if not connected:
                agent.lease = None
                if agent.life.state.value in ("active", "ready"):
                    agent.life.change(DroneState.HOLD, now, "command link unavailable")
            for msg in r.drain(name):
                if msg.payload.message_type in REPORTS | {
                    "mission_instruction",
                    "human_override",
                    "agent_health",
                    "heartbeat",
                }:
                    try:
                        if msg.payload.message_type == "mission_instruction" and (
                            not connected or msg.sent_ms < self.authority_after[name]
                        ):
                            raise ValueError("new assignment required after link recovery")
                        agent.receive(
                            msg,
                            msg.source,
                            now,
                            expected_revision=self.revisions.get(msg.message_id),
                            routed_group=msg.destination == "peers",
                        )
                    except (ValueError, TypeError) as exc:
                        r.event("application_rejected", msg.source, name, msg.message_id, str(exc))

    def connected(self, name: str) -> bool:
        return self.router.now - self.router.confirmed_contact[
            name
        ] < self.router.config.heartbeat_ms and all(
            self.router.endpoints[n].state == State.CONNECTED for n in (name, "command")
        )

    def export(self, path: Path) -> None:
        path.with_suffix(".communication.json").write_text(
            json.dumps(self.router.metrics(), indent=2), encoding="utf-8"
        )
        with path.with_suffix(".communication.jsonl").open("w", encoding="utf-8") as out:
            for event in self.router.events:
                out.write(json.dumps(event) + "\n")
