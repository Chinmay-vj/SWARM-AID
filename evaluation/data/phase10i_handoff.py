"""Create a D-drive-only Phase 10I human-review and authorization packet."""

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from evaluation.data.release_authorization import (
    AuthorizationBundle,
    TaskReadiness,
    TaskReadinessReport,
)

DEFAULT_CANDIDATE_ROOT = Path(
    r"D:\SWARM-AID-DATA\manifests\phase10i-b1-c1-v1"
)
DEFAULT_OUTPUT_ROOT = Path(
    r"D:\SWARM-AID-DATA\manifests\phase10i-d1-e1-v2"
)
SOURCE_IDS = {
    "HERIDAL": "heridal",
    "SARD": "sard",
    "FLAME": "flame",
    "FloodNet": "floodnet",
    "RescueNet": "rescuenet",
    "WiSARD": "wisard",
    "ESC-50": "esc50",
    "Smoke": "smoke-detection-iot",
    "UCI": "uci-air-quality",
    "USGS": "usgs-water-data",
    "native Model 1": "native-model1",
}
CANDIDATE_FILES = {
    "FLAME": "flame-fire-classification-v1.json",
    "ESC-50": "esc50-official-folds-v1.json",
    "UCI": "uci-co-next-hour-24h-v1.json",
}
DECISIONS = (
    "ACCEPT",
    "REJECT",
    "CORRECTION_REQUIRED",
    "INSUFFICIENT_EVIDENCE",
    "DEFERRED",
)


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_bytes())


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _relative_file(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe relative artifact path: {relative}")
    resolved_root = root.resolve()
    resolved = (resolved_root / path).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError(f"artifact escapes its root: {relative}")
    return resolved


def verify_candidate_artifacts(candidate_root: Path) -> dict[str, str]:
    checksums_path = candidate_root / "checksums.json"
    expected = _read_json(checksums_path)
    if not isinstance(expected, dict) or not expected:
        raise ValueError("candidate checksum manifest is empty or invalid")
    verified: dict[str, str] = {}
    for relative, expected_digest in sorted(expected.items()):
        if not isinstance(relative, str) or not isinstance(expected_digest, str):
            raise TypeError("candidate checksum manifest contains invalid entries")
        artifact = _relative_file(candidate_root, relative)
        if not artifact.is_file():
            raise FileNotFoundError(f"candidate artifact is missing: {relative}")
        actual = _sha256(artifact)
        if actual != expected_digest:
            raise ValueError(f"candidate artifact checksum mismatch: {relative}")
        verified[relative] = actual
    return verified


def _indexed_row(
    data_root: Path,
    dataset: str,
    source_path: str,
    index_cache: dict[str, dict[str, dict[str, Any]]],
    source_root_cache: dict[str, Path],
) -> tuple[Path, dict[str, Any]]:
    folder = data_root / "processed" / "phase10g-v1" / dataset
    if dataset not in source_root_cache:
        summary = _read_json(folder / "summary.json")
        source_root_cache[dataset] = Path(summary["configuration"]["source"]).resolve()
    source_root = source_root_cache[dataset]
    indexed_path = Path(source_path)
    if indexed_path.is_absolute() or any(
        part in {"", ".", ".."} for part in indexed_path.parts
    ):
        raise ValueError(f"unsafe review source path: {source_path}")
    source_file = (source_root / indexed_path).resolve()
    if not source_file.is_relative_to(source_root) or not source_file.is_file():
        raise FileNotFoundError(f"review source is missing: {source_file}")
    if dataset not in index_cache:
        rows: dict[str, dict[str, Any]] = {}
        for line in (folder / "index.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            for key in ("path", "mask"):
                indexed_path = row.get(key)
                if isinstance(indexed_path, str):
                    rows[indexed_path] = row
        index_cache[dataset] = rows
    try:
        return source_file, index_cache[dataset][source_path]
    except KeyError as error:
        raise ValueError(
            f"review source is absent from the Phase 10G index: {source_path}"
        ) from error


def _review_packet(
    candidate_root: Path,
    data_root: Path,
    verified_inputs: dict[str, str],
) -> list[dict[str, Any]]:
    queue_path = candidate_root / "human_review_queue.jsonl"
    queue_digest = verified_inputs.get("human_review_queue.jsonl")
    if queue_digest is None:
        raise ValueError("the candidate checksum manifest does not bind the review queue")
    cache: dict[Path, str] = {}
    index_cache: dict[str, dict[str, dict[str, Any]]] = {}
    source_root_cache: dict[str, Path] = {}
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in queue_path.read_text(encoding="utf-8").splitlines():
        original = json.loads(line)
        review_id = original.get("review_id")
        if not isinstance(review_id, str) or review_id in seen:
            raise ValueError("review queue contains a missing or duplicate review ID")
        if original.get("decision") is not None or original.get("review_status") != "pending":
            raise ValueError("review queue contains a pre-existing human decision")
        seen.add(review_id)
        source_file, indexed = _indexed_row(
            data_root,
            str(original["dataset"]),
            str(original["source_path"]),
            index_cache,
            source_root_cache,
        )
        current_digest = cache.get(source_file)
        if current_digest is None:
            current_digest = _sha256(source_file)
            cache[source_file] = current_digest
        index_digest = indexed.get("sha256") if indexed.get("path") == original["source_path"] else None
        if index_digest is not None and current_digest != index_digest:
            raise ValueError(f"review source no longer matches its Phase 10G index: {review_id}")
        review_slots: list[dict[str, Any]] = [
            {
                "slot": f"independent_reviewer_{slot}",
                "reviewer_identity": None,
                "decision": None,
                "decision_rationale": None,
                "reviewed_at": None,
                "evidence_refs": [],
            }
            for slot in (1, 2)
        ]
        records.append(
            {
                **original,
                "decision_options": list(DECISIONS),
                "review_status": "pending",
                "review_slots": review_slots,
                "source_evidence": {
                    "resolved_path": str(source_file),
                    "current_sha256": current_digest,
                    "index_sha256": index_digest,
                    "phase10g_index_reference": (
                        "path" if indexed.get("path") == original["source_path"] else "mask"
                    ),
                    "split_from_index": indexed.get("split"),
                    "index_record_had_sha256": index_digest is not None,
                },
                "deterministic_review_status": "SOURCE_AND_INDEX_VERIFIED",
                "human_decision": None,
            }
        )
    if len(records) != 152:
        raise ValueError(f"expected the existing 152-item queue, found {len(records)}")
    return records


def _task_readiness(
    candidate_root: Path,
    verified_inputs: dict[str, str],
) -> TaskReadinessReport:
    source_path = candidate_root / "model1_candidate_readiness.json"
    readiness = _read_json(source_path)
    tasks: list[TaskReadiness] = []
    for item in readiness["tasks"]:
        source_names = tuple(str(source) for source in item["sources"])
        if not source_names or any(source not in SOURCE_IDS for source in source_names):
            raise ValueError(f"unknown source in readiness task: {item['task']}")
        task_id = re.sub(r"[^a-z0-9]+", "-", item["task"].lower()).strip("-")
        if item["status"] != "BLOCKED":
            raise ValueError(
                f"candidate readiness changed; review task before classifying: {item['task']}"
            )
        candidate_sha256 = None
        if item["candidate_artifact"] and source_names[0] in CANDIDATE_FILES:
            relative = f"candidate_manifests/{CANDIDATE_FILES[source_names[0]]}"
            candidate_sha256 = verified_inputs.get(relative)
            if candidate_sha256 is None:
                raise ValueError(f"candidate descriptor is not checksum-bound: {relative}")
        tasks.append(
            TaskReadiness(
                schema_version="phase10i-task-readiness-1.0",
                task_id=task_id,
                dataset_id=SOURCE_IDS[source_names[0]],
                source_dataset_ids=tuple(SOURCE_IDS[source] for source in source_names),
                status="BLOCKED",
                blockers=tuple(str(blocker) for blocker in item["blockers"]),
                blocker_categories=tuple(
                    str(category) for category in item["blocker_categories"]
                ),
                candidate_manifest_sha256=candidate_sha256,
                approved_training_records=0,
            )
        )
    return TaskReadinessReport(
        schema_version="phase10i-task-readiness-report-1.0",
        tasks=tuple(tasks),
    )


def _historical_successor_changes(
    data_root: Path,
    repository_root: Path,
) -> tuple[dict[str, Any], str]:
    release_path = data_root / "manifests" / "phase10h-v1" / "release.json"
    ledger_path = data_root / "manifests" / "phase10i-a-raw-v1" / "checksums.json"
    release_sha256 = _sha256(release_path)
    ledger = _read_json(ledger_path)
    if ledger.get("phase10h_release_sha256") != release_sha256:
        raise ValueError("frozen Phase 10H release does not match the Phase 10I-A binding")
    release = _read_json(release_path)
    repository_entries = release.get("repository")
    relative = "evaluation/data/training_partition.py"
    if not isinstance(repository_entries, dict) or relative not in repository_entries:
        raise ValueError("Phase 10H release does not bind training_partition.py")
    historical_sha256 = repository_entries[relative]
    current_sha256 = _sha256(repository_root.joinpath(*Path(relative).parts))
    changes = []
    if current_sha256 != historical_sha256:
        changes.append(
            {
                "repository_path": relative,
                "historical_sha256": historical_sha256,
                "successor_sha256": current_sha256,
                "reason": (
                    "Phase 10I-D1/E1 adds checksum-bound human authorization to the "
                    "training loader. The Phase 10H release manifest and its historical "
                    "file checksum are preserved; this successor is separately recorded."
                ),
            }
        )
    return {
        "schema_version": "phase10i-historical-successors-1.0",
        "historical_release_sha256": release_sha256,
        "changes": changes,
    }, release_sha256


def build_handoff_packet(
    candidate_root: Path,
    data_root: Path,
    output_root: Path,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    verified_inputs = verify_candidate_artifacts(candidate_root)
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite an existing handoff packet: {output_root}")
    repository_root = repository_root or Path(__file__).resolve().parents[2]
    review_records = _review_packet(candidate_root, data_root, verified_inputs)
    readiness = _task_readiness(candidate_root, verified_inputs)
    historical_changes, historical_release_sha256 = _historical_successor_changes(
        data_root, repository_root
    )
    output_root.mkdir(parents=True)
    queue_path = output_root / "human_review_packet.jsonl"
    with queue_path.open("x", encoding="utf-8", newline="\n") as stream:
        for record in review_records:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    readiness_path = output_root / "task_readiness.json"
    _write_json(readiness_path, readiness.model_dump(mode="json"))
    authorization_path = output_root / "authorization_bundle.json"
    _write_json(
        authorization_path,
        AuthorizationBundle(
            schema_version="phase10i-authorization-bundle-1.0",
            records=(),
        ).model_dump(mode="json"),
    )
    historical_changes_path = output_root / "phase10h_successor_changes.json"
    _write_json(historical_changes_path, historical_changes)
    release_status_path = output_root / "training_release_status.json"
    _write_json(
        release_status_path,
        {
            "schema_version": "phase10i-training-release-status-1.0",
            "artifact_kind": "candidate_only_not_approved_training_release",
            "status": "NO_GO",
            "training_approved": False,
            "approved_training_records": 0,
            "candidate_artifacts_only": True,
            "human_annotation_decisions": 0,
            "owner_authorizations": 0,
            "model_training_performed": False,
            "phase11_started": False,
            "task_count": len(readiness.tasks),
            "blocked_task_count": sum(task.status == "BLOCKED" for task in readiness.tasks),
            "historical_phase10h_release_sha256": historical_release_sha256,
            "candidate_input_checksums": verified_inputs,
            "review_queue_sha256": verified_inputs["human_review_queue.jsonl"],
        },
    )
    output_hashes = {
        path.name: _sha256(path)
        for path in (
            queue_path,
            readiness_path,
            authorization_path,
            historical_changes_path,
            release_status_path,
        )
    }
    _write_json(output_root / "checksums.json", output_hashes)
    return {
        "output_root": str(output_root),
        "verified_candidate_files": len(verified_inputs),
        "review_items": len(review_records),
        "task_count": len(readiness.tasks),
        "blocked_tasks": sum(task.status == "BLOCKED" for task in readiness.tasks),
        "human_decisions": 0,
        "authorizations": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-root", type=Path, default=DEFAULT_CANDIDATE_ROOT)
    parser.add_argument("--data-root", type=Path, default=Path(r"D:\SWARM-AID-DATA"))
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    roots = (args.candidate_root, args.data_root, args.output_root)
    if any(path.resolve().drive.upper() != "D:" for path in roots):
        raise ValueError("Phase 10I handoff artifacts, data, and caches must remain on D:")
    result = build_handoff_packet(args.candidate_root, args.data_root, args.output_root)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
