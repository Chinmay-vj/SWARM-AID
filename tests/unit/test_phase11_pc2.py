import copy
import importlib.util
import json
from pathlib import Path

import pytest

if importlib.util.find_spec("torch") is None:
    pytest.skip("optional ML dependencies unavailable", allow_module_level=True)

import torch
from torch import nn
from torch.utils.data import DataLoader

from evaluation.model1.data import require_active_source
from evaluation.model1.models import MissingAwareFusion, SensorSequenceModel
from evaluation.model1.temporal import AgentTemporalContext, TemporalHead
from evaluation.model1.training import (
    ClassificationTask,
    SyntheticTaskDataset,
    TrainingConfig,
    fit,
    synthetic_training_context,
)


def test_missing_nan_and_invalid_present_features() -> None:
    fusion = MissingAwareFusion({"rgb": 3, "thermal": 2}, hidden_dim=4)
    values = {"rgb": torch.ones(2, 3), "thermal": torch.full((2, 2), float("nan"))}
    masks = {"rgb": torch.tensor([True, False]), "thermal": torch.tensor([False, False])}
    result, valid = fusion(values, masks)
    assert valid.tolist() == [True, False]
    assert torch.isfinite(result).all() and result[1].eq(0).all()
    result.sum().backward()
    assert all(p.grad is None or torch.isfinite(p.grad).all() for p in fusion.parameters())
    masks["thermal"][0] = True
    with pytest.raises(ValueError, match="finite"):
        fusion(values, masks)
    sensor = SensorSequenceModel(2, 2)
    with pytest.raises(ValueError, match="finite"):
        sensor(torch.full((1, 3, 2), float("nan")), torch.ones(1, 3, 2, dtype=torch.bool))


def test_temporal_agents_share_weights_not_history() -> None:
    model = TemporalHead(3, 5, 2).eval()
    first, second = AgentTemporalContext("a", model), AgentTemporalContext("b", model)
    feature = torch.ones(1, 3)
    a = first.observe("a", 1, feature, True)
    b = second.observe("b", 1, feature, True)
    assert torch.equal(a.logits, b.logits)
    first.observe("a", 2, feature * 2, True)
    second.observe("b", 2, feature * float("nan"), False)
    replay = AgentTemporalContext("b", model)
    replay.observe("b", 1, feature, True)
    assert torch.equal(
        second.observe("b", 3, feature, True).logits, replay.observe("b", 3, feature, True).logits
    )
    with pytest.raises(ValueError, match="owner"):
        first.observe("b", 4, feature, True)
    with pytest.raises(ValueError, match="tick"):
        first.observe("a", 2, feature, True)
    first.reset()
    assert torch.equal(first.observe("a", 1, feature, True).logits, a.logits)


@pytest.mark.parametrize("name", ["HERIDAL", "sard"])
def test_historical_sources_remain_excluded(name: str) -> None:
    with pytest.raises(ValueError, match="excluded"):
        require_active_source(name)


@pytest.mark.parametrize("device", ["cpu", "cuda"])
def test_epoch_resume_matches_uninterrupted_rng_and_optimizer(tmp_path: Path, device: str) -> None:
    if device == "cuda" and not torch.cuda.is_available():
        pytest.skip("CUDA unavailable")
    torch.manual_seed(2025)
    model = nn.Sequential(nn.Linear(3, 5), nn.Dropout(0.2), nn.Linear(5, 2))
    initial = copy.deepcopy(model.state_dict())
    examples = tuple((torch.randn(3), torch.tensor(i % 2)) for i in range(7))
    fixture = SyntheticTaskDataset(examples, fixture_id="resume", fixture_sha256="a" * 64)
    context = synthetic_training_context("fixture", fixture)

    def loaders() -> tuple[DataLoader[object], DataLoader[object]]:
        return (
            DataLoader(
                fixture, batch_size=2, shuffle=True, generator=torch.Generator().manual_seed(9)
            ),
            DataLoader(fixture, batch_size=3),
        )

    config = TrainingConfig(
        device=device,
        mixed_precision=device == "cuda",
        amp_dtype="float16",
        epochs=3,
        seed=2025,
        gradient_accumulation=2,
        checkpoint_every=1,
        checkpoint_root=tmp_path / "full",
    )
    train, val = loaders()
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001)
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=1, gamma=0.8)
    full = fit(
        model,
        train,
        val,
        ClassificationTask(),
        config=config,
        context=context,
        optimizer=optimizer,
        scheduler=scheduler,
        model_config={"kind": "fixture"},
    )
    expected = copy.deepcopy(model.state_dict())
    model.load_state_dict(initial)
    config = config.model_copy(update={"checkpoint_root": tmp_path / "resume"})
    train, val = loaders()
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001)
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=1, gamma=0.8)
    fit(
        model,
        train,
        val,
        ClassificationTask(),
        config=config,
        context=context,
        optimizer=optimizer,
        scheduler=scheduler,
        model_config={"kind": "fixture"},
        stop_after_epoch=1,
    )
    path = config.checkpoint_root / "synthetic/epoch-0001.pt"
    checksum = json.loads(path.with_suffix(".json").read_bytes())["sha256"]
    train, val = loaders()
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001)
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=1, gamma=0.8)
    resumed = fit(
        model,
        train,
        val,
        ClassificationTask(),
        config=config,
        context=context,
        optimizer=optimizer,
        scheduler=scheduler,
        model_config={"kind": "fixture"},
        resume_path=path,
        resume_sha256=checksum,
    )
    with pytest.raises(ValueError, match="checksum"):
        fit(
            model,
            train,
            val,
            ClassificationTask(),
            config=config,
            context=context,
            model_config={"kind": "fixture"},
            resume_path=path,
            resume_sha256="0" * 64,
        )
    assert resumed == full
    assert all(torch.equal(value, model.state_dict()[name]) for name, value in expected.items())
