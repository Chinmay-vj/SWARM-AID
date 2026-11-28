"""Collection-wide checks run before freezing a split or releasing files."""

import csv
import hashlib
import json
import wave
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from uuid import UUID
from xml.etree import ElementTree

from agents.shared.domain import Evidence
from evaluation.data.contracts import Annotation, Asset, Manifest, Registry, Sample
from evaluation.data.release_authorization import AuthorizationRecord, manifest_sha256

IMAGE = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
FORMATS = {
    "image": IMAGE,
    "thermal": IMAGE,
    "video": {".mp4", ".avi"},
    "audio": {".wav", ".flac"},
    "environment": {".csv", ".json", ".jsonl"},
    "gps": {".csv", ".json"},
    "imu": {".csv", ".json"},
    "text": {".txt", ".json"},
    "peer": {".json", ".jsonl"},
}
ANNOTATIONS = {
    "coco": {".json"},
    "yolo": {".txt"},
    "voc": {".xml"},
    "mask": {".png", ".tif", ".tiff"},
    "json": {".json"},
    "jsonl": {".jsonl"},
    "csv": {".csv"},
}


def inspect_asset(root: Path, asset: Asset, extensions: set[str], verify: bool) -> Path:
    path = (root / asset.path).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("asset escapes dataset root")
    if path.suffix.lower() not in extensions:
        raise ValueError("unsupported file format")
    if verify:
        if asset.availability != "available" or not path.is_file():
            raise ValueError("file unavailable")
        with path.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != asset.sha256:
                raise ValueError("file checksum mismatch")
    return path


def inspect_annotation(path: Path, ann: Annotation, sample: Sample) -> None:
    if ann.format == "mask":
        if path.suffix.lower() == ".png":
            with path.open("rb") as fp:
                header = fp.read(24)
            size = tuple(int.from_bytes(header[i : i + 4], "big") for i in (16, 20))
            if header[:8] != b"\x89PNG\r\n\x1a\n" or size != sample.dimensions:
                raise ValueError("segmentation mask dimension or signature mismatch")
        return
    if ann.format in {"json", "coco"}:
        data = json.loads(path.read_bytes())
        if ann.format == "coco" and (
            not isinstance(data, dict)
            or not all(
                isinstance(data.get(k), list) for k in ("images", "annotations", "categories")
            )
        ):
            raise ValueError("invalid COCO index")
    elif ann.format == "voc":
        if ElementTree.parse(path).getroot().tag != "annotation":
            raise ValueError("invalid VOC root")
    else:
        with path.open(encoding="utf-8-sig", newline="") as fp:
            if ann.format == "csv":
                if not next(csv.reader(fp, strict=True), []):
                    raise ValueError("missing CSV header")
            elif ann.format == "jsonl":
                for line in fp:
                    json.loads(line)
            else:
                for line in fp:
                    label, x, y, w, h = line.split()
                    cx, cy, width, height = map(float, (x, y, w, h))
                    if not (
                        label.isdecimal()
                        and 0 < width <= 1
                        and 0 < height <= 1
                        and width / 2 <= cx <= 1 - width / 2
                        and height / 2 <= cy <= 1 - height / 2
                    ):
                        raise ValueError("invalid normalized YOLO box")


def inspect_media(path: Path, sample: Sample) -> None:
    """Fast integrity checks in addition to the digest supplied by the source index."""
    suffix = path.suffix.lower()
    with path.open("rb") as stream:
        header = stream.read(32)
    if not header:
        raise ValueError("empty physical asset")
    signatures = {
        ".png": (b"\x89PNG\r\n\x1a\n",),
        ".jpg": (b"\xff\xd8\xff",),
        ".jpeg": (b"\xff\xd8\xff",),
        ".flac": (b"fLaC",),
        ".tif": (b"II*\x00", b"MM\x00*"),
        ".tiff": (b"II*\x00", b"MM\x00*"),
    }
    if suffix in signatures and not header.startswith(signatures[suffix]):
        raise ValueError("media signature mismatch")
    if suffix == ".png" and sample.dimensions:
        size = tuple(int.from_bytes(header[i : i + 4], "big") for i in (16, 20))
        if header[12:16] != b"IHDR" or size != sample.dimensions:
            raise ValueError("PNG dimensions mismatch")
    if suffix == ".wav":
        with wave.open(str(path)) as wav:
            if sample.sample_rate_hz and sample.sample_rate_hz != wav.getframerate():
                raise ValueError("WAV sample rate mismatch")


