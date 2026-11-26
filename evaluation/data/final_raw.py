"""Read-only comparison of the acquired sources with the Phase 10G inventory and digests."""

import argparse
import hashlib
import json
import os
import shutil
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from itertools import islice
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from evaluation.data.model2 import digest, write_json
from evaluation.data.phase10g import SOURCES
from evaluation.data.phase10g_quality import rows


def inventory(root: Path) -> Iterator[tuple[str, os.stat_result]]:
    def visit(folder: Path) -> Iterator[tuple[str, os.stat_result]]:
        with os.scandir(folder) as scan:
            entries = sorted(scan, key=lambda entry: entry.name)
        for entry in entries:
            if entry.is_file():
                yield Path(entry.path).relative_to(root).as_posix(), entry.stat()
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                yield from visit(Path(entry.path))

    if root.is_file():
        yield ".", root.stat()
    else:
        yield from visit(root)


def verify(name: str, root: Path) -> dict[str, Any]:
    folder = root / "processed/phase10g-v1" / name
    meta = json.loads((folder / "summary.json").read_bytes())
    raw = Path(meta["configuration"]["source"])
    index = folder / "index.jsonl"
    if digest(index) != meta["outputs"]["index.jsonl"]:
        raise ValueError(f"{name} changed index")
    keys = {Path(k).as_posix(): h for k, h in meta["source_digests"].items()}
    for row in rows(index):
        if row.get("sha256"):
            keys[row["path"]] = row["sha256"]
    fp = hashlib.sha256()
    count = size = 0
    for ref, stat in inventory(raw):
        count += 1
        size += stat.st_size
        fp.update(json.dumps([ref, stat.st_size, stat.st_mtime_ns]).encode())
    if fp.hexdigest() != meta["configuration"]["inventory_sha256"]:
        raise ValueError(f"{name} changed raw inventory")
    source = raw.parent if raw.is_file() else raw

    def compare(item: tuple[str, str]) -> None:
        ref, expected = item
        with (source / ref).open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                raise ValueError(f"{name} raw content mismatch")

    with ThreadPoolExecutor(4) as pool:
        items = iter(keys.items())
        while batch := list(islice(items, 128)):
            list(pool.map(compare, batch))
    return {
        "files": count,
        "bytes": size,
        "raw_checksum_matches": len(keys),
        "inventory_sha256": fp.hexdigest(),
        "summary_sha256": digest(folder / "summary.json"),
    }


def run(root: Path) -> None:
    if root.resolve().drive.upper() != "D:" or shutil.disk_usage(root).free < 20480 << 20:
        raise ValueError("D-drive release with 20 GiB reserve required")
    dest = root / "manifests/phase10h-raw-v1"
    if dest.exists():
        raise FileExistsError(dest)
    with TemporaryDirectory(dir=dest.parent) as tmp:
        out = Path(tmp) / dest.name
        out.mkdir()
        for name in SOURCES:
            write_json(out / (name + ".json"), verify(name, root))
            print(name, "verified", flush=True)
        out.rename(dest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    run(parser.parse_args().root)
