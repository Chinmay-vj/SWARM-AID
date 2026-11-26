"""Inspect public staging and export versioned review indexes, one source at a time."""

import argparse
import hashlib
import json
import shutil
import subprocess
import time
from collections import Counter, defaultdict
from collections.abc import Iterator
from datetime import UTC, datetime
from itertools import groupby
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from evaluation.data.contracts import Registry
from evaluation.data.model2 import digest
from evaluation.data.preprocessing import sensor_rows
from evaluation.data.public_preprocessing import context, esc, files, visual

SOURCES = {
    "HERIDAL": "rgb/HERIDAL",
    "SARD": "rgb/Sard",
    "FloodNet": "rgb/FloodNet",
    "RescueNet": "rgb/RescueNet",
    "FLAME": "rgb/FLAME",
    "WiSARD": "Multimodal/WiSARDv1",
    "ESC-50": "audio/ESC-50-master",
    "HumAID": "model2/HumAID",
    "CrisisMMD": "multimodal/CrisisMMD",
    "Smoke": "sensors/smoke_detection_iot.csv",
    "UCI": "sensors/AirQualityUCI.csv",
    "USGS": "sensors/USGSWater.csv",
}


def records(name: str, root: Path, pilot: int) -> Iterator[dict[str, Any]]:
    if name in {"UCI", "Smoke", "USGS"}:
        for line, values in groupby(sensor_rows(root), key=lambda r: r["line"]):
            fields = list(values)
            first = fields[0]
            yield {
                "source": root.name,
                "line": line,
                "timestamp": first["timestamp"],
                "group": first["device"] or first["sequence"],
                "period_end": first["period_end"],
                "parameter": first["parameter"],
                "quality": first["quality"],
                "label": first["alarm"],
                "missing": sum(r["missing"] for r in fields),
                "measurements": {
                    r["measurement"]: [
                        r["original"],
                        r["unit"],
                        r["standardized"],
                        r["standard_unit"],
                        r["missing"],
                    ]
                    for r in fields
                },
            }
    elif name == "ESC-50":
        yield from esc(root)
    elif name in {"HumAID", "CrisisMMD"}:
        yield from context(root, name)
    else:
        yield from visual(root, name, pilot)


