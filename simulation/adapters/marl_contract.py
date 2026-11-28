"""Versioned Phase 12 observation, action, reward and seed contracts (no policy training).

Policy-visible: the agent's own current packet, its bounded memory (own and delivered
peer findings), its own search history, public mission geometry, battery and link state.
Evaluator-only: tiles, people, hazards, true coverage and any future observation.
"""

from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray

from agents.drone_agent.components import Settings
from agents.shared.domain import Cell, Record
from simulation.core.engine import Move
from simulation.environments.base import BLOCKED

OBSERVATION_VERSION = "obs-1"
ACTION_VERSION = "action-1"
SEED_PROTOCOL_VERSION = "seeds-1"

# Policy actions keep the simulator's Move identifiers. HOLD leaves the agent's own
# observe/report/request behaviour in place, so a policy cannot suppress reporting.
ACTIONS = (Move.HOLD, Move.NORTH, Move.EAST, Move.SOUTH, Move.WEST)
OFFSETS = {Move.NORTH: (0, -1), Move.EAST: (1, 0), Move.SOUTH: (0, 1), Move.WEST: (-1, 0)}

RADIUS = 2
CHANNELS = ("known", "hazard", "possible_human", "blocked", "confidence", "uncertain",
            "peer_reported", "previously_searched", "outside_authorized_area")
SELF_FIELDS = ("x", "y", "position_known", "battery", "link_up", "elapsed", "has_readings",
               "searched_fraction", "unsearched_dx", "unsearched_dy", "peer_findings")
SENSORS = ("image", "thermal", "environment", "gps")
FIELDS = (
    *SELF_FIELDS,
    *(f"missing_{s}" for s in SENSORS),
    *(f"cell[{dx},{dy}].{c}" for dy in range(-RADIUS, RADIUS + 1)
      for dx in range(-RADIUS, RADIUS + 1) for c in CHANNELS),
)
SIZE = len(FIELDS)

DEVELOPMENT_SEEDS = range(12000, 13000)
VALIDATION_SEEDS = range(13000, 14000)
PROPOSED_FINAL_SEEDS = range(900000, 900100)
LEGACY_RESERVED_SEEDS = range(42, 47)


def require_open_seed(seed: int) -> Literal["development", "validation"]:
    """Only the Phase 12 development and validation namespaces can start an episode."""
    if seed in DEVELOPMENT_SEEDS:
        return "development"
    if seed in VALIDATION_SEEDS:
        return "validation"
    raise ValueError(f"seed {seed} is not an open Phase 12 development or validation seed")


def encode(
    agent: Any,
    packet: Any,
    searched: set[tuple[int, int]],
    bounds: tuple[int, int],
    restricted: frozenset[Cell],
    link_up: bool,
    elapsed: float,
    now: int,
    settings: Settings,
) -> NDArray[np.float32]:
    """Deterministic float32 vector in [-1, 1]. `searched` is updated from agent knowledge."""
    width, height = bounds
    cell = packet.frame.cell
    known: dict[tuple[int, int], list[Any]] = {}
    peers = 0
    for finding in agent.memory.recent(now - settings.ttl_ms):
        observation = finding.observation
        peers += any(e.origin != agent.owner for e in observation.evidence)
        if observation.cell is not None:
            key = (observation.cell.x, observation.cell.y)
            known.setdefault(key, []).append(finding)
    previously = set(searched)
    searched.update(known)

    sensed = {r.evidence.modality for r in packet.readings}
    values = np.zeros(SIZE, dtype=np.float32)
    area = width * height - len(restricted)
    values[0] = cell.x / max(width - 1, 1) if cell else -1
    values[1] = cell.y / max(height - 1, 1) if cell else -1
    values[2] = cell is not None
    values[3] = packet.frame.battery_fraction
    values[4] = link_up
    values[5] = min(elapsed, 1)
    values[6] = bool(packet.readings)
    values[7] = min(len(searched) / max(area, 1), 1)
    if cell:
        blocked = {(c.x, c.y) for c in restricted}
        remaining = [(abs(x - cell.x) + abs(y - cell.y), x, y)
                     for x in range(width) for y in range(height)
                     if (x, y) not in searched and (x, y) not in blocked]
        if remaining:
            _, x, y = min(remaining)
            values[8] = (x - cell.x) / max(width - 1, 1)
            values[9] = (y - cell.y) / max(height - 1, 1)
    values[10] = min(peers / 16, 1)
    start = len(SELF_FIELDS)
    for i, sensor in enumerate(SENSORS):
        values[start + i] = sensor not in sensed
    if cell is None:
        return values
    start += len(SENSORS)
    for dy in range(-RADIUS, RADIUS + 1):
        for dx in range(-RADIUS, RADIUS + 1):
            x, y = cell.x + dx, cell.y + dy
            patch = values[start : start + len(CHANNELS)]
            start += len(CHANNELS)
            if not (0 <= x < width and 0 <= y < height) or Cell(x=x, y=y) in restricted:
                patch[8] = 1
                continue
            findings = known.get((x, y), [])
            labels: dict[int, set[str]] = {}
            for f in findings:
                if f.kind != "possible_human":
                    labels.setdefault(f.observation.observed_ms, set()).add(f.label or "")
            patch[0] = bool(findings)
            patch[1] = any(f.kind == "hazard" for f in findings)
            patch[2] = any(f.kind == "possible_human" for f in findings)
            patch[3] = any(f.label in BLOCKED for f in findings)
            patch[4] = max((f.observation.confidence for f in findings), default=0)
            patch[5] = any(len(v) > 1 or "indistinct" in v for v in labels.values())
            patch[6] = any(e.origin != agent.owner for f in findings
                           for e in f.observation.evidence)
            patch[7] = (x, y) in previously
    return values


def action_mask(
    packet: Any, bounds: tuple[int, int], restricted: frozenset[Cell], link_up: bool,
    settings: Settings,
) -> NDArray[np.int8]:
    """Public constraints only. Unseen obstacles are still vetoed by the simulator."""
    mask = np.zeros(len(ACTIONS), dtype=np.int8)
    mask[0] = 1
    cell = packet.frame.cell
    if (cell is None or not link_up
            or packet.frame.battery_fraction * 100 - 2 < settings.reserve * 100 - 1e-8):
        return mask
    for index, move in enumerate(ACTIONS[1:], start=1):
        x, y = cell.x + OFFSETS[move][0], cell.y + OFFSETS[move][1]
        mask[index] = (0 <= x < bounds[0] and 0 <= y < bounds[1]
                       and Cell(x=x, y=y) not in restricted)
    return mask


class RewardConfig(Record):
    """Research reward over simulator outcomes. Nothing rewards claims about people."""

    # reward-1 "redundant": fraction of the footprint already covered (kept for comparison).
    # reward-2 "redundant": 1 when the agent moves back to a cell it already occupied.
    version: Literal["reward-1", "reward-2"] = "reward-1"
    new_cell: float = 0.1  # per newly covered team cell, split among first observers
    redundant: float = -0.02  # fraction of this step's footprint already covered
    corroborated: float = 0.01  # first time a cell has two spatial modalities, once per cell
    resolved_uncertainty: float = 0.05  # indistinct cell later clearly observed, once per cell
    rejected_action: float = -0.1  # own movement refused by gate, simulator or invalid id
