"""Verify the frozen Phase 10H inventory without treating later files as historical."""

import argparse
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from evaluation.data.final_release import VERSION, gate
from evaluation.data.model2 import digest
from evaluation.data.phase10g import SOURCES

SHA256 = re.compile(r"^[0-9a-f]{64}$")
DATASET_CONFIGS = {
    "field_matrix.json",
    "model2_pilot.json",
    "phase10h_tasks.json",
    "registry.json",
}
EXPERIMENT_CONFIGS = {
    "field_coordination.json",
    "phase6_field_command.json",
}


def _repository_path(value: str) -> PurePosixPath:
    if not value or "\\" in value:
        raise ValueError(f"invalid repository inventory path: {value!r}")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"invalid repository inventory path: {value!r}")
    allowed = (
        len(path.parts) == 3
        and path.parts[:2] == ("evaluation", "data")
        and path.suffix == ".py"
    ) or (
        len(path.parts) == 3
        and path.parts[:2] == ("configs", "datasets")
        and path.name in DATASET_CONFIGS
    ) or (
        len(path.parts) == 3
        and path.parts[:2] == ("configs", "scenarios")
        and path.name.endswith("_field.json")
    ) or (
        len(path.parts) == 3
        and path.parts[:2] == ("configs", "experiments")
        and path.name in EXPERIMENT_CONFIGS
    )
    if not allowed:
        raise ValueError(f"unexpected repository manifest entry: {value}")
    return path


def verify_repository_inventory(
    repository_root: Path,
    entries: dict[str, str],
    discovered_paths: set[str] | None = None,
    successor_digests: dict[str, str] | None = None,
) -> list[str]:
    """Verify every recorded path and return, but do not reject, newer files."""
    successor_digests = successor_digests or {}
    unexpected_successors = set(successor_digests) - set(entries)
    if unexpected_successors:
        raise ValueError(f"successor change is not in the Phase 10H inventory: {sorted(unexpected_successors)}")
    verified_successors: set[str] = set()
    for relative, expected in entries.items():
        path = _repository_path(relative)
        if not SHA256.fullmatch(expected):
            raise ValueError(f"invalid SHA-256 for recorded file: {relative}")
        source = repository_root.joinpath(*path.parts)
        if not source.is_file():
            raise FileNotFoundError(f"recorded Phase 10H file is missing: {relative}")
        actual = digest(source)
        if actual == expected:
            continue
        if successor_digests.get(relative) != actual:
            raise ValueError(f"recorded Phase 10H file checksum mismatch: {relative}")
        verified_successors.add(relative)
    if verified_successors != set(successor_digests):
        raise ValueError("successor change list contains files that still match the historical release")
    if discovered_paths is None:
        discovered_paths = _discover_repository_paths(repository_root)
    unexpected = discovered_paths - set(entries)
    return sorted(unexpected)


def _load_successor_changes(
    path: Path,
    root: Path,
    repository_entries: dict[str, str],
) -> list[dict[str, str]]:
    path = path.resolve()
    if not path.is_relative_to(root):
        raise ValueError("successor change record must remain under the D-drive data root")
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, dict) or payload.get(
        "schema_version"
    ) != "phase10i-historical-successors-1.0":
        raise ValueError("invalid historical successor change record")
    changes = payload.get("changes")
    if not isinstance(changes, list):
        raise TypeError("successor change record must contain a change list")
    verified: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in changes:
        if not isinstance(item, dict):
            raise TypeError("invalid successor change entry")
        relative = item.get("repository_path")
        historical = item.get("historical_sha256")
        successor = item.get("successor_sha256")
        reason = item.get("reason")
        if not isinstance(relative, str):
            raise TypeError("successor entries require a repository path")
        if not isinstance(historical, str):
            raise TypeError("successor entries require a historical SHA-256")
        if not isinstance(successor, str):
            raise TypeError("successor entries require a successor SHA-256")
        if not isinstance(reason, str):
            raise TypeError("successor entries require path, hashes, and reason")
        _repository_path(relative)
        if relative in seen:
            raise ValueError(f"duplicate successor change entry: {relative}")
        if repository_entries.get(relative) != historical:
            raise ValueError(f"historical successor reference does not match release: {relative}")
        if not SHA256.fullmatch(historical) or not SHA256.fullmatch(successor):
            raise ValueError(f"invalid successor SHA-256: {relative}")
        if not reason.strip():
            raise ValueError(f"successor change requires a reason: {relative}")
        seen.add(relative)
        verified.append(
            {
                "repository_path": relative,
                "historical_sha256": historical,
                "successor_sha256": successor,
                "reason": reason,
            }
        )
    return verified


