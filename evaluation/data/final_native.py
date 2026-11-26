"""Audit frozen symbolic releases and evaluator journals without replaying any mission."""

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from evaluation.data.model2 import digest, validate_release
from evaluation.data.model2_records import Features, Target
from evaluation.data.phase10g_quality import rows


def checked(path: Path, expected: str) -> None:
    if digest(path) != expected:
        raise ValueError(f"checksum mismatch: {path.name}")


def audit_native(root: Path) -> dict[str, Any]:
    base = root / "processed/model2"
    replay = root / "simulation/field-v1"
    rm = json.loads((replay / "manifest.json").read_bytes())
    for f, sha in rm["files"].items():
        checked(replay / f, sha)
    checks = len(rm["files"])
    releases = {}
    evidence_splits: dict[str, set[str]] = defaultdict(set)
    all_samples: dict[str, tuple[str, str, str]] = {}
    distributions: dict[str, dict[str, Counter[str]]] = {}
    pilot_ids: set[str] = set()
    overlap = 0
    model1: Counter[str] = Counter()
    reports = set()
    observations = set()
    providers: Counter[str] = Counter()
    evidence_by_episode: dict[str, set[str]] = defaultdict(set)
    for batch in [base / "pilot-2", *sorted(base.glob("field-v1-*"))]:
        pilot = batch.name == "pilot-2"
        meta = json.loads((batch / "release.json").read_bytes())
        splits = validate_release(batch)
        if not pilot:
            checked(
                batch / "release.json", rm["release_hashes"][batch.name.removeprefix("field-v1-")]
            )
            checks += 1 + len(meta["files"])
        category = "pilot" if pilot else "expanded"
        stats = distributions.setdefault(category, defaultdict(Counter))
        groups = set()
        for record, target in zip(
            rows(batch / "inputs.jsonl"), rows(batch / "targets.jsonl"), strict=True
        ):
            sid = record["sample_id"]
            if sid in all_samples or record["seed"] in range(42, 47) and record["split"] != "test":
                raise ValueError("duplicate identity or protected development row")
            all_samples[sid] = (batch.name, record["episode_id"], record["split"])
            receipts = [record["receipt"], *record["context"]]
            groups.add(tuple(sorted({r["report"]["message_id"] for r in receipts})))
            evidence = {
                e["evidence_id"]
                for r in receipts
                for e in r["report"]["finding"]["observation"]["evidence"]
            }
            if pilot:
                pilot_ids.update(evidence)
            else:
                overlap += bool(pilot_ids & evidence)
            for eid in evidence:
                evidence_splits[eid].add(category + "/" + record["split"])
            evidence_by_episode[record["episode_id"]].update(evidence)
            for key in ("scenario_id", "agents", "split", "variant", "communication"):
                stats[key][str(record[key])] += 1
            for key in (
                "assessment",
                "relationship",
                "urgency",
                "status",
                "provenance",
                "review_required",
            ):
                stats[key][str(target[key])] += 1
            stats["missing_information"][str(bool(target["missing_information"]))] += 1
            stats["uncertainty"][str(bool(target["uncertainty"]))] += 1
            stats["recommendation"][str(bool(target["recommendation"]))] += 1
            for ev in record["receipt"]["report"]["finding"]["observation"]["evidence"]:
                stats["focal_modality"][ev["modality"]] += 1
        for ep in meta["episodes"]:
            if not pilot:
                for row in rows(batch / ep["model1_file"]):
                    report = row["report"]
                    obs = report["finding"]["observation"]
                    reports.add(report["message_id"])
                    observations.add(obs["observation_id"])
                    providers[row["provider"]] += 1
                    model1[report["finding"]["kind"]] += 1
        releases[batch.name] = {
            "release_sha256": digest(batch / "release.json"),
            "manifest_sha256": digest(batch / "manifest.json"),
            "payloads": meta["files"],
            "schema": meta["schema_version"],
            "taxonomy": meta["taxonomy_version"],
            "episodes": len(meta["episodes"]),
            "groups": len(groups),
            "split": splits,
            "providers": meta["episodes"][0]["providers"] if not pilot else None,
            "version": meta["version"],
            "source_digests": meta["source_digests"],
        }
    queue = root / "annotations/model2/phase10g-field-v1"
    qm = json.loads((queue / "manifest.json").read_bytes())
    checked(queue / "review-queue.jsonl", qm["queue_sha256"])
    selected = set()
    episodes = set()
    for row in rows(queue / "review-queue.jsonl"):
        f = Features.model_validate(row["features"])
        form = Target.model_validate(row["form"])
        if (
            form != Target(sample_id=f.sample_id, provenance="unresolved")
            or str(f.sample_id) in selected
            or all_samples[str(f.sample_id)][0] != row["version"]
        ):
            raise ValueError("first-look form unblinded or repeated")
        selected.add(str(f.sample_id))
        episodes.add(all_samples[str(f.sample_id)][1])
    submitted = list((queue / "first-look").glob("*/*.json"))
    adjudications = [
        p for name in releases for p in (root / "annotations/model2" / name).glob("*.json")
    ]
    reviews: Counter[str] = Counter()
    for file in submitted + adjudications:
        reviewed = Target.model_validate_json(file.read_bytes())
        if reviewed.provenance != "human_reviewed" or not reviewed.reviewer:
            raise ValueError("unattributed submission")
        reviews[reviewed.status] += 1
    crossing = {eid for eid, memberships in evidence_splits.items() if len(memberships) > 1}
    excluded = sorted(ep for ep, ids in evidence_by_episode.items() if ids & crossing)
    return {
        "review_split_excluded_episodes": excluded,
        "releases": releases,
        "class_counts": distributions,
        "field_checksums": checks,
        "model1": dict(model1),
        "model1_report_ids": len(reports),
        "model1_observation_ids": len(observations),
        "model1_provider": providers,
        "cross_split_evidence_keys": dict(
            Counter(" & ".join(sorted(v)) for v in evidence_splits.values() if len(v) > 1)
        ),
        "replay_availability": rm["availability"],
        "field_rows_sharing_pilot_evidence": overlap,
        "queue_count": len(selected),
        "queued_episodes": len(episodes),
        "first_look_forms": len(submitted),
        "adjudications": len(adjudications),
        "human_status": reviews,
        "queue_sha256": qm["queue_sha256"],
    }