def validate(
    registry: Registry, manifests: Iterable[Manifest], root: Path, *, verify_files: bool = False,
    project_authorization: AuthorizationRecord | None = None,
    authorized_manifests: tuple[Manifest, ...] = (),
) -> dict[str, int]:
    """Pass every partition together. Release mode requires reviewed registry and local bytes."""
    entries = {(d.dataset_id, d.version): d for d in registry.datasets}
    permitted: dict[str, Manifest] = {}
    if project_authorization is not None:
        auth = AuthorizationRecord.model_validate(project_authorization.model_dump())
        if auth.dataset_id != "wisard" or auth.wisard_project_permission is None or auth.decision != "APPROVE":
            raise ValueError("invalid WiSARD project permission")
        for full in authorized_manifests:
            expected = (auth.training_manifest_sha256 if full.role == "operational"
                        else auth.training_targets_manifest_sha256)
            if (full.dataset_id != auth.dataset_id or full.dataset_version != auth.dataset_version
                    or manifest_sha256(full) != expected):
                raise ValueError("project permission manifest checksum mismatch")
            permitted[full.role] = full
    ids: set[tuple[str, str, str, str]] = set()
    groups: dict[tuple[str, ...], str] = {}
    pairs: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    counts: Counter[str] = Counter()
    operational_files: set[str] = set()
    target_files: set[str] = set()
    lineage: dict[tuple[UUID, UUID], Evidence] = {}
    verified_assets: dict[str, tuple[str, int, int]] = {}

    def checked_asset(asset: Asset, extensions: set[str]) -> Path:
        path = inspect_asset(root, asset, extensions, False)
        if verify_files:
            if not path.is_file():
                raise ValueError("file unavailable")
            stat = path.stat()
            identity = (asset.sha256, stat.st_size, stat.st_mtime_ns)
            if verified_assets.get(str(path)) != identity:
                inspect_asset(root, asset, extensions, True)
                after = path.stat()
                if (after.st_size, after.st_mtime_ns) != identity[1:]:
                    raise ValueError("asset changed during integrity verification")
                verified_assets[str(path)] = identity
            elif asset.availability != "available":
                raise ValueError("file unavailable")
        return path

    def group(key: tuple[str, ...], split: str) -> None:
        if groups.setdefault(key, split) != split:
            raise ValueError(f"cross-split {key[0]}")

    for manifest in manifests:
        dataset = entries.get((manifest.dataset_id, manifest.dataset_version))
        if dataset is None or dataset.origin != manifest.origin:
            raise ValueError("unknown dataset version or origin mismatch")
        bound = permitted.get(manifest.role)
        bound_samples = {s.sample_id: s for s in bound.samples} if bound else {}
        project_permitted = bound is not None and (
            manifest.dataset_id == bound.dataset_id and manifest.dataset_version == bound.dataset_version
            and all(bound_samples.get(s.sample_id) == s
                    for s in manifest.samples))
        if verify_files and (
            (dataset.licence_status != "verified" and not project_permitted)
            or dataset.privacy_status != "approved"
            or dataset.verification != "verified"
        ):
            raise ValueError("dataset governance review incomplete")
        for s in manifest.samples:
            key = (manifest.dataset_id, manifest.dataset_version, manifest.role, s.sample_id)
            if key in ids:
                raise ValueError("duplicate sample identifier")
            ids.add(key)
            if s.modality not in dataset.modalities:
                raise ValueError("modality outside registry")
            if dataset.licence and s.licence_ref != dataset.licence:
                raise ValueError("licence reference mismatch")
            group(("source", manifest.dataset_id, s.source_ref), s.split)
            group(("sample", manifest.dataset_id, s.sample_id), s.split)
            for field in ("sequence_id", "location_group", "event_id", "incident_id", "pair_id"):
                value = getattr(s, field)
                if value:
                    group((field, value), s.split)
            if s.scenario_id:
                group(("episode", s.scenario_id, str(s.seed)), s.split)
            if s.mission_id:
                group(("mission", str(s.mission_id)), s.split)
                for evidence in s.evidence:
                    ref = (s.mission_id, evidence.evidence_id)
                    if lineage.setdefault(ref, evidence) != evidence:
                        raise ValueError("conflicting evidence provenance for existing identifier")
                if s.observation_id:
                    group(("observation", str(s.mission_id), str(s.observation_id)), s.split)
            if s.pair_id:
                pairs[s.pair_id][s.modality].add(s.source_ref)
            if s.asset:
                if manifest.role == "operational" and any(
                    part.casefold() in {"evaluator", "annotations", "labels"}
                    for part in Path(s.asset.path).parts[:-1]
                ):
                    raise ValueError("operational asset in a restricted label directory")
                path = checked_asset(s.asset, FORMATS[s.modality])
                if s.modality == "environment" and s.source_rows:
                    for source_row in s.source_rows:
                        group(("sensor-row", str(path).casefold(), str(source_row)), s.split)
                else:
                    group(("content", s.asset.sha256), s.split)
                    group(("file", str(path).casefold()), s.split)
                if manifest.role == "operational":
                    operational_files.update((str(path).casefold(), s.asset.sha256))
                if verify_files:
                    inspect_media(path, s)
            if s.annotation:
                if any(
                    label not in dataset.label_definitions
                    for label in (*s.annotation.labels, *s.annotation.box_labels)
                ):
                    raise ValueError("undefined annotation label")
                path = checked_asset(s.annotation.asset, ANNOTATIONS[s.annotation.format])
                target_files.update((str(path).casefold(), s.annotation.asset.sha256))
                if verify_files:
                    inspect_annotation(path, s.annotation, s)
            counts[s.split] += 1
    if operational_files & target_files:
        raise ValueError("annotation file exposed as operational input")
    for members in pairs.values():
        if set(members) != {"image", "thermal"} or any(len(v) != 1 for v in members.values()):
            raise ValueError("pair requires exactly one RGB and one thermal source")
    return dict(sorted(counts.items()))
