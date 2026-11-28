"""Shared decoding and index structures must not change any result."""

import hashlib
import io
from pathlib import Path
from uuid import UUID

import pytest

pytest.importorskip("torch")

import torch
from PIL import Image

from agents.command_agent.agent import CommandAgent, Settings
from agents.drone_agent.reporting import Mailbox
from agents.shared.domain import Cell, Evidence, Observation, ReportedFinding
from communication.messages import HazardDetection
from evaluation.model1.environment_fusion import EnvironmentalFusion
from evaluation.model1.perception import ImageReuse, _image
from evaluation.model1.registry import ModelEntry, ModelRegistry


def encoded(width: int, height: int, kind: str = "PNG") -> bytes:
    image = Image.new("RGB", (width, height))
    image.putdata([((x * 7) % 256, (y * 5) % 256, (x + y) % 256)
                   for y in range(height) for x in range(width)])
    buffer = io.BytesIO()
    image.save(buffer, kind)
    return buffer.getvalue()


@pytest.mark.parametrize("kind", ["PNG", "JPEG"])
def test_shared_decode_gives_bit_identical_tensors_at_every_size(kind: str) -> None:
    payload = encoded(97, 61, kind)
    reuse = ImageReuse(payload)
    for size in (512, 224, 512):
        assert torch.equal(_image(payload, size, reuse), _image(payload, size))
    assert set(reuse.sized) == {224, 512}


def test_reuse_is_bound_to_one_artifact_and_bad_input_is_not_cached() -> None:
    first, second = encoded(8, 8), encoded(9, 9)
    with pytest.raises(ValueError, match="different artifact"):
        _image(second, 32, ImageReuse(first))
    broken = ImageReuse(b"not-an-image")
    for _ in range(2):  # every consumer sees the same failure
        with pytest.raises(OSError):
            _image(broken.payload, 32, broken)
    assert broken.decoded is None and not broken.sized


def test_mapped_loading_copies_weights_and_releases_the_file(tmp_path: Path) -> None:
    source = EnvironmentalFusion()
    path = tmp_path / "selected.pt"
    torch.save({"model_state": source.state_dict(),
                "optimizer_state": {"unused": torch.ones(1000)}}, path)
    entry = ModelEntry(model_id="fusion", task="environment_fusion", state="EXPERIMENTAL",
                       architecture="EnvironmentalFusion", checkpoint=path.name,
                       sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    registry = ModelRegistry({"fusion": entry}, tmp_path, device="cpu")
    model = registry.get("fusion")
    assert registry.get("fusion") is model and registry.loads == {"fusion": 1}
    path.unlink()  # Windows refuses this while any mapping of the file is alive
    for name, tensor in source.state_dict().items():
        assert torch.equal(model.state_dict()[name], tensor)


def reports(agent: CommandAgent, count: int) -> None:
    box = Mailbox("d0", agent.mission, count)
    for n in range(count):
        observation = Observation(
            observation_id=UUID(int=n + 1), cell=Cell(x=n % 3, y=0), observed_ms=5,
            confidence=0.5, evidence=(Evidence(evidence_id=UUID(int=1000 + n), origin="d0",
                                               captured_ms=5, modality="image",
                                               artifact_key="synthetic"),))
        box.publish(HazardDetection(message_type="hazard_detection", observation=observation,
                                    hazard="water"), 5)
        agent.consume(box.sent[-1], "d0", 5)


def test_model2_lookups_match_a_scan_and_belong_to_one_agent() -> None:
    first, second = (CommandAgent(UUID(int=n), frozenset(("d0",)), Settings()) for n in (1, 2))
    reports(first, 30)
    assert first._by_message == {r.message_id: r for r in first.findings.values()}
    for cell, items in first._by_cell.items():
        assert items == [r for r in first.findings.values() if r.finding.observation.cell == cell]
    assert not second._by_message and not second._by_cell
    restored = CommandAgent.restore(first.checkpoint(), first.mission, first.members)
    assert restored._by_cell == first._by_cell


def test_an_injected_memory_is_still_scanned() -> None:
    memory: dict[UUID, ReportedFinding] = {}
    agent = CommandAgent(UUID(int=3), frozenset(("d0",)), Settings(), memory=memory)
    reports(agent, 6)
    assert len(memory) == 6 and not agent._by_message and agent.incidents
