from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import IntEnum
from random import Random
from uuid import NAMESPACE_OID, uuid5

from agents.shared.domain import SensorFrame
from communication.messages import Envelope, EvidenceReference
from simulation.core.configuration import Scenario
from simulation.entities import Hazard, Person
from simulation.environments.base import BLOCKED, REGISTRY, Point
from simulation.sensors.mock import Packet, sense


class Move(IntEnum):
    HOLD = 0
    NORTH = 1
    EAST = 2
    SOUTH = 3
    WEST = 4
    OBSERVE = 5
    REQUEST = 6
    REPORT = 7
    RETURN = 8
    INACTIVE = 9


DELTAS = ((0, 0), (0, -1), (1, 0), (0, 1), (-1, 0))


@dataclass
class Drone:
    position: Point
    battery: int = 100
    active: bool = True
    heading: str = "north"
    drone_id: str = ""
    mission: str = ""
    health: str = "available"
    updated_ms: int = 0


class Engine:
    def __init__(self, config: Scenario):
        self.config = config
        self.reset(config.seed)

    def reset(self, seed: int) -> None:
        c = self.config
        self.mission_id = uuid5(NAMESPACE_OID, c.scenario_id)
        if c.field_profile:
            self.mission_id = uuid5(
                self.mission_id, f"v2/{seed}/{c.agents}/{c.field_profile.difficulty}"
            )
        self.seed = seed
        self.t = 0
        self.world = REGISTRY[c.disaster](c)
        free = [p for p, v in self.world.tiles.items() if v not in BLOCKED]
        self.base = next((p for p in free if self.world.tiles[p] == "base"), free[0])
        placement = free
        if c.field_profile and c.field_profile.search_region:
            region = {(cell.x, cell.y) for cell in c.field_profile.search_region}
            placement = [p for p in free if p in region]
        self.people = {
            p: Person(str(i), p, not c.hidden_people, c.moving_people)
            for i, p in enumerate(Random(f"{seed}/people").sample(placement, c.people))
        }
        candidates = [p for p in free if self.world.tiles[p] == self.world.ground]
        if c.hazards > len(candidates):
            raise ValueError("too few hazard placement cells")
        self.hazards = {
            p: Hazard(f"h{i}", p, self.world.hazard)
            for i, p in enumerate(Random(f"{seed}/hazards").sample(candidates, c.hazards))
        }
        for p, hazard in self.hazards.items():
            self.world.tiles[p] = hazard.category
        starts = [p for p in free if self.world.tiles[p] not in BLOCKED]
        if len(starts) < c.agents:
            raise ValueError("too few safe starts after hazards")
        self.drones = {
            f"d{i}": Drone(
                p,
                active=i not in c.unavailable,
                drone_id=f"d{i}",
                mission=c.scenario_id,
                health="unavailable" if i in c.unavailable else "available",
            )
            for i, p in enumerate(starts[: c.agents])
        }
        self.report_sequence = dict.fromkeys(self.drones, 0)
        self.views: dict[str, Packet] = {}
        self.pending: dict[tuple[int, str], Packet | None] = {}
        self.mail: list[tuple[int, str, Envelope]] = []
        self.covered_by_agent: dict[str, set[Point]] = {a: set() for a in self.drones}
        self.first_seen_ms: dict[str, int] = {}
        self.covered: set[Point] = set()
        self.seen: set[str] = set()
        self.invalid = self.false = self.missed = self.count = self.connected = (
            self.radio_samples
        ) = 0
        self.events: list[str] = []
        self.capture()

    @property
    def active(self) -> list[str]:
        return [a for a, d in self.drones.items() if d.active]

    @property
    def reason(self) -> str:
        return (
            "inactive"
            if not self.active
            else "horizon"
            if self.t >= self.config.horizon
            else "running"
        )

    def online(self, a: str) -> bool:
        return (
            self.drones[a].active
            and self.t not in self.config.outage_steps
            and self.world.tiles[self.drones[a].position] != "weak_radio"
        )

    def send(self, msg: Envelope) -> bool:
        a, b = msg.source, msg.destination
        if a not in self.drones or not self.online(a):
            return False
        if b != "command":
            if b not in self.drones or not self.online(b):
                return False
            x, y = self.drones[a].position
            u, v = self.drones[b].position
            if (
                abs(x - u) + abs(y - v) > self.config.radio_range
                or self.config.partition
                and (x < self.config.width // 2) != (u < self.config.width // 2)
            ):
                return False
        if Random(f"{self.seed}/{self.t}/{msg.message_id}").random() < self.config.loss:
            return False
        self.mail.append((self.t + self.config.delay, b, msg))
        return True

    def receive(self, b: str) -> tuple[Envelope, ...]:
        due = [entry for entry in self.mail if entry[1] == b and entry[0] <= self.t]
        self.mail = [entry for entry in self.mail if entry not in due]
        available = self.t not in self.config.outage_steps if b == "command" else self.online(b)
        return tuple(
            m
            for _, _, m in due
            if available and (m.expires_ms is None or self.t * self.config.tick_ms < m.expires_ms)
        )

    def capture(self) -> None:
        c = self.config
        for a in self.active:
            d = self.drones[a]
            pkt, seen, false, miss, foot = sense(
                c,
                self.seed,
                self.t,
                a,
                d.position,
                d.battery / 100,
                d.heading,
                self.world.tiles,
                {p: person.entity_id for p, person in self.people.items() if person.visible},
            )
            self.pending[self.t + c.latency, a] = pkt
            self.views[a] = self.pending.pop((self.t, a), None) or Packet(
                frame=SensorFrame(
                    agent_id=a,
                    tick_ms=self.t * c.tick_ms,
                    samples=(),
                    cell=None,
                    battery_fraction=d.battery / 100,
                ),
                readings=(),
            )
            self.covered_by_agent[a].update(foot)
            for person_id in seen:
                self.first_seen_ms.setdefault(person_id, self.t * c.tick_ms)
            self.covered.update(foot)
            self.seen.update(seen)
            self.false += false
            self.missed += miss
            self.count += len(pkt.readings)
            self.connected += int(self.online(a))
            self.radio_samples += 1

    def step(self, actions: dict[str, int], *, report_hook: bool = True) -> None:
        if self.reason != "running":
            raise RuntimeError("episode ended")
        targets = {}
        for a in self.active:
            d = self.drones[a]
            x, y = d.position
            raw = actions.get(a, Move.HOLD)
            if raw not in Move._value2member_map_:
                self.invalid += 1
                raw = Move.HOLD
            move = Move(raw)
            if move == Move.INACTIVE:
                d.active = False
            dx, dy = DELTAS[raw] if 0 <= raw <= 4 else (0, 0)
            if move == Move.RETURN:
                bx, by = self.base
                dx = (bx > x) - (bx < x)
                dy = 0 if dx else (by > y) - (by < y)
            p = (x + dx, y + dy)
            if p != d.position and (
                self.world.tiles.get(p, "obstacle") in BLOCKED
                or d.battery <= 22
                or not self.online(a)
                or self.views[a].frame.cell is None
            ):
                self.invalid += 1
                p = d.position
            targets[a] = p
            if move in (Move.REQUEST, Move.REPORT):
                self.events.append(f"{self.t} {a} {move.name}")
                if move == Move.REPORT and report_hook:
                    readings = self.views[a].readings
                    if readings:
                        reading = next(
                            (r for r in readings if r.value == "possible_human"), readings[0]
                        )
                        uid = uuid5(self.mission_id, f"{a}/{self.t}/report")
                        ms = self.t * self.config.tick_ms
                        message = Envelope(
                            schema_version="1.0",
                            message_id=uid,
                            source=a,
                            destination="command",
                            mission_id=self.mission_id,
                            session_id=uuid5(self.mission_id, a),
                            timestamp=datetime(2000, 1, 1, tzinfo=UTC) + timedelta(milliseconds=ms),
                            sent_ms=ms,
                            sequence=self.report_sequence[a],
                            priority="routine",
                            correlation_id=uid,
                            payload=EvidenceReference(
                                message_type="evidence_reference", evidence=reading.evidence
                            ),
                        )
                        self.report_sequence[a] += 1
                        self.send(message)
        while True:
            veto = set()
            for a, p in targets.items():
                if p == self.drones[a].position:
                    continue
                for b, d in self.drones.items():
                    if b != a and (
                        targets.get(b, d.position) == p
                        or d.position == p
                        and targets.get(b) == self.drones[a].position
                    ):
                        veto.add(a)
            if not veto:
                break
            for a in veto:
                targets[a] = self.drones[a].position
            self.invalid += len(veto)
        for a, p in targets.items():
            d = self.drones[a]
            moved = p != d.position
            if moved:
                d.heading = str((p[0] - d.position[0], p[1] - d.position[1]))
            d.battery = max(0, d.battery - 1 - int(moved))
            d.updated_ms = (self.t + 1) * self.config.tick_ms
            d.position = p
            d.active = d.active and d.battery > 20
        self.t += 1
        for e in self.config.events:
            if e.step == self.t:
                self.world.tiles[e.cell.x, e.cell.y] = e.terrain
                self.events.append(f"{self.t} {e.terrain}")
        if self.config.moving_people:
            moved_people = {}
            for p, person in sorted(self.people.items()):
                dx, dy = Random(f"{self.seed}/{person.entity_id}/{self.t}").choice(DELTAS)
                dest = p[0] + dx, p[1] + dy
                if (
                    self.world.tiles.get(dest, "obstacle") in BLOCKED
                    or dest in self.people
                    or dest in moved_people
                ):
                    dest = p
                person.position = dest
                moved_people[dest] = person
            self.people = moved_people
        self.capture()

    def snapshot(self) -> dict[str, object]:
        return {
            "step": self.t,
            "tiles": [[x, y, k] for (x, y), k in self.world.tiles.items()],
            "people": list(self.people),
            "drones": {a: d.position for a, d in self.drones.items()},
            "events": self.events.copy(),
        }
