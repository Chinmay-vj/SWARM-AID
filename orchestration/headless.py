"""Headless execution of one integrated mission without the backend or dashboard.

The stack is the one the backend runs per mission: seeded engine, one independent Model 1
agent per drone with simulated transport, the selected coordination baseline and one Model 2
instance. Results keep operational outputs (what agents, Model 2 and humans could see)
separate from evaluator-only metrics computed from simulator ground truth.
"""

import json
import math
import statistics
import time
import tracemalloc
from collections import Counter
from typing import Any

from backend.integrations.simulation_adapter import MissionConfig, SimulationContext
from orchestration.manifest import config_digest

RESULT_VERSION = "1"


def distribution(values: list[float]) -> dict[str, float | int | None]:
    """Sample count, mean, median, p95, p99, min and max (nearest-rank percentiles)."""
    if not values:
        return {
            "n": 0,
            "mean": None,
            "median": None,
            "p95": None,
            "p99": None,
            "min": None,
            "max": None,
        }
    ordered = sorted(values)

    def rank(p: float) -> float:
        return ordered[min(len(ordered) - 1, max(0, math.ceil(p * len(ordered)) - 1))]

    return {
        "n": len(ordered),
        "mean": round(statistics.fmean(ordered), 4),
        "median": round(statistics.median(ordered), 4),
        "p95": round(rank(0.95), 4),
        "p99": round(rank(0.99), 4),
        "min": round(ordered[0], 4),
        "max": round(ordered[-1], 4),
    }


def operational_fingerprint(ctx: SimulationContext) -> str:
    """Digest of deterministic, simulation-time outputs (no wall-clock values).

    Two runs with the same configuration must produce the same fingerprint if the integrated
    stack is deterministic. Model 2's read model, the router's metrics and every agent's
    reported position are included.
    """
    payload = {
        "t": ctx.engine.t,
        "model2": ctx.command.snapshot(),
        "network": ctx.network.router.metrics(),
        "positions": {a: d.position for a, d in sorted(ctx.engine.drones.items())},
        "tasks": ctx.fleet.assignments.command_snapshot() if ctx.fleet.assignments else None,
    }
    return config_digest(json.loads(json.dumps(payload, default=str)))


def run_mission(config: MissionConfig, *, measure_memory: bool = False) -> dict[str, Any]:
    """Run one mission to completion and return a structured, JSON-serialisable result."""
    build_started = time.perf_counter()
    ctx = SimulationContext(config)
    build_ms = (time.perf_counter() - build_started) * 1000
    if measure_memory:
        tracemalloc.start()
    step_ms: list[float] = []
    model2_timeline: list[tuple[int, str]] = []
    queue_depth: list[int] = []
    last_state = None
    started = time.perf_counter()
    while not ctx.finished:
        tick_started = time.perf_counter()
        ctx.step()
        step_ms.append((time.perf_counter() - tick_started) * 1000)
        state = ctx.command.state
        if state != last_state:
            model2_timeline.append((ctx.now_ms, state))
            last_state = state
        queue_depth.append(len(ctx.network.router.pending))
    wall_ms = (time.perf_counter() - started) * 1000
    peak_mb = None
    if measure_memory:
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_mb = round(peak / 2**20, 2)

    from evaluation.results import DEFINITIONS, metrics

    fixture = ctx.fleet.assignments
    task_states = (
        Counter(t.history[-1].state for t in fixture.tasks.values()) if fixture else Counter()
    )
    router = ctx.network.router.metrics()
    agents = ctx.fleet.agents
    return {
        "result_version": RESULT_VERSION,
        "configuration": config.model_dump(mode="json"),
        "scenario_version": ctx.scenario.version,
        "end_reason": ctx.engine.reason,
        "sim_time_ms": ctx.now_ms,
        "ticks": ctx.engine.t,
        "operational": {
            "model2_counts": dict(ctx.command.counts),
            "model2_incidents": len(ctx.command.incidents),
            "model2_admitted_findings": len(ctx.command.findings),
            "model2_state_timeline": model2_timeline,
            "communication": router,
            "tasks_issued": fixture.issued if fixture else 0,
            "task_final_states": dict(task_states),
            "agent_reported_cells": len(fixture.reported) if fixture else 0,
            "coordination_conflicts": len(fixture.conflicts) if fixture else 0,
            "repeated_reports": fixture.repeated_reports if fixture else 0,
            "safety_interventions": sum(a.health.invalid_actions for a in agents.values()),
            "agents": len(agents),
        },
        "evaluator_only": {
            "warning": "Simulator ground truth. Never shown to agents, Model 2 or operators.",
            "definitions": DEFINITIONS,
            "metrics": metrics(ctx.engine),
        },
        "performance": {
            "wall_clock_ms": round(wall_ms, 3),
            "context_build_ms": round(build_ms, 3),
            "step_ms": distribution(step_ms),
            "router_pending": distribution([float(q) for q in queue_depth]),
            "python_peak_traced_mb": peak_mb,
            "note": "Wall-clock values depend on the host and are not deterministic.",
        },
        "fingerprint": operational_fingerprint(ctx),
    }
