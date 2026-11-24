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
    for mode in cfg.modalities:
        rng = Random(f"{seed}/{agent}/{t}/{mode}")
        if rng.random() < cfg.dropout:
            continue

        def add(value: str, p: Point, score: float = 1.0, modality: str = mode) -> None:
            uid = uuid5(NAMESPACE_OID, f"{agent}/{t}/{modality}/{len(readings)}")
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
                    cell=Cell(x=p[0], y=p[1]),
                    confidence=score,
                )
            )

        if mode in ("image", "thermal", "environment"):
            for p, tile in tiles.items():
                if abs(p[0] - pos[0]) + abs(p[1] - pos[1]) > cfg.radius:
                    continue
                footprint.add(p)
                add(tile, p)
                if mode == "environment" or tile in ("debris", "building", "smoke", "damaged"):
                    continue
                detected = rng.random() >= cfg.miss
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
                    add("possible_human", pos if noisy else p, 0.6)
        else:
            add({"gps": "position", "imu": heading, "text": "survey permitted cells"}[mode], pos)
    cell = Cell(x=pos[0], y=pos[1]) if any(r.evidence.modality == "gps" for r in readings) else None
    frame = SensorFrame(
        agent_id=agent,
        tick_ms=t * cfg.tick_ms,
        samples=tuple(r.evidence for r in readings),
        cell=cell,
        battery_fraction=battery,
    )
    return Packet(frame=frame, readings=tuple(readings)), seen, false, misses, footprint
