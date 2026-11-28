"""Observation -> perception -> memory -> reasoning -> evidence -> network -> Model 2 -> operator.

Synthetic fixtures only. Tests using preserved checkpoints skip when they are absent.
"""

import io
from itertools import product
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("torchvision")
Image = pytest.importorskip("PIL.Image")

from agents.command_agent.agent import Settings as CommandSettings
from agents.drone_agent.evidence import (
    CATEGORIES,
    EvidenceLedger,
    fuse_environment,
)
from agents.shared.domain import Category, Cell, Evidence, Finding, Observation
from communication.messages import CommandAlert
from evaluation.model1 import environment_fusion, registry
from evaluation.model1.perception import Inference, MediaPerception, PerceptionRuntime
from evaluation.model1.phase11j import DATA, REGISTRY, synthetic_inputs
from evaluation.model1.registry import ModelEntry, ModelRegistry, ModelUnavailable
from simulation.adapters.model1 import Fleet
from simulation.core.configuration import Scenario, load
from simulation.core.engine import Engine
from simulation.sensors.mock import fixture_packet

real = pytest.mark.skipif(not REGISTRY.is_file(), reason="preserved registry not present")
VISUAL = ("rescuenet", "floodnet", "flame")
DEVELOPMENT_SEED = 3500  # 42-46 are reserved for evaluation


def png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), (30, 90, 40)).save(buffer, "PNG")
    return buffer.getvalue()


class Resolver:
    def __init__(self, payload: bytes | None) -> None:
        self.payload = payload

    def resolve(self, agent_id: str, evidence: Evidence) -> bytes | None:
        return self.payload


class Scripted(PerceptionRuntime):
    """Test double. Its outputs are scripted fixtures, not model results."""

    def __init__(self, confidence: float = 0.9, kind: str = "hazard", status: str = "accepted"):
        super().__init__(ModelRegistry({}, Path(".")))
        self.confidence, self.kind, self.status = confidence, kind, status

    def infer(self, model_id: str, payload: Any) -> Inference:
        if payload is None:
            return Inference(model_id=model_id, model_version="fixture",
                             availability="missing", status="not_assessed")
        return Inference.model_validate({
            "model_id": model_id, "model_version": "fixture", "availability": "available",
            "status": self.status, "kind": self.kind,
            "category": None if self.kind == "possible_human" else "fire",
            "confidence": self.confidence, "limitations": ("scripted fixture",)})


def engine(agents: int = 2, **changes: Any) -> Engine:
    return Engine(Scenario.model_validate(
        {**load("flood_basic").model_dump(), "agents": agents, "horizon": 12,
         "seed": DEVELOPMENT_SEED, **changes}))


def run(runtime: PerceptionRuntime, payload: bytes | None, ticks: int = 4,
        models: tuple[str, ...] = ("flame",),
        modalities: tuple[str, ...] = ("image", "gps"), **changes: Any
        ) -> tuple[Engine, Fleet, dict[str, EvidenceLedger]]:
    e = engine(**changes)
    fleet = Fleet(e, command=CommandSettings())
    ledgers = {a: EvidenceLedger(a, e.mission_id) for a in fleet.agents}
    for name, agent in fleet.agents.items():
        agent.perception = MediaPerception(
            runtime, Resolver(payload), models, ledgers[name], "synthetic_fixture")
    for _ in range(ticks):
        for name in e.active:
            e.views[name] = fixture_packet(e.views[name], modalities)
        fleet.advance(e)
    return e, fleet, ledgers


def alerts(fleet: Fleet) -> list[CommandAlert]:
    assert fleet.network is not None
    return [m.payload for m in fleet.network.history["operator"]
            if isinstance(m.payload, CommandAlert)]


def test_hazard_reaches_operator_with_provenance_and_requires_review() -> None:
    _, fleet, ledgers = run(Scripted(), png())
    assert all(a.health.provider_errors == 0 for a in fleet.agents.values())
    received = alerts(fleet)
    assert received
    for alert in received:
        records = [r for ledger in ledgers.values()
                   for i in alert.supporting_evidence for r in ledger.lookup(i)]
        assert records and {r.basis for r in records} == {"synthetic_fixture"}
        assert alert.update.incident.category == Category.HAZARD
        assert alert.review_state == "human_review_pending"
        assert alert.update.incident.confirmation_id is None


def test_possible_human_is_never_confirmed() -> None:
    _, fleet, _ = run(Scripted(kind="possible_human"), png(), models=("wisard-rgb",))
    received = alerts(fleet)
    assert received
    assert all(a.update.incident.category in (Category.POSSIBLE, Category.UNCERTAIN)
               for a in received)


