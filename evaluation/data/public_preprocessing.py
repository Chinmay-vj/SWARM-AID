"""Local source inspection. Outputs are review indexes, never approvals."""

import csv
import hashlib
import importlib
import json
import os
import wave
from collections import Counter, defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from evaluation.data.contracts import relative_path
from evaluation.data.model2 import digest
from evaluation.data.preprocessing import normalized_text

IMAGES = {".jpeg", ".jpg", ".png", ".tif", ".tiff"}


def files(root: Path) -> Iterator[Path]:
    def fail(error: OSError) -> None:
        raise error

    if not root.is_dir():
        raise FileNotFoundError(root)
    for folder, dirs, names in os.walk(root, onerror=fail):
        dirs.sort()
        for name in sorted(names):
            yield Path(folder) / name


def coco(root: Path) -> Iterator[dict[str, Any]]:
    for table in sorted(root.glob("*/_annotations.coco.json")):
        doc = json.loads(table.read_bytes())
        labels = {c["id"]: c["name"] for c in doc["categories"]}
        images = {i["id"] for i in doc["images"]}
        groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
        ids = set()
        for a in doc["annotations"]:
            if a["image_id"] not in images or a["id"] in ids:
                yield {"annotation": a["id"], "error": "orphan or duplicate annotation ID"}
            ids.add(a["id"])
            groups[a["image_id"]].append(a)
        seen = set()
        for i in doc["images"]:
            p = table.parent / relative_path(i["file_name"])
            anns = groups[i["id"]]
            error = None
            if i["id"] in seen or not p.is_file():
                error = "repeated image ID or missing file"
            seen.add(i["id"])
            boxes = set()
            for a in anns:
                x, y, w, h = a["bbox"]
                key = (a["category_id"], x, y, w, h)
                if not (
                    0 <= x < x + w <= i["width"]
                    and 0 <= y < y + h <= i["height"]
                    and a["category_id"] in labels
                    and key not in boxes
                ):
                    error = "invalid or repeated box/category"
                boxes.add(key)
            yield {
                "path": p.relative_to(root).as_posix(),
                "source": table.relative_to(root).as_posix(),
                "image_id": i["id"],
                "split": table.parent.name,
                "size": [i["width"], i["height"]],
                "annotations": anns,
                "categories": labels,
                "error": error,
            }


