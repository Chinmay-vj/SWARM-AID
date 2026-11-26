"""Aggregate HumAID split and text-overlap audit, without exporting posts."""

import argparse
import csv
import hashlib
import html
import importlib
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from evaluation.data.model2 import digest


def passages(text: str) -> set[bytes]:
    """Fingerprint contiguous 12-word passages after removing URLs and account handles."""
    value = unicodedata.normalize("NFKC", html.unescape(text)).casefold()
    words = re.findall(r"[^\W_]+", re.sub(r"https?://\S+|@\w+", " ", value))
    return {
        hashlib.sha256(" ".join(words[i : i + 12]).encode()).digest()
        for i in range(len(words) - 11)
    }


def passage_screen(humaid: Path, crisis: Path) -> dict[str, int]:
    """Report candidate rows only. Shared wording does not establish shared post identity."""
    known: set[bytes] = set()
    for path in sorted((crisis / "files_individual_events").glob("*.tsv")):
        with path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream, delimiter="\t", quoting=csv.QUOTE_NONE):
                known.update(passages(row["tweet_text"]))
    if not known:
        raise ValueError("no CrisisMMD passage index")
    result = {}
    with importlib.import_module("duckdb").connect(":memory:") as db:
        for split in ("train", "validation", "test"):
            table = db.read_parquet(str(humaid / f"{split}-00000-of-00001.parquet"))
            result[split] = sum(
                not known.isdisjoint(passages(text))
                for (text,) in table.project("tweet_text").fetchall()
                if text
            )
    return result


def text_key(value: str) -> str:
    text = unicodedata.normalize("NFKC", html.unescape(value)).casefold()
    return hashlib.sha256(" ".join(text.split()).encode()).hexdigest()


def audit(humaid: Path, crisis: Path) -> dict[str, Any]:
    shards = {s: humaid / f"{s}-00000-of-00001.parquet" for s in ("train", "validation", "test")}
    for path in shards.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    tables = sorted((crisis / "files_individual_events").glob("*.tsv"))
    if len(tables) != 7:
        raise ValueError("expected seven CrisisMMD v2 event tables")
    crisis_keys: set[str] = set()
    for path in tables:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream, delimiter="\t", quoting=csv.QUOTE_NONE):
                if row["tweet_text"].strip():
                    crisis_keys.add(text_key(row["tweet_text"]))
    splits: dict[str, Any] = {}
    memberships: dict[str, set[str]] = defaultdict(set)
    with importlib.import_module("duckdb").connect(":memory:") as db:
        for split, path in shards.items():
            table = db.read_parquet(str(path))
            schema = dict(zip(table.columns, map(str, table.types), strict=True))
            if any(schema.get(k) != "VARCHAR" for k in ("tweet_text", "class_label")):
                raise ValueError("incompatible HumAID schema")
            labels: Counter[str] = Counter()
            unique: set[str] = set()
            missing = overlap = total = 0
            for text, label in table.project("tweet_text, class_label").fetchall():
                total += 1
                if not text or not text.strip() or not label or not label.strip():
                    missing += 1
                    continue
                if not re.fullmatch(r"[a-z_]+", label):
                    raise ValueError("unexpected public annotation vocabulary")
                labels[label] += 1
                key = text_key(text)
                unique.add(key)
                memberships[key].add(split)
                overlap += key in crisis_keys
            splits[split] = {
                "source_file": path.name,
                "sha256": digest(path),
                "bytes": path.stat().st_size,
                "schema": schema,
                "rows": total,
                "missing": missing,
                "labels": dict(labels),
                "distinct_text": len(unique),
                "rows_matching_crisismmd": overlap,
            }
    return {
        "source": "QCRI/HumAID-all",
        "role": "supplementary_disaster_context",
        "approval": "pending",
        "splits": splits,
        "distinct_text": len(memberships),
        "text_in_multiple_humaid_splits": sum(len(v) > 1 for v in memberships.values()),
        "distinct_text_matching_crisismmd": len(crisis_keys.intersection(memberships)),
        "crisismmd_tables": {p.name: digest(p) for p in tables},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Screen candidate shared 12-word passages")
    parser.add_argument("--humaid", type=Path, required=True)
    parser.add_argument("--crisis", type=Path, required=True)
    args = parser.parse_args()
    print(passage_screen(args.humaid, args.crisis))
