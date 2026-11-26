"""Append first-look human judgments independently of the adjudicated revision history."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

from evaluation.data.field_review import agreement
from evaluation.data.model2 import digest, read_rows
from evaluation.data.model2_records import Input, Target


def reviewer_key(name: str) -> str:
    if not name.strip():
        raise ValueError("missing reviewer")
    return hashlib.sha256(name.encode("utf8")).hexdigest()


def submit(root: Path, form: Target) -> Path:
    directory = root / "annotations/model2/phase10g-field-v1"
    manifest = json.loads((directory / "manifest.json").read_bytes())
    queue = directory / "review-queue.jsonl"
    if digest(queue) != manifest["queue_sha256"]:
        raise ValueError("changed review batch")
    if (
        not form.reviewer
        or form.provenance != "human_reviewed"
        or form.revision != 1
        or form.recommendation
        or form.baseline_incident
    ):
        raise ValueError("first look requires independent revision one without baseline objects")
    with queue.open(encoding="utf8") as stream:
        selected = next(
            (r for r in map(json.loads, stream) if r["form"]["sample_id"] == str(form.sample_id)),
            None,
        )
    if not selected:
        raise ValueError("sample outside blinded queue")
    version = selected["version"]
    batch = root / "processed/model2" / version
    release = batch / "release.json"
    if digest(release) != manifest["release_hashes"][version]:
        raise ValueError("source release changed")
    inputs = batch / "inputs.jsonl"
    if digest(inputs) != json.loads(release.read_bytes())["files"]["inputs.jsonl"]:
        raise ValueError("source inputs changed")
    sample = next(r for r in read_rows(inputs, Input) if r.sample_id == form.sample_id)
    form.check(sample)
    parent = directory / "first-look" / reviewer_key(form.reviewer)
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / (str(form.sample_id) + ".json")
    tmp = parent / (str(uuid4()) + ".tmp")
    try:
        tmp.write_text(form.model_dump_json(), encoding="utf8")
        os.link(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    return target


def assessments(root: Path, reviewer: str) -> dict[UUID, str]:
    folder = root / "annotations/model2/phase10g-field-v1/first-look" / reviewer_key(reviewer)
    result = {}
    for path in folder.glob("*.json"):
        form = Target.model_validate_json(path.read_bytes())
        if reviewer != form.reviewer or path.stem != str(form.sample_id):
            raise ValueError("first-look provenance mismatch")
        result[form.sample_id] = form.assessment or "abstain"
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--submit", type=Path)
    action.add_argument("--agreement", nargs=2)
    args = parser.parse_args()
    if args.root.resolve().drive.upper() != "D:":
        parser.error("use D: storage")
    if args.submit:
        submit(args.root, Target.model_validate_json(args.submit.read_bytes()))
    else:
        a, b = args.agreement
        if a == b:
            parser.error("choose independent reviewers")
        print(json.dumps(agreement(assessments(args.root, a), assessments(args.root, b))))