def alerts(out: Path) -> dict[str, Any]:
    folder = Path("runs/phase10g-alert-v2")
    source = folder / "matched.jsonl"
    summary = json.loads((folder / "summary.json").read_bytes())
    checked(source, summary["matched_sha256"])
    checked(Path("configs/experiments/phase6_field_command.json"), summary["plan_sha256"])
    matched = list(rows(source))
    cited: dict[tuple[str, int, int], set[str]] = defaultdict(set)
    counts: Counter[str] = Counter()
    for row in matched:
        r, f = row["rules"], row["fusion"]
        if row["seed"] in range(42, 47) or any(
            r[k] != f[k] for k in ("evidence", "observation", "captured_ms", "kind", "colocated")
        ):
            raise ValueError("unmatched or reserved evaluation case")
        seen = cited[row["scenario"], row["agents"], row["seed"]]
        seen.update(f["explicit_evidence_ms"])
        if f["citations"]:
            seen.update(f["evidence"])
    with (out / "alert-review.jsonl").open("x", encoding="utf8") as stream:
        for row in matched:
            r, f = row["rules"], row["fusion"]
            left, right = r["first_ms"], f["first_ms"]
            status = (
                ("both" if right is not None else "rules_only")
                if left is not None
                else ("fusion_only" if right is not None else "neither")
            )
            if row["status"] != status:
                raise ValueError("incorrect historical classification")
            counts[status] += 1
            if r["colocated"]:
                counts["colocated_" + status] += 1
            if left is not None and right is not None and left < right:
                counts["later_in_fusion"] += 1
            if status == "rules_only":
                evidence = set(r["evidence"])
                retained = evidence & cited[row["scenario"], row["agents"], row["seed"]]
                outcome = "all" if retained == evidence else "partial" if retained else "none"
                counts["attributed_" + outcome] += 1
                counts["corroborated"] += "corroborated" in f["source_events"]
                if r["colocated"]:
                    counts["colocated_attributed_" + outcome] += 1
                print(
                    json.dumps(
                        {k: row[k] for k in ("scenario", "agents", "seed", "report")}
                        | {
                            "observation": r["observation"],
                            "retained": sorted(retained),
                            "absent": sorted(evidence - retained),
                            "reference_colocated": r["colocated"],
                            "fusion_events": f["source_events"],
                            "human_disposition": "pending",
                        }
                    ),
                    file=stream,
                )
    return {
        "counts": counts,
        "matched": len(matched),
        "source_sha256": digest(source),
        "review_sha256": digest(out / "alert-review.jsonl"),
    }


def baselines() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, group in (("coordination", "policy"), ("command", "mode")):
        folder = next(Path("runs/field-" + name).glob("*/comparison.csv")).parent
        sums: dict[str, Counter[str]] = defaultdict(Counter)
        identities = set()
        for file in folder.glob("episode-*.json"):
            r = json.loads(file.read_bytes())
            cfg = r["scenario"]
            key = (
                cfg["scenario_id"] if "scenario_id" in cfg else cfg["name"],
                cfg["agents"],
                cfg["seed"],
                r[group],
            )
            if key in identities or cfg["seed"] in range(42, 47):
                raise ValueError("duplicate or protected baseline")
            identities.add(key)
            s = sums[r[group]]
            s["episodes"] += 1
            if name == "coordination":
                s["coverage"] += r["metrics"]["coverage"]
            else:
                for k in ("operator_updates", "observations"):
                    s[k] += r[k]
        result[name] = sums
    return result


def main(root: Path) -> None:
    import shutil
    from tempfile import TemporaryDirectory

    from evaluation.data.model2 import write_json

    dest = root / "manifests/phase10h-native-v1"
    if root.resolve().drive.upper() != "D:" or shutil.disk_usage(root).free < 20480 << 20:
        raise ValueError("D-drive release with 20 GiB reserve required")
    if dest.exists():
        raise FileExistsError(dest)
    with TemporaryDirectory(dir=dest.parent) as tmp:
        out = Path(tmp) / dest.name
        out.mkdir()
        write_json(out / "native.json", audit_native(root))
        out.rename(dest)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument("--root", type=Path)
    options.add_argument("--journals", type=Path)
    args = parser.parse_args()
    if args.root:
        main(args.root)
    else:
        from tempfile import TemporaryDirectory

        from evaluation.data.model2 import write_json

        dest = args.journals.resolve()
        if dest.drive.upper() != "D:" or dest.exists():
            raise ValueError("unused D-drive destination required")
        with TemporaryDirectory(dir=dest.parent) as tmp:
            out = Path(tmp) / dest.name
            out.mkdir()
            write_json(out / "alerts.json", alerts(out))
            write_json(out / "baselines.json", baselines())
            out.rename(dest)
