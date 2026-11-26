import json
from pathlib import Path

import pytest

from evaluation.data.contracts import Manifest, Registry
from evaluation.data.training_partition import approved_training


def test_active_scope_preserves_other_registry_entries() -> None:
    folder = Path('configs/datasets')
    old = Registry.model_validate_json((folder / 'registry.phase10i-v1.json').read_bytes())
    active = Registry.model_validate_json((folder / 'registry.phase10j-v1.json').read_bytes())
    assert active.datasets == tuple(d for d in old.datasets if d.dataset_id not in {'heridal', 'sard'})
    scope = json.loads((folder / 'phase10j_scope.json').read_bytes())
    assert scope['reserved_evaluation_seeds'] == [42, 43, 44, 45, 46]
    assert not scope['training_approved']
    assert all(t['status'] == 'BLOCKED' for t in scope['tasks'])


@pytest.mark.parametrize('dataset_id', ['heridal', 'sard'])
def test_excluded_sources_fail_training_gate(dataset_id: str, tmp_path: Path) -> None:
    registry = Registry.model_validate_json(
        Path('configs/datasets/registry.phase10j-v1.json').read_bytes()
    )
    manifest = Manifest.model_validate({
        'schema_version': '1.0', 'manifest_version': 'test-only',
        'dataset_id': dataset_id, 'dataset_version': 'test-only',
        'origin': 'real', 'role': 'operational', 'samples': [{
            'sample_id': 'fixture', 'source_ref': 'fixture', 'source_id': 'fixture',
            'licence_ref': 'fixture', 'modality': 'image', 'representation': 'physical',
            'split': 'train', 'sequence_id': 'fixture',
            'asset': {'path': 'raw/fixture.jpg', 'sha256': 'a' * 64,
                      'availability': 'available'},
        }],
    })
    with pytest.raises(ValueError, match='unknown dataset version'):
        next(approved_training(registry, (manifest,), tmp_path, task_id='person-detection'))
