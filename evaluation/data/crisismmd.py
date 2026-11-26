"""Read-only inventory of extracted CrisisMMD task tables and optional ZIP members."""

import argparse
import csv
import hashlib
import json
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def map_observed(label: str, vocabulary: set[str]) -> str | None:
    """A public annotation remains a social-media task label, never a drone finding."""
    if label not in vocabulary:
        raise ValueError("unobserved source label")
    mapping = {
        "informative": "public_informative",
        "not_informative": "public_uninformative",
        "infrastructure_and_utility_damage": "public_infrastructure_context",
        "affected_individuals": "public_affected_people_context",
        "injured_or_dead_people": "public_reported_casualty_context",
        "vehicle_damage": "public_vehicle_damage_context",
        "other_relevant_information": "public_other_context",
        "not_humanitarian": "public_nonhumanitarian_context",
        "missing_or_found_people": "public_missing_or_found_context",
        "rescue_volunteering_or_donation_effort": "public_response_context",
        "severe_damage": "public_damage_severity",
        "mild_damage": "public_damage_severity",
        "little_or_no_damage": "public_damage_severity",
    }
    return mapping.get(label.strip().lower().replace(" ", "_"))


def snapshot_integrity(root: Path, hashes: dict[str, str]) -> dict[str, Any]:
    """Compare payloads with the local downloader index when one snapshot is identifiable."""
    indices = list((root / ".cache/huggingface/trees").glob("*.json"))
    if len(indices) != 1:
        return {"status": "unknown"}
    index = indices[0]
    entries = json.loads(index.read_bytes())["files"]
    missing = mismatched = size = 0
    for name, entry in entries.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("snapshot entry outside release")
        if not path.is_file():
            missing += 1
            continue
        size += path.stat().st_size
        if "lfs_sha256" in entry:
            actual = hashes.get(name) or hashlib.sha256(path.read_bytes()).hexdigest()
            expected = entry["lfs_sha256"]
        else:
            data = path.read_bytes()
            actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            expected = entry["blob_id"]
        mismatched += actual != expected or path.stat().st_size != entry["size"]
    return {
        "revision": index.stem,
        "index_sha256": hashlib.sha256(index.read_bytes()).hexdigest(),
        "files": len(entries),
        "bytes": size,
        "missing": missing,
        "mismatched": mismatched,
        "status": "failed" if missing or mismatched else "matched",
    }


def benchmark(root: Path, images: set[str]) -> dict[str, Any]:
    """Summarize the publisher's JSON task views without exporting posts or images."""
    hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in images}
    splits = []
    memberships: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    referenced: set[str] = set()
    for task in ("informative", "humanitarian", "damage"):
        for split in ("train", "dev", "test"):
            path = root / task / (split + ".json")
            if not path.exists():
                continue
            records = json.loads(path.read_bytes())
            events: Counter[str] = Counter()
            labels: Counter[str] = Counter()
            posts, pairs = set(), set()
            missing = empty = 0
            for row in records:
                post, image, name = str(row["tweet_id"]), row["image_id"], row["image_path"]
                posts.add(post)
                pairs.add((post, image))
                referenced.add(name)
                label = row["label"]
                labels[label] += 1
                events[row["event_name"]] += 1
                empty += not row["tweet_text"].strip()
                missing += name not in images
                groups = {"post": post, "image": image, "event": row["event_name"]}
                if name in hashes:
                    groups["media_sha256"] = hashes[name]
                for key, value in groups.items():
                    memberships[key][value].add(split)
                    memberships[task + "/" + key][value].add(split)
            splits.append(
                {
                    "file": path.relative_to(root).as_posix(),
                    "records": len(records),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "posts": len(posts),
                    "pairs": len(pairs),
                    "labels": dict(labels),
                    "mapping": {k: map_observed(k, set(labels)) for k in labels},
                    "events": dict(events),
                    "missing_images": missing,
                    "empty_text": empty,
                }
            )
    return {
        "splits": splits,
        "snapshot_integrity": snapshot_integrity(root, hashes),
        "unique": {k: len(v) for k, v in memberships.items()},
        "across_splits": {k: sum(len(s) > 1 for s in v.values()) for k, v in memberships.items()},
        "unreferenced_images": len(images - referenced),
        "distinct_image_bytes": len(set(hashes.values())),
    }


def inspect(root: Path) -> dict[str, Any]:
    if not root.is_dir():
        raise FileNotFoundError(root)
    tables = []
    images = {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    }
    archives = {}
    for archive in sorted(root.rglob("*.zip")):
        with zipfile.ZipFile(archive) as z:
            archives[archive.relative_to(root).as_posix()] = {
                "members": len(z.infolist()),
                "crc_pass": z.testzip() is None,
            }
    for table in sorted(root.rglob("*.tsv")):
        counts: dict[str, Counter[str]] = {}
        missing = records = 0
        pairs: set[tuple[str, str]] = set()
        posts: set[str] = set()
        events: Counter[str] = Counter()
        with table.open(encoding="utf-8-sig", newline="") as stream:
            # Event TSVs contain literal quotation marks in free text.
            reader = csv.DictReader(stream, delimiter="\t", quoting=csv.QUOTE_NONE)
            for row in reader:
                records += 1
                if None in row or any(v is None for v in row.values()):
                    raise ValueError("malformed annotation table")
                for key, val in row.items():
                    if key.startswith("label") or key in (
                        "text_info",
                        "image_info",
                        "text_human",
                        "image_human",
                        "image_damage",
                    ):
                        counts.setdefault(key, Counter())[val] += 1
                if row.get("tweet_id"):
                    posts.add(row["tweet_id"])
                if row.get("event_name"):
                    events[row["event_name"]] += 1
                if row.get("image_id") and row.get("tweet_id"):
                    pairs.add((row["tweet_id"], row["image_id"]))
                name = row.get("image_path", row.get("image"))
                if name is not None and name.removeprefix("./") not in images:
                    missing += 1
        tables.append(
            {
                "file": table.relative_to(root).as_posix(),
                "sha256": hashlib.sha256(table.read_bytes()).hexdigest(),
                "records": records,
                "posts": len(posts),
                "pairs": len(pairs),
                "events": dict(events),
                "missing_image_paths": missing,
                "labels": {k: dict(v) for k, v in counts.items()},
                "mapping": {
                    label: map_observed(label, set(v)) for v in counts.values() for label in v
                },
            }
        )
    return {
        "images": len(images),
        "tables": tables,
        "archives": archives,
        "benchmark": benchmark(root, images),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.source), indent=2))
