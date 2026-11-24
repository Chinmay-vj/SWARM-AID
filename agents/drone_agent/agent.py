from collections import deque
from copy import deepcopy
from uuid import UUID, uuid5

from agents.drone_agent.baselines import Fusion, MockPerception, Planner, Rules
from agents.drone_agent.components import Health, Inputs, Lifecycle, Memory, Settings, World
from agents.drone_agent.reporting import Mailbox
from agents.drone_agent.safety import authorize
from agents.shared.domain import Action, Cell, DroneState, Finding, TaskLease
from communication.messages import (
    AgentHealth,
    Envelope,
    EnvironmentalObservation,
    ErrorReport,
    EvidenceReference,
    HazardDetection,
    Heartbeat,
    HumanOverride,
    MissionInstruction,
    Payload,
    PossibleHumanDetection,
    Registration,
    TaskStatus,
)
from interfaces.providers import (
    PerceptionProvider,
    PlanningProvider,
    ReasoningProvider,
    SensorFusionProvider,
)
from simulation.core.engine import Move
from simulation.sensors.mock import Packet


class DroneAgent:
    def __init__(
        self,
        owner: str,
        mission: UUID,
        settings: Settings,
        bounds: tuple[int, int],
        restricted: frozenset[Cell] = frozenset(),
        *,
        perception: PerceptionProvider | None = None,
        fusion: SensorFusionProvider | None = None,
        reasoning: ReasoningProvider | None = None,
        planning: PlanningProvider | None = None,
        mailbox: Mailbox | None = None,
        base: Cell | None = None,
    ):
        self.owner, self.mission, self.settings = owner, mission, settings
        self.bounds, self.restricted = bounds, restricted
        if settings.agent_id not in ("template", owner):
            raise ValueError("agent identity mismatch")
        self.base = base
        self.revision = 0
        self.instructions: deque[Envelope] = deque(maxlen=settings.capacity)
        self.inputs = Inputs()
        self.perception = perception or MockPerception(self.inputs)
        self.fusion = fusion or Fusion()
        self.reasoning = reasoning or Rules()
        self.planning = planning or Planner()
        self.memory = Memory(owner, mission, settings)
        self.world = World(self.memory)
        self.life = Lifecycle(mission, owner, settings.capacity)
        self.health = Health()
        self.mail = mailbox or Mailbox(owner, mission, settings.capacity)
        self.logs: deque[dict[str, object]] = deque(maxlen=settings.capacity)
        self.lease: TaskLease | None = None
        self.override = ""
        self.peer_status: deque[Envelope] = deque(maxlen=settings.capacity)
        self.last_control_ms = -1
        self.last_override_ms = -1
        self.life.change(DroneState.READY, 0, "initialized")
        self.mail.publish(
            Registration(message_type="registration", role="drone", session_id=self.mail.session), 0
        )

    def receive(
        self,
        msg: Envelope,
        principal: str,
        now: int,
        *,
        expected_revision: int | None = None,
        routed_group: bool = False,
    ) -> None:
        if (
            (msg.source, msg.destination, msg.mission_id)
            != (
                principal,
                "peers"
                if routed_group
                and isinstance(
                    msg.payload,
                    (
                        EnvironmentalObservation,
                        HazardDetection,
                        PossibleHumanDetection,
                        AgentHealth,
                        Heartbeat,
                    ),
                )
                else self.owner,
                self.mission,
            )
            or msg.sent_ms > now
            or msg.expires_ms is not None
            and now >= msg.expires_ms
        ):
            raise ValueError("invalid message scope or time")
        payload = msg.payload
        if isinstance(payload, (HumanOverride, MissionInstruction)):
            expected = "operator" if isinstance(payload, HumanOverride) else "command"
            if (
                principal != expected
                or isinstance(payload, MissionInstruction)
                and (msg.sent_ms <= self.last_control_ms or self.override == "pause")
                or self.override == "end"
            ):
                raise ValueError("unauthorized or outdated control")
            if isinstance(payload, HumanOverride):
                if expected_revision != self.revision or msg.sent_ms < self.last_override_ms:
                    raise ValueError("override revision mismatch")
                self.last_override_ms = msg.sent_ms
                self.revision += 1
                self.override = payload.action
                self.lease = None
            elif msg.expires_ms is not None:
                self.lease = TaskLease(
                    task_id=payload.task_id, action=payload.action, expires_ms=msg.expires_ms
                )
            self.instructions.append(msg)
            self.last_control_ms = max(self.last_control_ms, msg.sent_ms)
        elif isinstance(payload, (AgentHealth, Heartbeat)):
            self.peer_status.append(msg)
        elif isinstance(
            payload, (EnvironmentalObservation, HazardDetection, PossibleHumanDetection)
        ):
            if now - payload.observation.observed_ms > self.settings.ttl_ms:
                raise ValueError("stale peer observation")
            self.memory.remember(
                Finding(
                    observation=payload.observation,
                    kind="hazard"
                    if isinstance(payload, HazardDetection)
                    else "environment"
                    if isinstance(payload, EnvironmentalObservation)
                    else "possible_human",
                    label=payload.hazard
                    if isinstance(payload, HazardDetection)
                    else payload.feature
                    if isinstance(payload, EnvironmentalObservation)
                    else None,
                )
            )
        else:
            raise TypeError("unsupported incoming message")

    def snapshot(self) -> dict[str, object]:
        return {
            "owner": self.owner,
            "mission": str(self.mission),
            "state": self.life.state.value,
            "health": vars(self.health).copy(),
            "world": self.world.snapshot(),
            "events": deepcopy(list(self.logs)),
            "transitions": deepcopy(list(self.life.history)),
            "instructions": [m.model_dump(mode="json") for m in self.instructions],
            "reports": [m.model_dump(mode="json") for m in self.mail.sent],
        }

    def cycle(self, packet: Packet, now: int, online: bool) -> Move:
        if self.life.state == DroneState.ENDED:
            return Move.INACTIVE
        self.memory.expire(now)
        self.mail.online = online
        try:
            try:
                self.inputs.ingest(packet, self.owner, self.mission, now, self.settings)
            except ValueError:
                self.health.invalid_inputs += 1
                raise
            frame = packet.frame.model_copy(
                update={
                    "samples": tuple(i.reading.evidence for i in self.inputs.current.values()),
                    "cell": packet.frame.cell
                    if any(
                        i.reading.evidence.modality == "gps" for i in self.inputs.current.values()
                    )
                    else None,
                }
            )
            found = self.perception.perceive(frame)
            if any(
                e.evidence_id not in self.inputs.current
                for f in found
                for e in f.observation.evidence
            ):
                raise ValueError("unresolved provider evidence")
            view = self.fusion.fuse(frame, found)
            if (
                view.agent_id != self.owner
                or view.tick_ms != frame.tick_ms
                or any(f.observation.observed_ms > now for f in view.observations)
                or any(
                    e.evidence_id not in self.inputs.current
                    or self.inputs.current[e.evidence_id].reading.evidence != e
                    for f in view.observations
                    for e in f.observation.evidence
                )
            ):
                raise ValueError("fusion scope or provenance mismatch")
            for f in view.observations:
                self.memory.remember(f)
            self.health.online = online
            self.health.battery_fraction = frame.battery_fraction
            self.health.memory_entries = len(self.memory.items)
            self.health.missing_modalities = tuple(
                sorted(set(self.settings.modalities) - {e.modality for e in frame.samples})
            )
            self.health.status = (
                "healthy"
                if online and frame.samples and frame.battery_fraction > self.settings.reserve
                else "degraded"
            )
            history_view = view.model_copy(
                update={"observations": self.memory.recent(now - self.settings.ttl_ms)}
            )
            intent = self.reasoning.select_intent(history_view)
            proposal = Action.model_validate(self.planning.plan(view, intent, self.lease))
            if self.life.state == DroneState.HOLD:
                self.life.change(DroneState.READY, now, "retry")
            self.life.change(DroneState.ACTIVE, now, "validated input")
            attention = next(
                (f for f in view.observations if f.kind == "possible_human"),
                next((f for f in view.observations if f.kind == "hazard"), None),
            )
            semantics: dict[Cell | None, set[str | None]] = {}
            for f in view.observations:
                if f.kind != "possible_human":
                    semantics.setdefault(f.observation.cell, set()).add(f.label)
            conflict = any(len(v) > 1 for v in semantics.values())
            category = (
                "conflicting_evidence"
                if conflict
                else attention.kind
                if attention
                else "routine"
                if view.observations
                else "insufficient_information"
            )
            fallback = (
                Move.REQUEST
                if conflict or not view.observations
                else Move.REPORT
                if attention
                else Move.OBSERVE
            )
            move, status, reason = authorize(
                proposal,
                fallback,
                frame,
                now,
                self.lease,
                self.settings,
                self.life.state,
                self.override,
                online,
                self.bounds,
                self.restricted,
            )
            if (
                move in (Move.NORTH, Move.SOUTH, Move.WEST, Move.EAST)
                and proposal.target == self.base
            ):
                move = Move.RETURN
            if proposal.target and "gps" not in {e.modality for e in frame.samples}:
                move, status, reason = Move.HOLD, "modified", "missing GPS"
            if not frame.samples and move != Move.INACTIVE:
                move, status, reason = Move.HOLD, "modified", "sensor failure"
            if status != "approved":
                self.health.invalid_actions += 1
            if move == Move.HOLD:
                self.life.change(DroneState.HOLD, now, reason)
            if move == Move.INACTIVE:
                self.life.change(DroneState.ENDED, now, reason)
            chosen = attention or next(iter(view.observations), None)
            payload: Payload
            if chosen:
                if chosen.kind == "possible_human":
                    payload = PossibleHumanDetection(
                        message_type="possible_human_detection", observation=chosen.observation
                    )
                elif chosen.kind == "hazard":
                    payload = HazardDetection(
                        message_type="hazard_detection",
                        observation=chosen.observation,
                        hazard=chosen.label or "unknown",
                    )
                else:
                    payload = EnvironmentalObservation(
                        message_type="environmental_observation",
                        observation=chosen.observation,
                        feature=chosen.label or "unknown",
                    )
                if conflict or chosen.kind == "possible_human":
                    self.mail.publish(
                        EvidenceReference(
                            message_type="evidence_reference",
                            evidence=chosen.observation.evidence[0],
                        ),
                        now,
                        "human_review",
                    )
                for dest in ("peers", "command"):
                    self.mail.publish(payload, now, dest)
            self.mail.publish(Heartbeat(message_type="heartbeat", state=self.life.state), now)
            self.mail.publish(
                AgentHealth(
                    message_type="agent_health",
                    battery_fraction=frame.battery_fraction,
                    degraded_sensors=tuple(
                        sorted(set(self.settings.modalities) - {e.modality for e in frame.samples})
                    ),
                    cell=frame.cell,
                ),
                now,
            )
            if self.lease:
                self.mail.publish(
                    TaskStatus(
                        message_type="task_status",
                        task_id=self.lease.task_id,
                        status="active" if status == "approved" else "rejected",
                    ),
                    now,
                )
            self.health.last_success_ms = now
            if self.settings.logging:
                self.logs.append(
                    {
                        "agent": self.owner,
                        "time_ms": now,
                        "decision_id": str(uuid5(self.mail.session, f"decision/{now}")),
                        "category": category,
                        "health": self.health.status,
                        "memory_entries": len(self.memory.items),
                        "constraints": ["lease", "public bounds", "reserve", "operator override"],
                        "evidence": [str(e.evidence_id) for e in chosen.observation.evidence]
                        if chosen
                        else [],
                        "uncertain": bool(attention or conflict or not view.observations),
                        "proposal": proposal.model_dump(mode="json"),
                        "action": move.name,
                        "safety": status,
                        "reason": reason,
                        "provider": "rules/1",
                    }
                )
            return move
        except Exception as exc:  # noqa: BLE001 - injected provider failures must hold
            self.health.provider_errors += 1
            self.health.status = "failed"
            if self.life.state.value != "ended":
                self.life.change(DroneState.HOLD, now, "cycle failure")
            self.mail.publish(
                ErrorReport(message_type="error_report", code=type(exc).__name__, retryable=True),
                now,
            )
            self.logs.append(
                {"agent": self.owner, "time_ms": now, "error": type(exc).__name__, "action": "HOLD"}
            )
            return Move.INACTIVE if self.override == "end" else Move.HOLD