def _discover_repository_paths(repository_root: Path) -> set[str]:
    paths = {
        path.relative_to(repository_root).as_posix()
        for path in (repository_root / "evaluation" / "data").glob("*.py")
    }
    dataset_dir = repository_root / "configs" / "datasets"
    paths.update(
        (dataset_dir / name).relative_to(repository_root).as_posix()
        for name in DATASET_CONFIGS
        if (dataset_dir / name).is_file()
    )
    scenario_dir = repository_root / "configs" / "scenarios"
    paths.update(
        path.relative_to(repository_root).as_posix()
        for path in scenario_dir.glob("*_field.json")
    )
    experiment_dir = repository_root / "configs" / "experiments"
    paths.update(
        (experiment_dir / name).relative_to(repository_root).as_posix()
        for name in EXPERIMENT_CONFIGS
        if (experiment_dir / name).is_file()
    )
    return paths


def _evidence_paths(root: Path) -> list[Path]:
    base = root / "manifests"
    payloads = [base / "phase10h-raw-v1" / f"{name}.json" for name in SOURCES]
    payloads += [
        base / "phase10h-native-v1" / "native.json",
        base / "phase10h-public-v1" / "public.json",
        base / "phase10g-v1" / "quality.json",
        base / "phase10g-crisis-decode-v1" / "summary.json",
        base / "phase10g-v1" / "crisis-task-views.jsonl",
        root / "simulation" / "field-v1" / "manifest.json",
        root / "annotations" / "model2" / "phase10g-field-v1" / "manifest.json",
    ]
    return payloads


def _validate_evidence_inventory(entries: dict[str, str], expected_paths: set[str]) -> None:
    if set(entries) != expected_paths:
        missing = sorted(expected_paths - set(entries))
        unexpected = sorted(set(entries) - expected_paths)
        raise ValueError(
            f"Phase 10H evidence inventory differs (missing={missing}, unexpected={unexpected})"
        )


def verify_release(
    root: Path,
    repository_root: Path,
    *,
    expected_release_sha256: str | None = None,
    successor_changes_path: Path | None = None,
    require_d_drive: bool = True,
) -> dict[str, Any]:
    root = root.resolve()
    repository_root = repository_root.resolve()
    if require_d_drive and root.drive.upper() != "D:":
        raise ValueError("D-drive dataset storage required")
    release_path = root / "manifests" / VERSION / "release.json"
    release_sha256 = digest(release_path)
    if expected_release_sha256 is None:
        ledger_path = root / "manifests" / "phase10i-a-raw-v1" / "checksums.json"
        ledger = json.loads(ledger_path.read_bytes())
        expected_release_sha256 = str(ledger["phase10h_release_sha256"])
    if not SHA256.fullmatch(expected_release_sha256) or release_sha256 != expected_release_sha256:
        raise ValueError("frozen Phase 10H release checksum does not match its audit binding")

    release = json.loads(release_path.read_bytes())
    task_path = repository_root / "configs" / "datasets" / "phase10h_tasks.json"
    tasks = json.loads(task_path.read_bytes())["tasks"]
    if release.get("tasks") != tasks:
        raise ValueError("task configuration differs from frozen manifest")
    if (
        release.get("approved_training_records") != 0
        or release.get("version") != VERSION
        or release.get("decision") != gate(release.get("tasks", []))
    ):
        raise ValueError("incorrect frozen audit decision or version")

    evidence_entries = release.get("evidence")
    if not isinstance(evidence_entries, dict):
        raise TypeError("invalid Phase 10H evidence inventory")
    payloads = _evidence_paths(root)
    expected_evidence = {path.relative_to(root).as_posix() for path in payloads}
    _validate_evidence_inventory(evidence_entries, expected_evidence)
    for path in payloads:
        relative = path.relative_to(root).as_posix()
        expected = evidence_entries[relative]
        if not isinstance(expected, str) or not SHA256.fullmatch(expected):
            raise ValueError(f"invalid SHA-256 for evidence: {relative}")
        if digest(path) != expected:
            raise ValueError(f"Phase 10H evidence checksum mismatch: {relative}")

    repository_entries = release.get("repository")
    if not isinstance(repository_entries, dict) or not repository_entries:
        raise ValueError("invalid Phase 10H repository inventory")
    successors = (
        _load_successor_changes(successor_changes_path, root, repository_entries)
        if successor_changes_path is not None
        else []
    )
    successor_digests = {
        item["repository_path"]: item["successor_sha256"] for item in successors
    }
    unrecorded = verify_repository_inventory(
        repository_root,
        repository_entries,
        successor_digests=successor_digests,
    )
    return {
        "status": "VERIFIED_WITH_SUCCESSOR_CHANGES" if successors else "VERIFIED",
        "release_version": VERSION,
        "release_sha256": release_sha256,
        "repository_entries_verified": len(repository_entries),
        "repository_entries_superseded_by_later_phase": successors,
        "evidence_entries_verified": len(evidence_entries),
        "newly_discovered_unrecorded_repository_files": unrecorded,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--successor-changes", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            verify_release(
                args.root,
                args.repository,
                successor_changes_path=args.successor_changes,
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