@pytest.mark.parametrize("runtime,payload,availability,status", [
    (Scripted(), None, "missing", "not_assessed"),
    (Scripted(confidence=0.2, status="abstained"), b"x", "available", "abstained"),
])
def test_missing_or_low_confidence_creates_no_finding_or_alert(
    runtime: PerceptionRuntime, payload: bytes | None, availability: str, status: str
) -> None:
    _, fleet, ledgers = run(runtime, payload)
    assert not alerts(fleet)
    assert all(not a.memory.items for a in fleet.agents.values())
    items = [i for ledger in ledgers.values() for i in ledger.items]
    assert items
    assert {(i.availability, i.status) for i in items} == {(availability, status)}
    if availability == "missing":
        assert all(i.confidence is None and i.category is None for i in items)


def test_agents_keep_independent_state_and_a_new_episode_is_empty() -> None:
    _, fleet, ledgers = run(Scripted(), png(), agents=3)
    first, second = list(fleet.agents)[:2]
    assert fleet.agents[first].memory is not fleet.agents[second].memory
    assert {i.agent_id for i in ledgers[first].items} == {first}
    with pytest.raises(ValueError):
        ledgers[second].add(ledgers[first].items[0])
    assert all(not a.memory.items for a in Fleet(engine(3)).agents.values())
    ledgers[first].reset(UUID(int=1))
    assert not ledgers[first].items
    # Original observation IDs are unique per evidence, so repeats never overwrite memory.
    memory = fleet.agents[second].memory
    finding = next(iter(memory.items.values()))
    before = len(memory.items)
    memory.remember(finding.model_copy(update={"label": "water"}))
    assert len(memory.items) == before
    assert memory.items[finding.observation.observation_id] == finding
    memory.expire(finding.observation.observed_ms + 10**9)
    assert not memory.items


def test_duplicate_and_conflicting_messages() -> None:
    _, fleet, _ = run(Scripted(), png())
    assert fleet.network is not None and fleet.command is not None
    message = next(m for m in fleet.network.history["command"]
                   if m.payload.message_type == "hazard_detection")
    findings, incidents = len(fleet.command.findings), len(fleet.command.incidents)
    now = fleet.command.last_tick
    assert fleet.command.consume(message, message.source, now) is None
    changed = message.model_copy(update={
        "payload": message.payload.model_copy(update={"hazard": "water"})})
    assert fleet.command.consume(changed, changed.source, now) is None
    assert (len(fleet.command.findings), len(fleet.command.incidents)) == (findings, incidents)
    assert fleet.command.conflicts
    assert type(message).model_validate_json(message.model_dump_json()) == message


def test_communication_interruption_delivers_nothing_to_model_2() -> None:
    _, fleet, ledgers = run(Scripted(), png(), outage_steps=list(range(12)))
    assert fleet.command is not None
    assert not fleet.command.findings and not alerts(fleet)
    assert all(ledger.items for ledger in ledgers.values())
    assert all(a.health.provider_errors == 0 for a in fleet.agents.values())


def test_symbolic_simulation_records_symbolic_basis_and_fuses() -> None:
    e = engine(3)
    fleet = Fleet(e, command=CommandSettings(), record_evidence=True)
    ledgers = fleet.ledgers
    while e.reason == "running":
        fleet.advance(e)
    assert all(a.health.provider_errors == 0 for a in fleet.agents.values())
    items = [i for ledger in ledgers.values() for i in ledger.items]
    assert items and {i.basis for i in items} == {"symbolic_simulator"}
    assert e.seed == DEVELOPMENT_SEED
    assessments = [a for ledger in ledgers.values() for a in ledger.assessments]
    assert assessments and {a.basis for a in assessments} == {"deterministic_inference"}
    assert all((a.category is None) == (a.status != "accepted") for a in assessments)
    assert not Fleet(engine(3), record_evidence=True).ledgers["d0"].items
    with pytest.raises(ValueError, match="symbolic"):
        MediaPerception(Scripted(), Resolver(None), ("flame",), ledgers["d0"],
                        "symbolic_simulator")


def finding(number: int, label: str, mode: str, confidence: float = 1.0) -> Finding:
    source = Evidence(evidence_id=UUID(int=number), origin="d0", captured_ms=0,
                      modality=mode, artifact_key="k")
    return Finding(kind="environment", label=label, observation=Observation(
        observation_id=UUID(int=number), cell=Cell(x=1, y=1), observed_ms=0,
        confidence=confidence, evidence=(source,)))


def test_deterministic_fusion_handles_agreement_conflict_and_unknown() -> None:
    assert dict(environment_fusion.TERRAIN) == {
        k: environment_fusion.LABELS.index(v) for k, v in CATEGORIES.items()}
    agree = fuse_environment([finding(1, "water", "image"), finding(2, "water", "thermal")])[0]
    assert (agree.status, agree.category, agree.missing_modalities) == (
        "accepted", "water", ("environment",))
    conflict = fuse_environment([finding(1, "water", "image"), finding(2, "fire", "thermal")])[0]
    assert (conflict.status, conflict.category, conflict.confidence) == ("conflict", None, None)
    assert fuse_environment([finding(1, "indistinct", "image")])[0].status == "abstained"
    for a, b, score in product(("dry", "water", "fire"), ("dry", "water"), (0.3, 0.9)):
        ours = fuse_environment(
            [finding(1, a, "image", score), finding(2, b, "thermal", score)])[0]
        values = torch.zeros(1, 3, 6)
        for i, label in enumerate((a, b)):
            index = environment_fusion.TERRAIN[label]
            values[0, i, index] = values[0, i, 4] = score
            values[0, i, 5] = 1
        eligible = environment_fusion.eligibility(
            values, torch.tensor([[True, True, False]]))
        assert (ours.status == "accepted") == bool(eligible[0])


