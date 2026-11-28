from random import Random
from uuid import NAMESPACE_OID, uuid5

from agents.shared.domain import Cell, Evidence, Record, SensorFrame
from simulation.core.configuration import Scenario
from simulation.environments.base import Point


class Reading(Record):
    evidence: Evidence
    value: str
    cell: Cell | None
    confidence: float


class Packet(Record):
    frame: SensorFrame
    readings: tuple[Reading, ...]


def sense(
    cfg: Scenario,
    seed: int,
    t: int,
    agent: str,
    pos: Point,
    battery: float,
    heading: str,
    tiles: dict[Point, str],
    people: dict[Point, str],
) -> tuple[Packet, set[str], int, int, set[Point]]:
    readings: list[Reading] = []
    seen = set()
    footprint = set()
    misses = false = 0
    radius, dropout, miss, score = cfg.radius, cfg.dropout, cfg.miss, 0.6
    disabled: set[str] = set()
    namespace = NAMESPACE_OID
    if profile := cfg.field_profile:
        severity = {"easy": 0, "moderate": 1, "difficult": 2}[profile.difficulty]
        dropout = min(1.0, dropout + 0.04 * severity)
        miss = min(1.0, miss + 0.12 * severity)
        score -= 0.08 * severity
        namespace = uuid5(
            NAMESPACE_OID, f"{cfg.scenario_id}/{seed}/{cfg.agents}/{profile.difficulty}"
        )
        if int(agent.removeprefix("d")) % 2:
            disabled.update(profile.alternate_disabled)
        for window in profile.windows:
            if window.start <= t < window.stop:
                radius = min(radius, window.radius)
                disabled.update(window.disabled)
                score -= 0.08
    for mode in cfg.modalities:
        rng = Random(f"{seed}/{agent}/{t}/{mode}")
        if mode in disabled or rng.random() < dropout:
            continue

        def add(value: str, p: Point | None, score: float = 1.0, modality: str = mode) -> None:
            uid = uuid5(namespace, f"{agent}/{t}/{modality}/{len(readings)}")
            readings.append(
                Reading(
                    evidence=Evidence(
                        evidence_id=uid,
                        origin=agent,
                        captured_ms=t * cfg.tick_ms,
                        modality=modality,
                        artifact_key=uid.hex,
                    ),
                    value=value,
                    cell=Cell(x=p[0], y=p[1]) if p is not None else None,
                    confidence=score,
                )
            )

        if mode in ("image", "thermal", "environment"):
            for p, tile in tiles.items():
                if abs(p[0] - pos[0]) + abs(p[1] - pos[1]) > radius:
                    continue
                footprint.add(p)
                if profile and cfg.noise and rng.random() < cfg.noise:
                    add("indistinct", p, score)
                elif profile and mode == "thermal" and tile == "fire":
                    add("thermal_anomaly", p, score)
                else:
                    add(tile, p)
                if mode == "environment" or tile in ("debris", "building", "smoke", "damaged"):
                    continue
                detected = rng.random() >= miss
                spurious = rng.random() < cfg.false_positive
                noisy = rng.random() < cfg.noise
                if p in people:
                    if detected:
                        seen.add(people[p])
                    else:
                        misses += 1
                elif spurious:
                    false += 1
                if (p in people and detected) or (p not in people and spurious):
                    add("possible_human", pos if noisy else p, score)
        else:
            add(
                {"gps": "position", "imu": heading, "text": "survey permitted cells"}[mode],
                pos if mode == "gps" else None,
            )
    cell = Cell(x=pos[0], y=pos[1]) if any(r.evidence.modality == "gps" for r in readings) else None
    frame = SensorFrame(
        agent_id=agent,
        tick_ms=t * cfg.tick_ms,
        samples=tuple(r.evidence for r in readings),
        cell=cell,
        battery_fraction=battery,
    )
    return Packet(frame=frame, readings=tuple(readings)), seen, false, misses, footprint


def fixture_packet(packet: Packet, modalities: tuple[str, ...]) -> Packet:
    """Synthetic media-carrier packet: one evidence reference per modality, no symbolic content.

    Used to exercise model adapters. The references carry no observation of the simulated world.
    """
    own = packet.frame
    readings = tuple(
        Reading(
            evidence=Evidence(
                evidence_id=(uid := uuid5(NAMESPACE_OID, f"fixture/{own.agent_id}/{own.tick_ms}/{m}")),
                origin=own.agent_id,
                captured_ms=own.tick_ms,
                modality=m,
                artifact_key=uid.hex,
            ),
            value="fixture",
            cell=None,
            confidence=1.0,
        )
        for m in modalities
    )
    frame = SensorFrame(
        agent_id=own.agent_id,
        tick_ms=own.tick_ms,
        samples=tuple(r.evidence for r in readings),
        cell=own.cell or Cell(x=0, y=0),
        battery_fraction=own.battery_fraction,
    )
    return Packet(frame=frame, readings=readings)