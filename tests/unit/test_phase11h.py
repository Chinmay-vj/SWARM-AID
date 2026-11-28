"""Synthetic-only Phase 11H contracts; no real checkpoint or reserved data access."""
import importlib.util
import json
from pathlib import Path

import pytest

if importlib.util.find_spec('torch') is None:
    pytest.skip('optional ML dependencies unavailable', allow_module_level=True)

import numpy as np
import torch

from evaluation.model1.environment_fusion import (
    EnvironmentalDataset,
    EnvironmentalFusion,
    EpisodePlan,
    category,
    development_plans,
    eligibility,
    generate,
    project,
    readiness,
    verify,
)
from evaluation.model1.frozen_features import FeatureProvenance, FrozenFeatureAdapter
from evaluation.model1.models import AudioClassifier, SensorSequenceModel


def identity(value: object) -> object:
    return value


def test_frozen_adapters() -> None:
    for name, model, source in (
        ('audio', AudioClassifier(3), torch.ones(2, 1, 8, 8)),
        ('sensor', SensorSequenceModel(2, 1), {'values': torch.ones(2, 3, 2),
                                             'available': torch.ones(2, 3, 2, dtype=torch.bool)}),
    ):
        provenance = FeatureProvenance.model_validate({'component': name,
            'checkpoint_sha256': 'a' * 64, 'preprocessing_sha256': 'b' * 64,
            'source_manifest_sha256': 'c' * 64, 'authorization_id': 'synthetic-only'})
        adapter = FrozenFeatureAdapter(model, identity, provenance)
        before = {k: v.clone() for k, v in model.state_dict().items()}
        adapter.train()
        if name == 'sensor':
            assert isinstance(source, dict)
            source['available'][1] = False
        features, valid = adapter(source)
        assert valid.tolist() == ([True, False] if name == 'sensor' else [True, True])
        if name == 'sensor':
            assert features[1].eq(0).all()
        assert features.shape == (2, 128) and not features.requires_grad
        assert not model.training and not any(p.requires_grad for p in model.parameters())
        assert all(torch.equal(before[k], v) for k, v in model.state_dict().items())


def test_missing_conflicting_and_invalid_evidence() -> None:
    model = EnvironmentalFusion()
    values = torch.zeros(3, 3, 6)
    values[:, :, 0] = 1
    values[:, :, 4:] = 1
    mask = torch.ones(3, 3, dtype=torch.bool)
    mask[0] = False
    values[0] = float('nan')
    values[1, 1, 0] = 0
    values[1, 1, 1] = 1
    logits, valid = model(values, mask)
    assert valid.tolist() == [False, False, True]
    assert logits[:2].eq(0).all() and torch.isfinite(logits).all()
    values[2, 0, 0] = float('nan')
    with pytest.raises(ValueError, match='finite'):
        model(values, mask)


def test_symbolic_release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr('evaluation.model1.environment_fusion.DATA_ROOT', tmp_path)
    for seed in range(42, 47):
        with pytest.raises(ValueError, match='reserved'):
            EpisodePlan(scenario='flood_basic', seed=seed, split='train')
    plan = EpisodePlan(scenario='flood_basic', seed=2025, split='train', ticks=2)
    other = EpisodePlan(scenario='flood_basic', seed=2026, split='validation', ticks=2)
    with pytest.raises(ValueError, match='unique'):
        generate((plan, plan.model_copy(update={'split': 'validation'})), tmp_path)
    output = generate((plan, other), tmp_path)
    assert generate((plan, other), tmp_path) == output
    with np.load(output / 'inputs.npz', allow_pickle=False) as inputs:
        assert set(inputs.files) == {'values', 'available', 'split', 'classification_eligible'}
        assert inputs['values'].shape[1:] == (3, 6)
        assert set(inputs['split']) == {'train', 'validation'}
        assert not inputs['available'][2::5].any()
    targets = np.load(output / 'targets.npy', allow_pickle=False)
    assert np.all(targets.reshape(-1, 5) == targets.reshape(-1, 5)[:, :1])
    training = EnvironmentalDataset(output, 'train')
    abstention = EnvironmentalDataset(output, 'train', subset='abstention')
    assert len(training) and len(abstention)
    report = json.loads((output / 'readiness.json').read_bytes())
    assert report['status'] == 'BLOCKED'  # Small unit fixture cannot claim 60/20 readiness.
    with (output / 'targets.npy').open('ab') as stream:
        stream.write(b'corruption')
    with pytest.raises(ValueError, match='integrity'):
        verify(output)


def test_mapping_mixtures_and_episode_coverage() -> None:
    assert category('water') == 1 and category('fire') == 2 and category('debris') == 3
    assert category('dry') == 0 and category('new_unknown_terrain') is None
    assert category('possible_human') is None
    x, present = project(())
    assert not x.any() and not present.any()
    values = torch.zeros(1, 3, 6)
    values[:, :, :2] = .5
    values[:, :, 4:] = 1
    masks = torch.ones(1, 3, dtype=torch.bool)
    assert eligibility(values, masks).item()  # Compatible mixtures are not contradictions.
    masks[:, 1:] = False
    assert eligibility(values, masks).item()  # Partial availability remains eligible.
    plans = development_plans()
    assert len(plans) == 80 and sum(p.split == 'train' for p in plans) == 60
    assert len({p.seed for p in plans}) == 80
    assert not {p.seed for p in plans}.intersection(range(42, 47))
    for split in ('train', 'validation'):
        assert len({p.scenario for p in plans if p.split == split}) == 8


def test_duplicate_parent_and_split_rejected() -> None:
    plan = EpisodePlan(scenario='flood_basic', seed=2025, split='train')
    row = {'sample_id': 'one', 'parent_id': 'parent', 'episode': 'flood_basic/2025',
           'variant': 'native', 'seed': 2025, 'observation_ids': ['obs']}
    with pytest.raises(ValueError, match='duplicate native parent'):
        readiness(np.array([0, 0]), np.array(['train', 'train']), np.array([True, True]),
                  [row, {**row, 'sample_id': 'two'}], (plan,))
    with pytest.raises(ValueError, match='split mismatch'):
        readiness(np.array([0]), np.array(['validation']), np.array([True]), [row], (plan,))
