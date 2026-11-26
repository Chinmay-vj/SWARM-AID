"""Validate the CrisisMMD event images and compare their bytes to indexed visual sources."""

import argparse
import hashlib
import importlib
import json
from collections import Counter
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from evaluation.data.model2 import digest, write_json
from evaluation.data.phase10g_quality import rows
from evaluation.data.review_loaders import asset


def run(root: Path) -> None:
    base = root / "processed/phase10g-v1"
    folder = base / "CrisisMMD"
    meta = json.loads((folder / "summary.json").read_bytes())
    index = folder / "index.jsonl"
    index_hash = digest(index)
    if meta["outputs"]["index.jsonl"] != index_hash:
        raise ValueError("changed event index")
    source = Path(meta["configuration"]["source"])
    dest = root / "manifests/phase10g-crisis-decode-v1"
    if dest.exists():
        raise FileExistsError(dest)
    pil = importlib.import_module("PIL.Image")
    outcomes: dict[str, str | None] = {}
    counts: Counter[str] = Counter()
    with TemporaryDirectory(dir=dest.parent) as tmp:
        stage = Path(tmp) / dest.name
        stage.mkdir()
        with (stage / "flags.jsonl").open("x", encoding="utf8") as flags:
            for row in rows(index):
                data = asset(source, row["path"]).read_bytes()
                key = hashlib.sha256(data).hexdigest()
                if key not in outcomes:
                    try:
                        with pil.open(BytesIO(data)) as image:
                            image.load()
                        outcomes[key] = None
                    except (ValueError, OSError, pil.DecompressionBombError) as exc:
                        outcomes[key] = type(exc).__name__
                counts["references"] += 1
                if outcomes[key]:
                    counts["flagged"] += 1
                    print(json.dumps({"path": row["path"], "error": outcomes[key]}), file=flags)
        overlaps = {}
        for name in ("HERIDAL", "SARD", "FloodNet", "RescueNet", "FLAME", "WiSARD"):
            other = base / name
            other_index = other / "index.jsonl"
            metadata = json.loads((other / "summary.json").read_bytes())
            if digest(other_index) != metadata["outputs"]["index.jsonl"]:
                raise ValueError("changed visual index")
            overlaps[name] = len({r["sha256"] for r in rows(other_index)} & outcomes.keys())
        write_json(stage / "summary.json", {
            "event_index_sha256": index_hash,
            "counts": dict(counts),
            "distinct_image_hashes": len(outcomes),
            "exact_hash_overlap_by_visual_source": overlaps,
            "flags_sha256": digest(stage / "flags.jsonl"),
            "code_sha256": digest(Path(__file__)),
        })
        stage.rename(dest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    run(parser.parse_args().root)
