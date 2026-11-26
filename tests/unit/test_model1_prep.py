import json
from datetime import datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from evaluation.data import model1_prep
from evaluation.data.contracts import Manifest
from evaluation.data.model1_prep import (
    CandidateManifest,
    audit_flame,
    build_esc50_candidate,
    build_uci_windows,
)


def _uci_rows() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    line = 2
    for offset in range(24 * 20):
        timestamp = datetime(2004, 1, 1) + timedelta(hours=offset)
        result.append(
            {
                "line": line,
                "timestamp": timestamp.isoformat(),
                "measurements": {"CO(GT)": ["1,0", "mg/m3", 1.0, "mg/m3", False]},
            }
        )
        line += 1
    return result


def test_uci_windows_stay_inside_time_partitions() -> None:
    audit, windows = build_uci_windows(_uci_rows(), "AirQualityUCI.csv", "a" * 64)

    assert audit["candidate_windows_by_partition"] == {
        "test": 48,
        "train": 312,
        "validation": 48,
    }
    assert audit["cross_partition_raw_row_overlap"] == 0
    assert all(len(window.source_rows) == 24 for window in windows)
    assert all(window.metadata["horizon_hours"] == 1 for window in windows)
    assert all(window.metadata["lookback_hours"] == 24 for window in windows)


def test_uci_windows_reject_duplicate_timestamps() -> None:
    duplicate = _uci_rows()
    duplicate.append(dict(duplicate[0]))

    with pytest.raises(ValueError, match="duplicate timestamps"):
        build_uci_windows(duplicate, "AirQualityUCI.csv", "a" * 64)


def test_esc50_overlay_excludes_complete_cross_fold_recordings() -> None:
    rows = [
        {
            "group": group,
            "fold": fold,
            "path": f"{group}-{fold}-{i}.wav",
            "sha256": "b" * 64,
            "label": "rain",
            "rate": 44100,
        }
        for group, folds in {
            "131943": (2, 3, 3),
            "134049": (2, 3),
            "209698": (4, 5),
            "234879": (4, 5),
            "123456": (1,),
        }.items()
        for i, fold in enumerate(folds)
    ]

    audit, exclusions, candidates = build_esc50_candidate(rows)

    assert audit["excluded_records"] == 9
    assert len(exclusions) == 9
    assert len(candidates) == 1
    assert candidates[0].source_path == "123456-1-0.wav"


def test_candidate_manifest_is_not_a_training_manifest() -> None:
    payload = {
        "schema_version": "phase10i-candidate-1.0",
        "artifact_kind": "candidate_only_not_approved_training_release",
        "dataset_id": "fixture",
        "dataset_version": None,
        "task": "candidate",
        "records_file": "records.jsonl",
        "records_sha256": "a" * 64,
        "candidate_records": 1,
        "partition_counts": {"train": 1},
        "target_distribution": {},
        "partition_integrity": "PENDING",
        "source_index_sha256": "b" * 64,
        "raw_inventory_sha256": "c" * 64,
        "training_approved": False,
        "approved_training_records": 0,
        "human_review_required": True,
    }

    candidate = CandidateManifest.model_validate(payload)

    assert candidate.training_approved is False
    assert candidate.approved_training_records == 0
    with pytest.raises(ValidationError):
        CandidateManifest.model_validate({**payload, "training_approved": True})
    with pytest.raises(ValidationError):
        Manifest.model_validate(payload)


def _write_flame_fixture(root: Any, *, expected_near: int, same_hash: bool = False) -> None:
    processed = root / "processed" / "phase10g-v1" / "FLAME"
    visual = root / "manifests" / "phase10g-visual-v1" / "FLAME"
    processed.mkdir(parents=True)
    visual.mkdir(parents=True)
    train_hash = "a" * 64
    test_hash = train_hash if same_hash else "b" * 64
    (processed / "index.jsonl").write_text(
        "\n".join(
            [
                '{"path":"train.jpg","split":"train","sha256":"'
                + train_hash
                + '","label":"Fire"}',
                '{"path":"test.jpg","split":"test","sha256":"'
                + test_hash
                + '","label":"No_Fire"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (visual / "frame-hashes.jsonl").write_text(
        '{"path":"train.jpg","split":"train","dhash":"0000000000000000"}\n'
        '{"path":"test.jpg","split":"test","dhash":"0000000000000000"}\n',
        encoding="utf-8",
    )
    (visual / "summary.json").write_text(
        json.dumps({"counts": {"train_frames_near_any_test_frame": expected_near}}),
        encoding="utf-8",
    )


def test_flame_audit_matches_frozen_near_test_count(tmp_path: Any, monkeypatch: Any) -> None:
    _write_flame_fixture(tmp_path, expected_near=1)
    monkeypatch.setattr(model1_prep, "near_pairs", lambda _: [(0, 1)])

    summary, overlay, candidates = audit_flame(tmp_path)

    assert summary["training_frames_excluded"] == 1
    assert len(overlay) == 1
    assert [row.source_path for row in candidates] == ["test.jpg"]


def test_flame_audit_rejects_mismatched_frozen_count(tmp_path: Any, monkeypatch: Any) -> None:
    _write_flame_fixture(tmp_path, expected_near=2)
    monkeypatch.setattr(model1_prep, "near_pairs", lambda _: [(0, 1)])

    with pytest.raises(ValueError, match="frozen visual audit"):
        audit_flame(tmp_path)


def test_flame_audit_rejects_exact_cross_split_hashes(tmp_path: Any, monkeypatch: Any) -> None:
    _write_flame_fixture(tmp_path, expected_near=0, same_hash=True)
    monkeypatch.setattr(model1_prep, "near_pairs", lambda _: [])

    with pytest.raises(ValueError, match="exact content hashes"):
        audit_flame(tmp_path)
