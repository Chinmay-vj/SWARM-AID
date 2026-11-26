import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from evaluation.data.final_native import checked
from evaluation.data.final_raw import verify
from evaluation.data.final_release import freeze, gate, storage
from evaluation.data.model2 import digest
from evaluation.data.phase10g import process


def test_audit_gate_refuses_task_promotion() -> None:
    assert gate([{"approved_records": 0, "training_status": "BLOCKED"}]) == "NO-GO"
    for tasks in (
        [],
        [{"approved_records": 1, "training_status": "BLOCKED"}],
        [{"approved_records": 0, "training_status": "READY"}],
    ):
        with pytest.raises(ValueError):
            gate(tasks)


def test_raw_digest_catches_content_change_with_same_inventory(tmp_path: Path) -> None:
    raw = tmp_path / "AirQualityUCI.csv"
    raw.write_text("Date;Time;T;\n10/03/2004;18.00.00;2;\n")
    base = tmp_path / "processed/phase10g-v1"
    base.mkdir(parents=True)
    process("UCI", raw, base, 1, 1 << 20, 1)
    assert verify("UCI", tmp_path)["raw_checksum_matches"] == 1
    st = raw.stat()
    raw.write_bytes(raw.read_bytes().replace(b";2;", b";3;"))
    os.utime(raw, ns=(st.st_atime_ns, st.st_mtime_ns))
    with pytest.raises(ValueError, match="content mismatch"):
        verify("UCI", tmp_path)


def test_audit_version_and_evidence_tampering(tmp_path: Path) -> None:
    payload = tmp_path / "release.json"
    payload.write_text("{}")
    stamp = digest(payload)
    payload.write_text('{"approved_training_records":1}')
    with pytest.raises(ValueError, match="checksum"):
        checked(payload, stamp)
    folder = tmp_path / "manifests/phase10h-v1"
    folder.mkdir(parents=True)
    if tmp_path.drive.upper() == "D:":
        with pytest.raises(FileExistsError):
            freeze(tmp_path)
    else:
        with pytest.raises(ValueError, match="D-drive"):
            freeze(tmp_path)


def test_task_matrix_unique_and_closed() -> None:
    plan = json.loads(Path("configs/datasets/phase10h_tasks.json").read_bytes())
    tasks = plan["tasks"]
    assert len({(r["model"], r["task"]) for r in tasks}) == len(tasks)
    assert {r["model"] for r in tasks} == {"1", "2"}
    assert gate(tasks) == "NO-GO"


def test_storage_audit_reports_access_restrictions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def inaccessible(path: Path) -> Iterator[tuple[str, os.stat_result]]:
        yield from ()
        raise PermissionError(13, "access denied", str(path))

    monkeypatch.setattr("evaluation.data.final_release.inventory", inaccessible)
    assert storage(tmp_path) == {
        "files": 0,
        "bytes": 0,
        "status": "partial",
        "unreadable_path": str(tmp_path),
    }