def test_thermal_is_excluded_even_if_registered() -> None:
    entry = ModelEntry(model_id="wisard-thermal", task="object_detection", state="READY")
    models = ModelRegistry({"wisard-thermal": entry}, Path("."))
    with pytest.raises(ModelUnavailable, match="EXCLUDED"):
        models.get("wisard-thermal")
    assert PerceptionRuntime(models).infer("wisard-thermal", png()).availability == "excluded"
    _, fleet, _ = run(Scripted(), png(), modalities=("thermal", "gps"))
    assert not alerts(fleet)


def test_missing_and_corrupted_checkpoints_are_unavailable(tmp_path: Path) -> None:
    (tmp_path / "bad.pt").write_bytes(b"not a checkpoint")
    for name, checksum in (("absent.pt", "0" * 64), ("bad.pt", "0" * 64),
                           ("bad.pt", registry.file_sha256(tmp_path / "bad.pt"))):
        entry = ModelEntry(model_id="flame", task="image_classification", state="READY",
                           architecture="mobilenet_v3_small", checkpoint=name, sha256=checksum,
                           config={"image_size": 224, "normalization_mean": [0, 0, 0],
                                   "normalization_scale": [1, 1, 1]})
        runtime = PerceptionRuntime(ModelRegistry({"flame": entry}, tmp_path))
        if name == "bad.pt" and checksum != "0" * 64:
            with pytest.raises(Exception):  # noqa: B017 - torch raises its own pickle errors
                runtime.registry.get("flame")
        else:
            assert runtime.infer("flame", png()).availability == "unavailable"
        assert not runtime.registry.resident


def test_cpu_fallback_and_precision(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    models = ModelRegistry({}, Path("."), device="cuda", precision="bf16")
    assert (models.device.type, models.precision) == ("cpu", "fp32")


@real
def test_every_selected_checkpoint_infers_invalidates_and_shares_bounded_instances() -> None:
    models = ModelRegistry.from_file(REGISTRY, DATA, max_resident=2)
    runtime = PerceptionRuntime(models)
    for model_id, payload in synthetic_inputs(models).items():
        result = runtime.infer(model_id, payload)
        assert result.availability == "available", (model_id, result.details)
        assert len(models.resident) <= 2
        assert runtime.infer(model_id, None).availability == "missing"
        bad: Any = ([[1.0]], [True]) if model_id == "environment-fusion-neural" else b"broken"
        if model_id != "environment-fusion-neural":
            assert runtime.infer(model_id, bad).availability == "invalid", model_id
    assert models.state("wisard-rgb") == "EXPERIMENTAL"
    assert models.state("usgs-water") == "UNAVAILABLE"
    assert all(not p.requires_grad for m in models.resident.values() for p in m.parameters())


@real
def test_cpu_inference_matches_state_and_runs() -> None:
    models = ModelRegistry.from_file(REGISTRY, DATA, device="cpu", precision="fp16")
    result = PerceptionRuntime(models).infer("flame", png())
    assert (result.availability, result.device, result.precision) == ("available", "cpu", "fp32")


@real
@pytest.mark.parametrize("model_id", VISUAL)
def test_real_visual_inference_through_the_whole_path(model_id: str) -> None:
    models = ModelRegistry.from_file(REGISTRY, DATA, max_resident=1)
    _, fleet, ledgers = run(PerceptionRuntime(models), png(), ticks=3, models=(model_id,))
    assert models.loads == {model_id: 1}  # one instance shared by all agents
    assert all(a.health.provider_errors == 0 for a in fleet.agents.values())
    items = [i for ledger in ledgers.values() for i in ledger.items]
    assert items and {i.model_id for i in items} == {model_id}
    assert all(i.availability == "available" and len(i.model_version) == 64 for i in items)
    assert fleet.command is not None
    if any(i.status == "accepted" for i in items):
        assert fleet.command.findings


@real
def test_rtx2060_runtime_configuration_applies() -> None:
    config = Path(__file__).resolve().parents[2] / "configs/rtx2060_runtime.json"
    models = ModelRegistry.from_config(REGISTRY, DATA, config)
    assert models.max_resident == 2
    assert models.precision == ("fp16" if models.device.type == "cuda" else "fp32")
    assert PerceptionRuntime(models).infer("flame", png()).availability == "available"