def visual(root: Path, name: str, pilot: int) -> Iterator[dict[str, Any]]:
    pil = importlib.import_module("PIL.Image")
    if name in {"HERIDAL", "SARD"}:
        records = coco(root)
    else:
        records = (
            {"path": p.relative_to(root).as_posix()}
            for p in files(root)
            if p.suffix.lower() in IMAGES
        )
    decoded: Counter[str] = Counter()
    for row in records:
        if not row.get("path") or row.get("error"):
            yield row
            continue
        path = root / row["path"]
        parts = Path(row["path"]).parts
        if name in {"FloodNet", "RescueNet"}:
            if not any(p.endswith("-org-img") for p in parts):
                continue
            split = next(p for p in parts if p in {"train", "val", "test"})
            mask = path.parents[1] / f"{split}-label-img" / (path.stem + "_lab.png")
            row.update(split=split, mask=mask.relative_to(root).as_posix())
        elif name == "FLAME":
            row.update(
                label=path.parent.name, split={"Training": "train", "Test": "test"}.get(parts[0])
            )
            if parts[0] == "Masks":
                row.update(task="unpaired_mask", label=None)
        elif name == "WiSARD":
            row.update(
                sequence=parts[0],
                modality="thermal" if "_IR_" in parts[0] else "image",
                annotation=path.with_suffix(".txt").is_file(),
                paired=False,
            )
        try:
            row["sha256"] = digest(path)
            with pil.open(path) as im:
                if row.get("size", list(im.size)) != list(im.size):
                    raise ValueError("annotation dimension mismatch")
                row.update(
                    size=list(im.size),
                    mode=im.mode,
                    bit_depth=(
                        im.tag_v2.get(258)
                        if im.format == "TIFF"
                        else (
                            16
                            if "16" in im.mode
                            else 8
                            if im.mode in ("RGB", "L", "RGBA") and im.format == "JPEG"
                            else None
                        )
                    ),
                    channels=len(im.getbands()),
                    format=im.format,
                    orientation=im.getexif().get(274, 1),
                )
                if row.get("mask"):
                    with pil.open(root / row["mask"]) as m:
                        if m.size != im.size or m.mode not in ("P", "L", "I", "I;16"):
                            raise ValueError("mask shape or representation")
                        row["mask_mode"] = m.mode
                        if decoded[str(row.get("split"))] < pilot:
                            colors = m.getcolors(256)
                            if colors is None or any(
                                c not in range(10 + (name == "RescueNet")) for _, c in colors
                            ):
                                raise ValueError("unexpected mask class")
                            row["mask_histogram"] = {str(c): n for n, c in colors}
                group = str(row.get("split") or row.get("modality") or row.get("task"))
                if decoded[group] < pilot:
                    im.load()
                    gray = list(im.convert("L").resize((9, 8)).getdata())
                    row["dhash"] = hex(
                        sum((gray[j] > gray[j + 1]) << (j - j // 9) for j in range(72) if j % 9 < 8)
                    )
                    decoded[group] += 1
        except (OSError, ValueError) as exc:
            row["error"] = type(exc).__name__ + ": " + str(exc)
        yield row


def esc(root: Path) -> Iterator[dict[str, Any]]:
    table = next(root.rglob("esc50.csv"))
    with table.open(encoding="utf8", newline="") as src:
        for r in csv.DictReader(src):
            path = table.parent.parent / "audio" / relative_path(r["filename"])
            row: dict[str, Any] = {
                "path": path.relative_to(root).as_posix(),
                "label": r["category"],
                "target": r["target"],
                "group": r["src_file"],
                "fold": int(r["fold"]),
            }
            try:
                with wave.open(str(path)) as wav:
                    n = wav.getnframes()
                    data = wav.readframes(n)
                    if (
                        len(data) != n * wav.getsampwidth() * wav.getnchannels()
                        or not 1 <= row["fold"] <= 5
                    ):
                        raise ValueError("invalid waveform or fold")
                    row.update(
                        rate=wav.getframerate(),
                        channels=wav.getnchannels(),
                        duration=n / wav.getframerate(),
                        sha256=digest(path),
                    )
            except (ValueError, OSError, wave.Error, EOFError) as exc:
                row["error"] = str(exc)
            yield row


def context(root: Path, name: str) -> Iterator[dict[str, Any]]:
    if name == "HumAID":
        with importlib.import_module("duckdb").connect(":memory:") as db:
            for path in sorted(root.glob("*.parquet")):
                cursor = db.execute(
                    "select tweet_text,class_label from read_parquet(?)", [str(path)]
                )
                line = 0
                while rows := cursor.fetchmany(256):
                    for value, label in rows:
                        line += 1
                        normalized = normalized_text(value)
                        yield {
                            "source": path.name,
                            "line": line,
                            "split": path.name.split("-")[0],
                            "label": label,
                            "text_key": text_digest(normalized),
                            "error": None if normalized and label else "missing text/label",
                        }
    else:
        for path in sorted((root / "files_individual_events").glob("*.tsv")):
            with path.open(encoding="utf-8-sig", newline="") as src:
                for line, r in enumerate(
                    csv.DictReader(src, delimiter="\t", quoting=csv.QUOTE_NONE), 2
                ):
                    ref = relative_path(r["image_path"].removeprefix("./"))
                    normalized = normalized_text(r["tweet_text"])
                    yield {
                        "source": path.relative_to(root).as_posix(),
                        "line": line,
                        "path": ref,
                        "event": path.stem,
                        "text_key": text_digest(normalized),
                        "labels": {
                            k: v
                            for k, v in r.items()
                            if k.startswith(("text_", "image_"))
                            and k not in {"image_path", "image_id", "image_url"}
                        },
                        "error": None
                        if normalized and (root / ref).is_file()
                        else "missing text/media",
                    }


def text_digest(value: str | None) -> str | None:
    return hashlib.sha256(value.casefold().encode()).hexdigest() if value else None
