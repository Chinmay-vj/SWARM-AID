import hashlib
import json
from pathlib import Path

import pytest

from evaluation.data.phase10h_verify import (
    _evidence_paths,
    _validate_evidence_inventory,
    verify_release,
    verify_repository_inventory,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_repository_verifier_reports_new_files_without_requiring_them_in_snapshot(
    tmp_path: Path,
) -> None:
    old = tmp_path / "evaluation" / "data" / "old.py"
    new = tmp_path / "evaluation" / "data" / "new.py"
    old.parent.mkdir(parents=True)
    old.write_text("frozen\n", encoding="utf-8")
    new.write_text("later phase\n", encoding="utf-8")

    discovered = {
        "evaluation/data/old.py",
        "evaluation/data/new.py",
    }
    assert verify_repository_inventory(
        tmp_path, {"evaluation/data/old.py": _sha(old)}, discovered
    ) == ["evaluation/data/new.py"]


def test_repository_verifier_rejects_missing_recorded_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="recorded Phase 10H file is missing"):
        verify_repository_inventory(
            tmp_path, {"evaluation/data/missing.py": "a" * 64}, set()
        )


def test_repository_verifier_rejects_modified_recorded_file(tmp_path: Path) -> None:
    path = tmp_path / "evaluation" / "data" / "old.py"
    path.parent.mkdir(parents=True)
    path.write_text("changed\n", encoding="utf-8")

    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_repository_inventory(
            tmp_path,
            {"evaluation/data/old.py": hashlib.sha256(b"original\n").hexdigest()},
            {"evaluation/data/old.py"},
        )


def test_repository_verifier_accepts_only_explicitly_bound_successor(
    tmp_path: Path,
) -> None:
    path = tmp_path / "evaluation" / "data" / "old.py"
    path.parent.mkdir(parents=True)
    path.write_text("successor\n", encoding="utf-8")
    historical = hashlib.sha256(b"historical\n").hexdigest()
    successor = _sha(path)

    assert verify_repository_inventory(
        tmp_path,
        {"evaluation/data/old.py": historical},
        {"evaluation/data/old.py"},
        {"evaluation/data/old.py": successor},
    ) == []


def test_repository_verifier_rejects_invalid_checksums(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid SHA-256"):
        verify_repository_inventory(tmp_path, {"evaluation/data/a.py": "bad"}, set())


def test_repository_verifier_rejects_unexpected_manifest_entries(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unexpected repository manifest entry"):
        verify_repository_inventory(tmp_path, {"unexpected/file.py": "a" * 64}, set())


def test_evidence_inventory_rejects_unexpected_entries() -> None:
    with pytest.raises(ValueError, match="unexpected"):
        _validate_evidence_inventory(
            {"manifests/known.json": "a" * 64, "manifests/unexpected.json": "b" * 64},
            {"manifests/known.json"},
        )


def test_current_release_verifier_checks_the_bound_inventory(tmp_path: Path) -> None:
    dataset_root = tmp_path / "data"
    repository = tmp_path / "repository"
    release_dir = dataset_root / "manifests" / "phase10h-v1"
    release_dir.mkdir(parents=True)
    tasks = [{"approved_records": 0, "training_status": "BLOCKED"}]
    task_path = repository / "configs" / "datasets" / "phase10h_tasks.json"
    task_path.parent.mkdir(parents=True)
    task_path.write_text(json.dumps({"tasks": tasks}), encoding="utf-8")
    old_code = repository / "evaluation" / "data" / "old.py"
    old_code.parent.mkdir(parents=True)
    old_code.write_text("frozen\n", encoding="utf-8")

    evidence = {}
    for path in _evidence_paths(dataset_root):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")
        evidence[path.relative_to(dataset_root).as_posix()] = _sha(path)
    release = {
        "version": "phase10h-v1",
        "tasks": tasks,
        "decision": "NO-GO",
        "approved_training_records": 0,
        "evidence": evidence,
        "repository": {
            "configs/datasets/phase10h_tasks.json": _sha(task_path),
            "evaluation/data/old.py": _sha(old_code),
        },
    }
    release_path = release_dir / "release.json"
    release_path.write_text(json.dumps(release), encoding="utf-8")

    result = verify_release(
        dataset_root,
        repository,
        expected_release_sha256=_sha(release_path),
        require_d_drive=False,
    )

    assert result["status"] == "VERIFIED"
    assert result["repository_entries_verified"] == 2
    assert result["evidence_entries_verified"] == len(evidence)
