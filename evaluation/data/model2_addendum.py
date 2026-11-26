"""Create reference collections and a pending reviewer batch for an existing pilot."""

import argparse
import json
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import UUID

from evaluation.data.humaid import audit
from evaluation.data.model2 import digest, read_rows, validate_release, write_json, write_rows
from evaluation.data.model2_records import Input, Target

GOALS = {
    "false_alarm": 40,
    "conflicting": 50,
    "duplicate_or_forwarded": 50,
    "communication_interruption": 30,
    "multiple_unrelated_incidents": 30,
    "missing_information": 50,
    "stale": 30,
    "possible_rescue": 70,
    "independent_observations": 80,
    "routine": 70,
}


def conditions(
    row: Input, target: Target, episode: dict[str, Any], false_ids: set[UUID]
) -> list[str]:
    config = episode["configuration"]
    tick = config["tick_ms"]
    offline_ticks = set(config["network"]["server_down"]) | set(config["outage_steps"])
    in_transit = any(
        row.receipt.sent_ms <= step * tick <= row.receipt.received_ms for step in offline_ticks
    )
    flags = {
        "false_alarm": row.sample_id in false_ids,
        "conflicting": target.relationship == "conflicting",
        "duplicate_or_forwarded": target.relationship == "duplicate" or row.variant == "relay",
        "communication_interruption": row.variant == "native" and in_transit,
        "missing_information": bool(row.disabled_modalities or target.missing_information),
        "stale": row.age_ms >= episode["settings"]["freshness_ms"],
        "possible_rescue": target.assessment in ("possible_human", "uncertain_need"),
        "independent_observations": target.relationship == "corroborating",
        "routine": target.assessment == "routine",
    }
    return [key for key in GOALS if flags.get(key)]


def summarize(release: Path, out: Path) -> dict[str, Any]:
    splits = validate_release(release)
    meta = json.loads((release / "release.json").read_bytes())
    episodes = {e["episode_id"]: e for e in meta["episodes"]}
    false_ids = {
        UUID(e["sample_id"])
        for e in json.loads((release / "evaluator.json").read_bytes())
        if e.get("controlled_false_sighting") is True
    }
    rows = read_rows(release / "inputs.jsonl", Input)
    targets = read_rows(release / "targets.jsonl", Target)
    eligible: Counter[str] = Counter()
    primary: Counter[str] = Counter()
    categories = {}
    for row, target in zip(rows, targets, strict=True):
        flags = conditions(row, target, episodes[str(row.episode_id)], false_ids)
        eligible.update(flags)
        key = next((k for k in flags if primary[k] < GOALS[k]), next(iter(flags), "other"))
        primary[key] += 1
        categories[row.sample_id] = key

    # Preserve the original batch and fill underrepresented strata deterministically.
    selected = {t.sample_id for t in read_rows(release / "review-queue.jsonl", Target)}
    by_id = {r.sample_id: r for r in rows}
    if not selected <= by_id.keys() or len(selected) > 50:
        raise ValueError("original review batch is incompatible")
    cat_count = Counter(categories[i] for i in selected)
    ep_count = Counter(by_id[i].episode_id for i in selected)
    while len(selected) < min(50, len(rows)):
        row = min(
            (r for r in rows if r.sample_id not in selected),
            key=lambda r: (cat_count[categories[r.sample_id]], ep_count[r.episode_id], r.sample_id),
        )
        selected.add(row.sample_id)
        cat_count[categories[row.sample_id]] += 1
        ep_count[row.episode_id] += 1
    write_rows(
        out / "review-queue.jsonl",
        (Target(sample_id=i, provenance="unresolved") for i in sorted(selected)),
    )
    # The indices join to the immutable inputs, retaining the original line order and IDs.
    for name, native in (("native", True), ("controlled", False)):
        with (out / f"{name}-index.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
            for n, r in enumerate(rows, 1):
                if (r.variant == "native") == native:
                    print(json.dumps({"sample_id": str(r.sample_id), "input_line": n}), file=stream)
    return {
        "release_sha256": digest(release / "release.json"),
        "splits": splits,
        "category_goals": GOALS,
        "eligible": dict(eligible),
        "primary": dict(primary),
        "review_primary": dict(cat_count),
        "review_episodes": len(ep_count),
        "review_count": len(selected),
        "disasters": dict(
            Counter(episodes[str(r.episode_id)]["configuration"]["disaster"] for r in rows)
        ),
        "source_files": meta["files"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--humaid", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, help="unused addendum directory under manifests/model2"
    )
    args = parser.parse_args()
    root = args.root.resolve()
    if root.drive.upper() != "D:" or args.humaid.resolve().drive.upper() != "D:":
        parser.error("use D: dataset storage")
    release = root / "processed/model2/pilot-2"
    parent = root / "manifests/model2"
    dest = (args.output or parent / "pilot-2-addendum-1").resolve()
    if dest.parent != parent:
        parser.error("output must be a direct child of manifests/model2")
    if dest.exists():
        raise FileExistsError(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=dest.parent) as tmp:
        out = Path(tmp) / "addendum"
        out.mkdir()
        native = summarize(release, out)
        public = audit(args.humaid, root / "raw/multimodal/CrisisMMD")
        write_json(out / "coverage.json", native)
        write_json(out / "humaid-context.json", public)
        crisis_audit = root / "manifests/model2/crisismmd-10a5626-audit.json"
        verified = json.loads(crisis_audit.read_bytes())
        if public["crisismmd_tables"] != {
            Path(t["file"]).name: t["sha256"] for t in verified["tables"]
        }:
            raise ValueError("CrisisMMD tables differ from the audited snapshot")
        write_json(
            out / "manifest.json",
            {
                "version": "1.0",
                "release": "processed/model2/pilot-2",
                "native": "native-index.jsonl",
                "controlled": "controlled-index.jsonl",
                "baseline_and_unresolved_targets": "processed/model2/pilot-2/targets.jsonl",
                "evaluation": "processed/model2/pilot-2/evaluator.json",
                "review_batch": "review-queue.jsonl",
                "human_reviews": "annotations/model2/pilot-2",
                "humaid_source": str(args.humaid.resolve()),
                "humaid_context": "humaid-context.json",
                "crisismmd_context": crisis_audit.relative_to(root).as_posix(),
                "crisismmd_audit_sha256": digest(crisis_audit),
                "files": {p.name: digest(p) for p in out.iterdir()},
            },
        )
        out.rename(dest)
    print(dest)
    print(json.dumps({k: v for k, v in native.items() if k != "source_files"}))
    print(json.dumps(public))
    print("Addendum bytes", sum(p.stat().st_size for p in dest.iterdir()))


if __name__ == "__main__":
    main()
