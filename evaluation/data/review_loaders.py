"""Offline preview loaders. Consumers receive operational fields only."""

import csv
import importlib
import json
from collections.abc import Iterator
from functools import partial
from itertools import groupby
from pathlib import Path
from typing import Any

from evaluation.data.contracts import relative_path
from evaluation.data.model2 import digest
from evaluation.data.model2_collect import LocalReport
from evaluation.data.model2_records import Features
from evaluation.data.preprocessing import audio, batches, image, normalized_text


def asset(root: Path, name: str) -> Path:
    path = (root / relative_path(name)).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("reference escapes release")
    return path


def paired(
    root: Path, rgb: str, thermal: str, pair_id: str, synchronization_ref: str
) -> dict[str, Any]:
    if not pair_id or not synchronization_ref:
        raise ValueError("missing authoritative pair metadata")
    return {
        "image": image(asset(root, rgb)),
        "thermal": image(asset(root, thermal)),
        "pair_id": pair_id,
        "synchronization_ref": synchronization_ref,
    }


def public_batches(
    folder: Path, size: int = 1, rate: int = 16000
) -> Iterator[list[dict[str, Any]]]:
    meta = json.loads((folder / "summary.json").read_bytes())
    root = Path(meta["configuration"]["source"])
    index = folder / "index.jsonl"
    if digest(index) != meta["outputs"]["index.jsonl"]:
        raise ValueError("changed review index")
    name = meta["dataset"]
    visual_flags = folder.parents[2] / "manifests" / "phase10g-visual-v1" / name
    excluded: set[str] = set()
    if visual_flags.is_dir():
        visual_meta = json.loads((visual_flags / "summary.json").read_bytes())
        flagfile = visual_flags / "flags.jsonl"
        if (
            visual_meta["index_sha256"] != meta["outputs"]["index.jsonl"]
            or digest(flagfile) != visual_meta["flags_sha256"]
        ):
            raise ValueError("incompatible full-decode audit")
        with flagfile.open(encoding="utf8") as flags:
            excluded.update(json.loads(line)["path"] for line in flags)
    source_hashes = {Path(k).as_posix(): v for k, v in meta["source_digests"].items()}

    def load_rows() -> Iterator[dict[str, Any]]:
        with index.open(encoding="utf8") as src:
            if name in {"CrisisMMD", "HumAID"}:
                for source, group in groupby(map(json.loads, src), key=lambda r: r["source"]):
                    path = asset(root, source)
                    if digest(path) != source_hashes[source]:
                        raise ValueError("changed text source")
                    if name == "CrisisMMD":
                        with path.open(encoding="utf-8-sig", newline="") as stream:
                            table = enumerate(
                                csv.DictReader(stream, delimiter="\t", quoting=csv.QUOTE_NONE), 2
                            )
                            for record in group:
                                text = next(
                                    r["tweet_text"] for n, r in table if n == record["line"]
                                )
                                yield {
                                    "text": normalized_text(text),
                                    "image": image(asset(root, record["path"])),
                                    "labels": record["labels"],
                                }
                    else:
                        with importlib.import_module("duckdb").connect(":memory:") as db:
                            cursor = db.execute(
                                "select tweet_text from read_parquet(?)", [str(path)]
                            )
                            texts = enumerate(
                                (
                                    v[0]
                                    for chunk in iter(partial(cursor.fetchmany, 256), [])
                                    for v in chunk
                                ),
                                1,
                            )
                            for record in group:
                                text = next(value for n, value in texts if n == record["line"])
                                yield {"text": normalized_text(text), "label": record["label"]}
                return
            for line in src:
                row = json.loads(line)
                if row.get("path") in excluded:
                    continue
                if row.get("sha256") and digest(asset(root, row["path"])) != row["sha256"]:
                    raise ValueError("source media changed")
                if name in {"Smoke", "UCI", "USGS"}:
                    yield {"measurements": row["measurements"], "timestamp": row["timestamp"]}
                elif name == "ESC-50":
                    yield {
                        "audio": audio(asset(root, row["path"]), rate),
                        "label": row["label"],
                        "fold": row["fold"],
                    }
                elif row.get("task") != "unpaired_mask":
                    modality = row.get("modality", "image")
                    sample = {modality: image(asset(root, row["path"])), "available": [modality]}
                    for key in ("annotations", "categories", "label"):
                        if key in row:
                            sample[key] = row[key]
                    if "mask" in row:
                        sample["mask"] = image(asset(root, row["mask"]))
                    yield sample

    yield from batches(load_rows(), size)


def native_batches(batch: Path, kind: str, size: int = 1) -> Iterator[list[dict[str, Any]]]:
    meta = json.loads((batch / "release.json").read_bytes())
    if kind not in {"model1", "model2"}:
        raise ValueError("unknown consumer")
    if any(ep["plan"]["seed"] in range(42, 47) for ep in meta["episodes"]):
        raise ValueError("development loader requires a release without protected episodes")
    sources = (
        ["features.jsonl"] if kind == "model2" else [ep["model1_file"] for ep in meta["episodes"]]
    )

    def rows() -> Iterator[dict[str, Any]]:
        for name in sources:
            path = asset(batch, name)
            if digest(path) != meta["files"][name]:
                raise ValueError("checksum mismatch")
            with path.open(encoding="utf8") as stream:
                for line in stream:
                    if kind == "model2":
                        yield Features.model_validate_json(line).model_dump(mode="json")
                    else:
                        record = LocalReport.model_validate_json(line)
                        yield {
                            "readings": [r.model_dump(mode="json") for r in record.readings],
                            "report": record.report.model_dump(mode="json"),
                        }

    yield from batches(rows(), size)
