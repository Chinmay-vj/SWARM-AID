"""Phase 9 cross-component integration: the stack the backend runs, exercised headless.

Simulation observation -> Model 1 -> simulated transport -> Model 2, with coordination, fault
fixtures, provenance, time and coordinate consistency, agent isolation and evaluator isolation.
"""

import gc
import types
from collections import Counter
from typing import Any

import pytest

from agents.drone_agent.agent import DroneAgent
from agents.drone_agent.components import Memory
from backend.integrations.simulation_adapter import MissionConfig, SimulationContext
from communication.messages import (
    EnvironmentalObservation,
    HazardDetection,
    PossibleHumanDetection,
)
from simulation.core.engine import Drone, Engine
from simulation.entities import Hazard, Person

REPORTS = (EnvironmentalObservation, HazardDetection, PossibleHumanDetection)


def run(scenario: str = "flood_basic", **config: Any) -> SimulationContext:
    ctx = SimulationContext(MissionConfig(scenario_id=scenario, **config))
    while not ctx.finished:
        ctx.step()
    return ctx


def reachable(root: object, limit: int = 200_000) -> list[object]:
    """Objects reachable from root through references (modules, classes and functions are
    not followed: they reach everything through globals)."""
    seen: set[int] = {id(root)}
    stack: list[object] = [root]
    out: list[object] = []
    skip = (types.ModuleType, type, types.FunctionType, types.BuiltinFunctionType)
    while stack and len(out) < limit:
        obj = stack.pop()
        out.append(obj)
        for ref in gc.get_referents(obj):
            if id(ref) in seen or isinstance(ref, skip):
                continue
            seen.add(id(ref))
            stack.append(ref)
    return out


@pytest.fixture(scope="module")
def flood() -> SimulationContext:
    return run("flood_basic", agents=6, seed=42)


def test_reports_reach_model2_with_provenance(flood: SimulationContext) -> None:
    inbox = {m.message_id: m for m in flood.network.history["command"]}
    findings = list(flood.command.findings.values())
    assert len(findings) > 20, "Model 2 admitted too few reports to be meaningful"
    reporters = set()
    for record in findings:
        message = inbox[record.message_id]  # every admitted finding came through transport
        assert isinstance(message.payload, REPORTS)
        assert message.payload.observation == record.finding.observation
        reporters.add(message.source)
        for evidence in record.finding.observation.evidence:
            # Evidence keeps its original capturing agent through forwarding and fusion.
            assert evidence.origin == message.source
    assert reporters == set(flood.engine.drones), "every independent agent reported"


def test_incidents_cite_only_admitted_reports(flood: SimulationContext) -> None:
    admitted = {r.message_id for r in flood.command.findings.values()}
    assert flood.command.history, "Model 2 produced no incident updates"
    for update in flood.command.history:
        assert set(update.incident.reports) <= admitted
        if update.recommendation is not None:
            assert update.recommendation.incident_id == update.incident.incident_id
            assert update.recommendation.incident_revision == update.incident.revision


def test_time_and_coordinates_are_consistent(flood: SimulationContext) -> None:
    width, height = flood.scenario.width, flood.scenario.height
    end = flood.now_ms
    for message in flood.network.history["command"]:
        assert message.sent_ms <= end
        if isinstance(message.payload, REPORTS):
            obs = message.payload.observation
            assert obs.observed_ms <= message.sent_ms, "observation reported before capture"
            if obs.cell is not None:  # missing locations stay missing, never (0, 0)
                assert 0 <= obs.cell.x < width and 0 <= obs.cell.y < height
            for evidence in obs.evidence:
                assert evidence.captured_ms <= message.sent_ms
    times = [m.sent_ms for m in flood.network.history["command"]]
    assert times == sorted(times), "command inbox delivered out of simulation-time order"


def test_peer_to_peer_delivery_between_independent_agents(flood: SimulationContext) -> None:
    drones = set(flood.engine.drones)
    peer = [
        e
        for e in flood.network.router.events
        if e["event"] == "delivered" and e["sender"] in drones and e["recipient"] in drones
    ]
    assert peer, "no drone-to-drone delivery under shared_information"


def test_coordination_tasks_follow_lifecycle(flood: SimulationContext) -> None:
    fixture = flood.fleet.assignments
    assert fixture is not None and fixture.issued > 0
    from simulation.adapters.task_registry import TERMINAL

    for task in fixture.tasks.values():
        assert task.member in flood.engine.drones
        times = [h.time_ms for h in task.history]
        assert times == sorted(times), "task history out of simulation-time order"
        states = [h.state for h in task.history]
        terminal = [i for i, state in enumerate(states) if state in TERMINAL]
        assert not terminal or terminal[0] == len(states) - 1, f"activity after terminal: {states}"


