"""Phase 11I gating, deadline and wrapper checks. Synthetic tensors only."""

import json
import time
from pathlib import Path
from typing import Any

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("torchvision")

from torch import nn
from torch.utils.data import DataLoader

from evaluation.model1 import phase11i, phase11i_tasks
from evaluation.model1.active_scope import require_trainable_task
from evaluation.model1.training import (
    ClassificationTask,
    SyntheticTaskDataset,
    TrainingConfig,
    fit,
    synthetic_training_context,
)


def _data() -> SyntheticTaskDataset:
    examples = tuple((torch.ones(4) * (i % 2), torch.tensor(i % 2)) for i in range(8))
    return SyntheticTaskDataset(examples, fixture_id="p11i", fixture_sha256="1" * 64)


def test_thermal_training_is_blocked_but_rgb_is_not() -> None:
    with pytest.raises(ValueError, match="excluded"):
        require_trainable_task("wisard-thermal-human-detection")
    require_trainable_task("wisard-visual-human-detection")
    data = _data()
    with pytest.raises(ValueError, match="excluded"):
        fit(nn.Linear(4, 2), DataLoader(data), DataLoader(data), ClassificationTask(),
            config=TrainingConfig(epochs=1),
            context=synthetic_training_context("wisard-thermal-human-detection", data))


def test_deadline_stops_after_a_checkpointed_epoch(tmp_path: Path) -> None:
    data = _data()
    config = TrainingConfig(epochs=5, checkpoint_every=1, checkpoint_root=Path(tmp_path))
    if tmp_path.resolve().drive.upper() not in {"D:", ""}:
        config = config.model_copy(update={"checkpoint_root": Path(
            "D:/SWARM-AID-DATA/checkpoints/phase11i/smoke") / f"test-{time.time_ns()}"})
    result = fit(nn.Linear(4, 2), DataLoader(data, batch_size=4), DataLoader(data, batch_size=4),
                 ClassificationTask(), config=config,
                 context=synthetic_training_context("deadline", data),
                 model_config={"test": True}, deadline=time.time())
    assert len(result.history) == 1
    assert (config.checkpoint_root / "synthetic/epoch-0001.pt").is_file()


def test_owner_decision_must_match_exact_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    decision = tmp_path / "decision.json"
    monkeypatch.setattr(phase11i, "DECISION", decision)
    (tmp_path / "release.json").write_bytes(b"{}")
    spec: dict[str, Any] = {
        "owner_identity": "owner", "release": str(tmp_path),
        "release_sha256": {"release.json": phase11i_tasks.sha(tmp_path / "release.json")},
        "task_code_sha256": phase11i_tasks.sha(Path(phase11i_tasks.__file__)),
    }
    assert "absent" in str(phase11i.approval_problem("x", spec))
    body: dict[str, Any] = {
        "decision": "PENDING", "approved_at": "2026-01-01T00:00:00+00:00",
        "experiments": {"x": {"config_sha256": phase11i.digest_of(spec),
                              "owner_identity": "owner"}},
    }
    decision.write_text(json.dumps(body))
    assert phase11i.approval_problem("x", spec) is not None
    body["decision"] = "APPROVE_TRAINING_START"
    decision.write_text(json.dumps(body))
    assert phase11i.approval_problem("x", spec) is None
    assert phase11i.approval_problem("y", spec) is not None
    assert phase11i.approval_problem("x", {**spec, "extra": 1}) is not None
    (tmp_path / "release.json").write_bytes(b"[]")
    assert "changed" in str(phase11i.approval_problem("x", spec))


def test_wrappers_keep_shapes_and_are_inert_in_evaluation() -> None:
    jitter = phase11i_tasks.PhotometricJitter(nn.Identity(), 0.2)
    image = torch.rand(2, 3, 8, 8)
    assert not torch.equal(jitter.train()(image), image)
    assert torch.equal(jitter.eval()(image), image)
    audio = phase11i_tasks.AudioMobileNet(50)
    clip = torch.randn(2, 1, 101, 64)
    assert audio.train()(clip).shape == (2, 50)
    assert audio.eval()(clip).shape == (2, 50)
    logits = torch.randn(2, 3, 4, 4, requires_grad=True)
    loss = phase11i_tasks.WeightedSegmentation(torch.ones(3)).loss(
        nn.Identity(), logits, torch.randint(0, 3, (2, 4, 4)))
    torch.autograd.backward(loss)
    assert torch.isfinite(loss)
