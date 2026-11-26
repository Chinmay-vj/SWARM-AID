"""Bounded CPU integrity pass over frozen visual indexes. Raw pixels stay in memory."""

import argparse
import importlib
import json
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from evaluation.data.model2 import digest, write_json
from evaluation.data.phase10g_quality import rows
from evaluation.data.preprocessing import batches
from evaluation.data.review_loaders import asset


def inspect_one(root: Path, name: str, row: dict[str, Any]) -> dict[str, Any]:
    pil = importlib.import_module("PIL.Image")
    result: dict[str, Any] = {}
    try:
        p = asset(root, row["path"])
        with pil.open(p) as im:
            im.load()
            if im.size != tuple(row["size"]):
                raise ValueError("dimensions changed")
            if name == "FLAME" and row.get("split"):
                gray = im.convert("L").resize((9, 8))
                values = gray.tobytes()
                result["dhash"] = sum(
                    (values[i] > values[i + 1]) << (i - i // 9) for i in range(72) if i % 9 < 8
                )
            if im.format == "PNG":
                with p.open("rb") as stream:
                    result["bits_per_sample"] = stream.read(25)[24]
        if row.get("mask"):
            with pil.open(asset(root, row["mask"])) as mask:
                if mask.size != tuple(row["size"]) or mask.mode not in {"L", "P", "I", "I;16"}:
                    raise ValueError("invalid class-index mask")
                counts = mask.getcolors(256)
                if counts is None or any(
                    c not in range(10 + (name == "RescueNet")) for _, c in counts
                ):
                    raise ValueError("unknown mask class")
                result["pixels"] = {str(c): n for n, c in counts}
        if name == "WiSARD" and row.get("annotation"):
            side = p.with_suffix(".txt")
            classes: Counter[str] = Counter()
            for text in side.read_text(encoding="utf-8-sig").splitlines():
                label, x, y, w, h = text.split()
                cx, cy, width, height = map(float, (x, y, w, h))
                if not (
                    label.isdecimal()
                    and 0 < width <= 1
                    and 0 < height <= 1
                    and width / 2 <= cx <= 1 - width / 2
                    and height / 2 <= cy <= 1 - height / 2
                ):
                    raise ValueError("invalid normalized box")
                classes[label] += 1
            result["sidecar_classes"] = classes
    except (ValueError, OSError, IndexError) as exc:
        return {"error": str(exc)}
    return result


def scan(base: Path, name: str, destination: Path, workers: int) -> None:
    if not 1 <= workers <= 4:
        raise ValueError("choose one to four CPU workers")
    meta = json.loads((base / name / "summary.json").read_bytes())
    source = Path(meta["configuration"]["source"])
    index = base / name / "index.jsonl"
    checksum = digest(index)
    if checksum != meta["outputs"]["index.jsonl"]:
        raise ValueError("changed index")
    if destination.exists():
        report = json.loads((destination / "summary.json").read_bytes())
        if report["index_sha256"] != checksum or report["code_sha256"] != digest(Path(__file__)):
            raise ValueError("changed inspection configuration")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    counts: Counter[str] = Counter()
    pixels: Counter[str] = Counter()
    classes: Counter[str] = Counter()
    depths: Counter[str] = Counter()
    buckets: dict[tuple[int, int], set[int]] = defaultdict(set)
    with TemporaryDirectory(dir=destination.parent) as tmp:
        out = Path(tmp) / name
        out.mkdir()
        with (
            (out / "flags.jsonl").open("x", encoding="utf8") as flags,
            (out / "frame-hashes.jsonl").open("x", encoding="utf8") as hashes,
            ThreadPoolExecutor(workers) as pool,
        ):
            for group in batches(rows(index), workers):
                futures = [pool.submit(inspect_one, source, name, r) for r in group]
                for row, future in zip(group, futures, strict=True):
                    result = future.result()
                    counts["checked"] += 1
                    if result.get("error"):
                        print(
                            json.dumps({"path": row["path"], "error": result["error"]}), file=flags
                        )
                        counts["invalid"] += 1
                        continue
                    pixels.update(result.get("pixels", {}))
                    classes.update(result.get("sidecar_classes", {}))
                    if "bits_per_sample" in result:
                        depths[str(result["bits_per_sample"])] += 1
                    if "dhash" in result:
                        k = result["dhash"]
                        print(
                            json.dumps(
                                {"path": row["path"], "split": row["split"], "dhash": hex(k)}
                            ),
                            file=hashes,
                        )
                        bands = [(b, (k >> (16 * b)) & 65535) for b in range(4)]
                        if row["split"] == "test":
                            for band in bands:
                                buckets[band].add(k)
                        # Source traversal order is irrelevant: check train rows after all test hashes exist.
        if buckets:
            for row in rows(out / "frame-hashes.jsonl"):
                if row["split"] != "train":
                    continue
                k = int(row["dhash"], 16)
                if any(
                    (v ^ k).bit_count() <= 3
                    for b in range(4)
                    for v in buckets.get((b, (k >> (16 * b)) & 65535), set())
                ):
                    counts["train_frames_near_any_test_frame"] += 1
        write_json(
            out / "summary.json",
            {
                "dataset": name,
                "index_sha256": checksum,
                "code_sha256": digest(Path(__file__)),
                "counts": dict(counts),
                "mask_pixels": dict(pixels),
                "sidecar_classes": dict(classes),
                "png_bit_depth": dict(depths),
                "flags_sha256": digest(out / "flags.jsonl"),
                "frame_hashes_sha256": digest(out / "frame-hashes.jsonl"),
            },
        )
        out.rename(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument(
        "--source",
        required=True,
        choices=["FloodNet", "RescueNet", "FLAME", "SARD", "HERIDAL", "WiSARD"],
    )
    args = parser.parse_args()
    if args.root.resolve().drive.upper() != "D:":
        parser.error("use D: storage")
    scan(
        args.root / "processed/phase10g-v1",
        args.source,
        args.root / "manifests/phase10g-visual-v1" / args.source,
        args.workers,
    )
