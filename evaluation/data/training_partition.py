"""Use approved Phase 10A release manifests to fit or consume frozen development parameters."""

import json
import math
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

from evaluation.data.contracts import Manifest, Registry, Sample
from evaluation.data.model2 import digest
from evaluation.data.preprocessing import batches, fit, require_training
from evaluation.data.release_authorization import (
    AuthorizationRecord,
    require_training_authorization,
)
from evaluation.data.validation import validate


def approved_training(
    registry: Registry,
    manifests: tuple[Manifest, ...],
    root: Path,
    size: int = 1,
    *,
    task_id: str | None = None,
    candidate_manifest_paths: Mapping[str, Path] | None = None,
    authorization_records: tuple[AuthorizationRecord, ...] = (),
) -> Iterator[list[Sample]]:
    if not manifests:
        raise ValueError("at least one authorized release manifest is required")
    for manifest in manifests:
        require_training_authorization(
            registry,
            manifest,
            task_id=task_id,
            candidate_manifest_paths=candidate_manifest_paths,
            authorization_records=authorization_records,
            dataset_root=root,
        )
    validate(registry, manifests, root, verify_files=True)
    records = (
        row
        for manifest in manifests
        if manifest.role == "operational"
        for row in manifest.samples
        if row.split == "train"
    )

    def eligible() -> Iterator[Sample]:
        for row in records:
            require_training(row.split, True, row.seed)
            yield row

    yield from batches(eligible(), size)


def save_normalizer(
    destination: Path,
    split_manifest: Path,
    registry: Registry,
    root: Path,
    records: Iterable[tuple[str, bool, int | None, str, float]],
    *,
    task_id: str | None = None,
    candidate_manifest_paths: Mapping[str, Path] | None = None,
    authorization_records: tuple[AuthorizationRecord, ...] = (),
) -> str:
    manifest = Manifest.model_validate_json(split_manifest.read_bytes())
    require_training_authorization(
        registry,
        manifest,
        task_id=task_id,
        candidate_manifest_paths=candidate_manifest_paths,
        authorization_records=authorization_records,
        dataset_root=root,
    )
    validate(registry, (manifest,), root, verify_files=True)
    if manifest.role != "operational":
        raise ValueError("expected operational training source")
    approved = {r.sample_id: (r.split, r.seed) for r in manifest.samples}
    seen: set[str] = set()

    def checked() -> Iterator[tuple[str, bool, int | None, str, float]]:
        for split, allowed, seed, ref, value in records:
            if approved.get(ref) != (split, seed) or ref in seen:
                raise ValueError("unknown, repeated or mismatched source row")
            seen.add(ref)
            yield split, allowed, seed, ref, value

    params = fit(checked())
    params["split_manifest_sha256"] = digest(split_manifest)
    params["manifest_version"] = manifest.manifest_version
    with destination.open("x", encoding="utf8") as stream:
        json.dump(params, stream, sort_keys=True)
    return digest(destination)


def standardized(value: float | None, parameters: Path, checksum: str) -> float | None:
    if digest(parameters) != checksum:
        raise ValueError("frozen parameters changed")
    params: dict[str, Any] = json.loads(parameters.read_bytes())
    mean, scale = float(params["mean"]), float(params["scale"])
    if (
        params["split"] != "train"
        or not math.isfinite(mean)
        or not math.isfinite(scale)
        or scale <= 0
    ):
        raise ValueError("invalid normalization configuration")
    return None if value is None else (value - mean) / scale