def test_agents_keep_private_memory_and_no_ground_truth() -> None:
    ctx = SimulationContext(MissionConfig(scenario_id="flood_basic", agents=3, seed=42))
    for _ in range(8):
        ctx.step()
    agents = ctx.fleet.agents
    memories = {name: agent.memory for name, agent in agents.items()}
    assert len({id(m) for m in memories.values()}) == len(agents)
    forbidden = (Engine, Person, Hazard, Drone, SimulationContext)
    for name, agent in agents.items():
        graph = reachable(agent)
        leaks = Counter(type(o).__name__ for o in graph if isinstance(o, forbidden))
        assert not leaks, f"{name} can reach simulator ground truth: {dict(leaks)}"
        others = [
            o
            for o in graph
            if isinstance(o, (DroneAgent, Memory)) and o not in (agent, agent.memory)
        ]
        assert not others, f"{name} can reach another agent's private state"
    command_graph = reachable(ctx.command)
    assert not [o for o in command_graph if isinstance(o, forbidden + (DroneAgent, Memory))], (
        "Model 2 can reach ground truth or Model 1 private state"
    )


def test_identical_configuration_reproduces_identically() -> None:
    from orchestration.headless import run_mission

    config = MissionConfig(scenario_id="wildfire_basic", agents=3, seed=44)
    first, second = run_mission(config), run_mission(config)
    assert first["fingerprint"] == second["fingerprint"]
    assert first["operational"] == second["operational"]
    other = run_mission(config.model_copy(update={"seed": 45}))
    assert other["fingerprint"] != first["fingerprint"]


def test_headless_result_separates_operational_and_evaluator_data() -> None:
    from orchestration.headless import run_mission

    result = run_mission(MissionConfig(scenario_id="flood_basic", agents=3, seed=42))
    evaluator_keys = {"people_observed", "false_positive", "missed", "coverage"}
    assert not evaluator_keys & set(result["operational"])
    assert evaluator_keys <= set(result["evaluator_only"]["metrics"])
    assert "ground truth" in result["evaluator_only"]["warning"].lower()


@pytest.mark.parametrize(
    ("scenario", "check"),
    [
        ("flood_network_loss", "dropped"),
        ("flood_network_duplicate", "duplicate"),
        ("flood_network_partition", "partition"),
        ("flood_network_delay", "delivered"),
        ("flood_network_reorder", "delivered"),
        ("flood_agent_disconnected", "connection_lost"),
        ("flood_server_unavailable", "model2_offline"),
        ("flood_outage", "model2_offline"),
        ("flood_unavailable", "inactive_agent"),
        ("command_missing_modalities", "modalities"),
        ("command_stale", "stale"),
        ("flood_noise", "delivered"),
    ],
)
def test_fault_fixtures_degrade_without_failing(scenario: str, check: str) -> None:
    ctx = run(scenario, agents=6, seed=42)
    assert ctx.engine.reason in ("horizon", "inactive")
    metrics = ctx.network.router.metrics()
    assert int(str(metrics["delivered"])) <= int(str(metrics["generated"])) * 6
    if check == "dropped":
        assert int(str(metrics["dropped"])) > 0
    elif check == "duplicate":
        assert int(str(metrics["duplicate"])) > 0 or ctx.command.counts["duplicate"] > 0
    elif check == "partition":
        assert float(str(metrics["delivery_ratio"])) < 1.0
    elif check == "connection_lost":
        assert int(str(metrics["connection_lost"])) > 0
    elif check == "model2_offline":
        assert ctx.command.counts["offline"] >= 1 and ctx.command.counts["recovered"] >= 1
    elif check == "stale":
        # Reports delayed beyond Model 2's freshness window are refused, never fused.
        assert ctx.command.counts["stale"] > 0
        assert not ctx.command.findings and not ctx.command.incidents
        return
    elif check == "inactive_agent":
        assert any(not d.active for d in ctx.engine.drones.values())
    elif check == "modalities":
        allowed = set(ctx.scenario.modalities)
        for message in ctx.network.history["command"]:
            if isinstance(message.payload, REPORTS):
                assert {e.modality for e in message.payload.observation.evidence} <= allowed
    assert ctx.command.findings, "Model 2 received no reports under this fault"