def process(name: str, source: Path, out: Path, pilot: int, limit: int, reserve: int) -> None:
    start = time.perf_counter()
    folder = out / name
    fingerprint = hashlib.sha256()
    size = count = 0
    evidence = {}
    for p in files(source) if source.is_dir() else [source]:
        stat = p.stat()
        fingerprint.update(
            json.dumps([p.relative_to(source).as_posix(), stat.st_size, stat.st_mtime_ns]).encode()
        )
        size += stat.st_size
        count += 1
        if (
            p.suffix.lower() in {".parquet", ".csv", ".json", ".tsv", ".zip", ".7z"}
            or "license" in p.name.lower()
        ):
            evidence[str(p.relative_to(source.parent if source.is_file() else source))] = digest(p)
    code = {
        p.name: digest(p)
        for p in (
            Path(__file__),
            Path(__file__).with_name("public_preprocessing.py"),
            Path(__file__).with_name("preprocessing.py"),
        )
    }
    config = {
        "source": str(source),
        "inventory_sha256": fingerprint.hexdigest(),
        "code": code,
        "pilot": pilot,
    }
    if folder.exists():
        meta = json.loads((folder / "summary.json").read_bytes())
        if meta["configuration"] != config or any(
            digest(folder / k) != v for k, v in meta["outputs"].items()
        ):
            raise ValueError("published source or configuration changed; select a new version")
        return
    used = sum(p.stat().st_size for p in out.glob("*/*") if p.is_file())
    if shutil.disk_usage(out).free < reserve or used >= limit:
        raise ValueError("storage limit")
    stats: Counter[str] = Counter()
    columns: dict[str, Counter[str]] = defaultdict(Counter)
    seen: dict[str, set[str]] = defaultdict(set)
    folds: dict[str, set[str]] = defaultdict(set)
    perceptual: set[str] = set()
    with TemporaryDirectory(dir=out) as tmp:
        stage = Path(tmp) / name
        stage.mkdir()
        with (
            (stage / "index.jsonl").open("xb") as valid,
            (stage / "quarantine.jsonl").open("xb") as invalid,
        ):
            for row in records(name, source, pilot):
                data = (json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
                used += len(data)
                if (
                    used > limit
                    or stats["rows"] % 128 == 0
                    and shutil.disk_usage(out).free < reserve + len(data)
                ):
                    raise ValueError("storage limit")
                stats["rows"] += 1
                if row.get("error"):
                    invalid.write(data)
                    stats["invalid"] += 1
                    continue
                valid.write(data)
                stats["valid"] += 1
                for k in (
                    "label",
                    "split",
                    "mode",
                    "fold",
                    "task",
                    "modality",
                    "rate",
                    "channels",
                    "duration",
                    "mask_mode",
                ):
                    if row.get(k) is not None:
                        columns[k][str(row[k])] += 1
                key = row.get("sha256") or row.get("text_key")
                if key:
                    stats["exact_repeats"] += key in seen
                    seen[key].add(str(row.get("split") or row.get("fold") or "unassigned"))
                if row.get("fold"):
                    folds[str(row["group"])].add(str(row["fold"]))
                if "annotations" in row:
                    stats["empty_boxes"] += not row["annotations"]
                    stats["boxes"] += len(row["annotations"])
                if row.get("dhash"):
                    stats["decoded_pilot"] += 1
                    stats["pilot_perceptual_hash_collisions"] += row["dhash"] in perceptual
                    perceptual.add(row["dhash"])
                stats["missing_measurements"] += row.get("missing", 0)
        stats["cross_split_exact_keys"] = sum(len(v) > 1 for v in seen.values())
        stats["cross_fold_recordings"] = sum(len(v) > 1 for v in folds.values())
        meta = {
            "dataset": name,
            "version": out.name,
            "schema_version": "1.0",
            "approval": "pending",
            "approved": 0,
            "raw_files": count,
            "raw_bytes": size,
            "counts": stats,
            "distributions": columns,
            "configuration": config,
            "source_digests": evidence,
            "outputs": {p.name: digest(p) for p in stage.iterdir()},
            "seconds": round(time.perf_counter() - start, 2),
            "created": datetime.now(UTC).isoformat(),
            "git": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        }
        (stage / "summary.json").write_text(json.dumps(meta, indent=2), encoding="utf8")
        stage.rename(folder)
    print(name, dict(stats), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--staging", type=Path, default=Path("datasets/raw"))
    parser.add_argument("--version", default="phase10g-v1")
    parser.add_argument("--source", choices=SOURCES, action="append")
    parser.add_argument("--pilot", type=int, default=3)
    parser.add_argument("--limit-mib", type=int, default=1024)
    parser.add_argument("--reserve-mib", type=int, default=20480)
    args = parser.parse_args()
    from evaluation.data.contracts import relative_path

    if (
        args.root.resolve().drive.upper() != "D:"
        or args.staging.resolve().drive.upper() != "D:"
        or "/" in relative_path(args.version)
        or args.pilot < 0
        or min(args.limit_mib, args.reserve_mib) <= 0
    ):
        parser.error("invalid D-drive storage configuration")
    Registry.model_validate_json(Path("configs/datasets/registry.json").read_bytes())
    out = args.root.resolve() / "processed" / args.version
    out.mkdir(parents=True, exist_ok=True)
    print("Capacity", shutil.disk_usage(out), flush=True)
    for name in args.source or SOURCES:
        rel = SOURCES[name]
        options = [args.root / "raw" / rel, args.staging / rel]
        source = next((p.resolve() for p in options if p.exists()), None)
        if source is None:
            print(name, "missing")
            continue
        process(name, source, out, args.pilot, args.limit_mib << 20, args.reserve_mib << 20)


if __name__ == "__main__":
    main()
