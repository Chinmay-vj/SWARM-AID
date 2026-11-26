import hashlib
import json
from pathlib import Path

import pytest

from evaluation.data.phase10i_handoff import build_handoff_packet


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_handoff_packet_preserves_queue_and_leaves_decisions_blank(tmp_path: Path) -> None:
    candidate_root = tmp_path / "candidate"
    data_root = tmp_path / "data"
    output_root = tmp_path / "output"
    repository_root = tmp_path / "repository"
    source_root = data_root / "raw" / "heridal"
    source_file = source_root / "image.jpg"
    source_file.parent.mkdir(parents=True)
    source_file.write_bytes(b"synthetic-image-bytes")
    source_sha256 = hashlib.sha256(source_file.read_bytes()).hexdigest()

    phase10g = data_root / "processed" / "phase10g-v1" / "HERIDAL"
    _write_json(
        phase10g / "summary.json",
        {"configuration": {"source": str(source_root)}},
    )
    index = {
        "path": "image.jpg",
        "split": "train",
        "sha256": source_sha256,
        "annotations": [],
    }
    (phase10g / "index.jsonl").write_text(json.dumps(index) + "\n", encoding="utf-8")

    queue = [
        {
            "review_id": f"review-{number:03}",
            "dataset": "HERIDAL",
            "source_path": "image.jpg",
            "review_task": "determine empty annotation meaning",
            "split": "train",
            "decision": None,
            "review_status": "pending",
        }
        for number in range(152)
    ]
    queue_bytes = "".join(json.dumps(item) + "\n" for item in queue).encode()
    candidate_root.mkdir(parents=True)
    (candidate_root / "human_review_queue.jsonl").write_bytes(queue_bytes)
    _write_json(
        candidate_root / "model1_candidate_readiness.json",
        {
            "tasks": [
                {
                    "task": "RGB person detection",
                    "sources": ["HERIDAL", "SARD"],
                    "status": "BLOCKED",
                    "candidate_artifact": False,
                    "blockers": ["source group identifiers pending"],
                    "blocker_categories": ["BLOCKED_METADATA"],
                }
            ]
        },
    )
    training_partition = repository_root / "evaluation" / "data" / "training_partition.py"
    training_partition.parent.mkdir(parents=True)
    training_partition.write_text("successor\n", encoding="utf-8")
    historical_digest = hashlib.sha256(b"historical\n").hexdigest()
    release_path = data_root / "manifests" / "phase10h-v1" / "release.json"
    _write_json(
        release_path,
        {"repository": {"evaluation/data/training_partition.py": historical_digest}},
    )
    _write_json(
        data_root / "manifests" / "phase10i-a-raw-v1" / "checksums.json",
        {
            "phase10h_release_sha256": hashlib.sha256(
                release_path.read_bytes()
            ).hexdigest()
        },
    )
    checksums = {}
    for name in ("human_review_queue.jsonl", "model1_candidate_readiness.json"):
        checksums[name] = hashlib.sha256((candidate_root / name).read_bytes()).hexdigest()
    _write_json(candidate_root / "checksums.json", checksums)

    summary = build_handoff_packet(
        candidate_root, data_root, output_root, repository_root
    )

    assert summary["verified_candidate_files"] == 2
    assert summary["review_items"] == 152
    assert summary["task_count"] == 1
    packet = [
        json.loads(line)
        for line in (output_root / "human_review_packet.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [item["review_id"] for item in packet] == [
        item["review_id"] for item in queue
    ]
    assert all(item["human_decision"] is None for item in packet)
    assert all(
        slot["decision"] is None
        for item in packet
        for slot in item["review_slots"]
    )
    assert all(item["source_evidence"]["current_sha256"] == source_sha256 for item in packet)
    release = json.loads((output_root / "training_release_status.json").read_bytes())
    assert release["training_approved"] is False
    assert release["approved_training_records"] == 0
    assert release["human_annotation_decisions"] == 0
    assert release["phase11_started"] is False
    successor = json.loads(
        (output_root / "phase10h_successor_changes.json").read_bytes()
    )
    assert successor["changes"][0]["historical_sha256"] == historical_digest
    assert successor["changes"][0]["repository_path"] == (
        "evaluation/data/training_partition.py"
    )
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        build_handoff_packet(candidate_root, data_root, output_root, repository_root)
