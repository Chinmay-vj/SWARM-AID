"""Freeze and verify the Phase 10H audit decision and its versioned evidence."""

import argparse
import json
import shutil
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from evaluation.data.final_native import checked
from evaluation.data.final_raw import inventory
from evaluation.data.model2 import digest, write_json
from evaluation.data.phase10g import SOURCES

VERSION = "phase10h-v1"


def storage(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"files": 0, "bytes": 0, "status": "absent"}
    size = count = 0
    try:
        for _, stat in inventory(path):
            size += stat.st_size
            count += 1
    except PermissionError as exc:
        return {
            "files": count,
            "bytes": size,
            "status": "partial",
            "unreadable_path": str(exc.filename or path),
        }
    return {"files": count, "bytes": size, "status": "complete"}


def gate(tasks: list[dict[str, Any]]) -> str:
    """This audit-only version cannot authorize training through a changed task file."""
    if not tasks or any(
        r["approved_records"] != 0 or r["training_status"] != "BLOCKED" for r in tasks
    ):
        raise ValueError("changed training disposition requires a new reviewed release")
    return "NO-GO"


def freeze(root: Path, verify: bool = False) -> None:
    if root.resolve().drive.upper() != "D:":
        raise ValueError("D-drive dataset storage required")
    base = root / "manifests"
    dest = base / VERSION
    task_file = Path("configs/datasets/phase10h_tasks.json")
    code = sorted(Path("evaluation/data").glob("*.py"))
    configs = [
        task_file,
        Path("configs/datasets/registry.json"),
        Path("configs/datasets/field_matrix.json"),
        Path("configs/datasets/model2_pilot.json"),
        *sorted(Path("configs/scenarios").glob("*_field.json")),
        Path("configs/experiments/field_coordination.json"),
        Path("configs/experiments/phase6_field_command.json"),
    ]
    payloads = [base / "phase10h-raw-v1" / (name + ".json") for name in SOURCES]
    payloads += [
        base / "phase10h-native-v1/native.json",
        base / "phase10h-public-v1/public.json",
        base / "phase10g-v1/quality.json",
        base / "phase10g-crisis-decode-v1/summary.json",
        base / "phase10g-v1/crisis-task-views.jsonl",
        root / "simulation/field-v1/manifest.json",
        root / "annotations/model2/phase10g-field-v1/manifest.json",
    ]
    if verify:
        release = json.loads((dest / "release.json").read_bytes())
        if release["tasks"] != json.loads(task_file.read_bytes())["tasks"]:
            raise ValueError("task configuration differs from frozen manifest")
        if release["approved_training_records"] != 0:
            raise ValueError("audit release cannot authorize training")
        if release["decision"] != gate(release["tasks"]) or release["version"] != VERSION:
            raise ValueError("incorrect release decision or version")
        expected = {p.relative_to(root).as_posix() for p in payloads}
        if set(release["evidence"]) != expected:
            raise ValueError("incomplete evidence manifest")
        for p in payloads:
            checked(p, release["evidence"][p.relative_to(root).as_posix()])
        for p in code + configs:
            checked(p, release["repository"][p.as_posix()])
        return
    if dest.exists():
        raise FileExistsError(dest)
    if shutil.disk_usage(root).free < 20480 << 20:
        raise ValueError("20 GiB storage reserve")
    tasks = json.loads(task_file.read_bytes())["tasks"]
    public = json.loads(payloads[len(SOURCES) + 1].read_bytes())["public"]
    if set(public) != set(SOURCES) or any(
        row["approved_training_records"] for row in public.values()
    ):
        raise ValueError("changed public scope")
    for name in SOURCES:
        raw = json.loads((base / "phase10h-raw-v1" / (name + ".json")).read_bytes())
        if raw["summary_sha256"] != public[name]["summary_sha256"]:
            raise ValueError("audit stages used different source indexes")
    workbook = Path(public["UCI"]["source"]).with_suffix(".xlsx")
    checked(workbook, "c92d102bb35cd4c0b42c0b6a1336c4065ccdca7069f80a6890ee1b7e3124bd5d")
    with zipfile.ZipFile(workbook) as archive:
        if archive.testzip() is not None:
            raise ValueError("workbook CRC mismatch")
    stores = {}
    for label, path in (("external", root), ("repository", Path("datasets"))):
        for sub in (
            "raw",
            "interim",
            "processed",
            "manifests",
            "annotations",
            "simulation",
            "artifacts",
            "splits",
            ".hf_cache",
        ):
            stores[label + "/" + sub] = storage(path / sub)
    with TemporaryDirectory(dir=base) as tmp:
        out = Path(tmp) / VERSION
        out.mkdir()
        write_json(
            out / "release.json",
            {
                "version": VERSION,
                "schema_version": "1.0",
                "taxonomy": "source-specific; native 1.0",
                "purpose": "private dataset audit",
                "created_utc": datetime.now(UTC).isoformat(),
                "git": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                "dirty": bool(subprocess.check_output(["git", "status", "--porcelain"])),
                "tasks": tasks,
                "decision": gate(tasks),
                "approved_training_records": 0,
                "evidence": {p.relative_to(root).as_posix(): digest(p) for p in payloads},
                "repository": {p.as_posix(): digest(p) for p in code + configs},
                "storage": stores,
                "disk": shutil.disk_usage(root)._asdict(),
                "workbook_sha256": digest(workbook),
                "workbook_crc": "pass",
            },
        )
        out.rename(dest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    freeze(args.root, args.verify)
