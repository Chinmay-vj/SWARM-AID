import hashlib
import json
import wave
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from evaluation.data.contracts import Asset, Manifest, Registry, Storage
from evaluation.data.validation import validate

UID = "00000000-0000-0000-0000-000000000001"
DIGEST = hashlib.sha256(b"fixture").hexdigest()


def registry(**updates: Any) -> Registry:
    entry = {
        "dataset_id": "fixture",
        "name": "Fixture",
        "origin": "real",
        "version": "1",
        "licence": "fixture",
        "licence_status": "verified",
        "privacy_status": "approved",
        "verification": "verified",
        "privacy_considerations": "fixture only",
        "modalities": ["image", "thermal"],
        "annotation_types": ["mask"],
        "tasks": ["test"],
        "label_definitions": {"background": "fixture background"},
        "limitations": "test only",
    }
    return Registry.model_validate({"schema_version": "1.0", "datasets": [{**entry, **updates}]})


def row(key: str = "a", **updates: Any) -> dict[str, Any]:
    return dict(
        {
            "sample_id": key,
            "source_id": "camera",
            "source_ref": key,
            "sequence_id": key,
            "modality": "image",
            "representation": "physical",
            "split": "train",
            "licence_ref": "fixture",
            "asset": {"path": "raw/index.png", "sha256": DIGEST, "availability": "available"},
        },
        **updates,
    )


def manifest(*rows: dict[str, Any], **updates: Any) -> Manifest:
    return Manifest.model_validate(
        dict(
            {
                "schema_version": "1.0",
                "manifest_version": "1",
                "dataset_id": "fixture",
                "dataset_version": "1",
                "origin": "real",
                "role": "operational",
                "samples": rows,
            },
            **updates,
        )
    )


def symbolic(seed: int, split: str) -> dict[str, Any]:
    return row(
        str(seed),
        representation="symbolic",
        asset=None,
        mission_id=UID,
        scenario_id="flood",
        tick_ms=1,
        seed=seed,
        split=split,
        evidence=[
            {
                "evidence_id": UID,
                "origin": "d0",
                "captured_ms": 0,
                "modality": "image",
                "artifact_key": "opaque",
            }
        ],
    )


@pytest.mark.parametrize(
    "field", ["sequence_id", "location_group", "event_id", "incident_id", "pair_id", "source_ref"]
)
def test_related_group_never_crosses_manifests(tmp_path: Path, field: str) -> None:
    a = row(**{field: "group"})
    b = row("b", split="test", **{field: "group"})
    b["asset"]["sha256"] = "1" * 64
    with pytest.raises(ValueError, match="cross-split"):
        validate(registry(), [manifest(a), manifest(b)], tmp_path)


@pytest.mark.parametrize("seed", range(42, 47))
@pytest.mark.parametrize("split", ["train", "validation"])
def test_reserved_seeds(seed: int, split: str) -> None:
    with pytest.raises(ValidationError, match="reserved"):
        manifest(symbolic(seed, split), origin="synthetic")
    manifest(symbolic(seed, "test"), origin="synthetic")


def test_episode_group(tmp_path: Path) -> None:
    a, b = symbolic(5, "train"), symbolic(5, "validation")
    b.update(sample_id="b", source_ref="b", sequence_id="b")
    with pytest.raises(ValueError, match="cross-split episode"):
        validate(registry(origin="synthetic"), [manifest(a, b, origin="synthetic")], tmp_path)


def test_symbolic_evidence_and_missing_modality() -> None:
    s = symbolic(1, "train")
    s["missing_modalities"] = ["thermal"]
    manifest(s, origin="synthetic")
    change: dict[str, Any]
    for change in (
        {"evidence": []},
        {"missing_modalities": ["image"]},
        {"asset": row()["asset"]},
        {"tick_ms": -1},
    ):
        with pytest.raises(ValidationError):
            manifest({**s, **change}, origin="synthetic")


@pytest.mark.parametrize("path", ["A:/x", "../x", "raw/../x", "/x", "raw/x:other", "raw/CON"])
def test_unsafe_reference(path: str) -> None:
    with pytest.raises(ValidationError):
        Asset(path=path, sha256=DIGEST, availability="available")


def test_duplicate_ids_content_and_pair(tmp_path: Path) -> None:
    for second, error in [(row(), "duplicate sample"), (row("b", split="test"), "content")]:
        with pytest.raises(ValueError, match=error):
            validate(registry(), [manifest(row(), second)], tmp_path)
    a = row(pair_id="pair")
    with pytest.raises(ValueError, match="pair requires"):
        validate(registry(), [manifest(a)], tmp_path)
    assert validate(
        registry(), [manifest(a, row("b", pair_id="pair", modality="thermal"))], tmp_path
    ) == {"train": 2}


def test_integrity_and_governance(tmp_path: Path) -> None:
    m = manifest(row())
    with pytest.raises(ValueError, match="governance"):
        validate(registry(privacy_status="pending"), [m], tmp_path, verify_files=True)
    with pytest.raises(ValueError, match="unavailable"):
        validate(registry(), [m], tmp_path, verify_files=True)
    path = tmp_path / "raw/index.png"
    path.parent.mkdir()
    path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        validate(registry(), [m], tmp_path, verify_files=True)


def test_annotation_isolation_and_bounds() -> None:
    ann = {
        "format": "mask",
        "asset": row()["asset"],
        "labels": ["background"],
        "label_schema_version": "1",
        "label_source": "fixture",
        "review_status": "evaluator_truth",
    }
    s = row(dimensions=[3, 2], annotation=ann)
    manifest(s, role="evaluator")
    for role in ("operational", "training_targets"):
        with pytest.raises(ValidationError):
            manifest(s, role=role)
    change: dict[str, Any]
    for change in ({"boxes": [[0, 1, 3, 2]]}, {"labels": []}):
        with pytest.raises(ValidationError):
            manifest({**s, "annotation": {**ann, **change}}, role="evaluator")


def test_registry_storage_and_provenance() -> None:
    reg = registry().model_dump()
    reg["datasets"] *= 2
    with pytest.raises(ValidationError, match="duplicate dataset"):
        Registry.model_validate(reg)
    with pytest.raises(ValidationError):
        Storage(root=" ", schema_version="1.0")
    s = row()
    del s["source_ref"]
    with pytest.raises(ValidationError):
        manifest(s)
    with pytest.raises(ValidationError, match="licence"):
        registry(licence=None)


def test_wav_release_and_target_reference(tmp_path: Path) -> None:
    path = tmp_path / "clip.wav"
    with wave.open(str(path), "wb") as stream:
        stream.setparams((1, 1, 8000, 0, "NONE", "not compressed"))
        stream.writeframes(bytes([128] * 8))
    asset = {
        "path": "clip.wav",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "availability": "available",
    }
    s = row(asset=asset, modality="audio", sample_rate_hz=8000)
    reg = registry(modalities=["audio"])
    assert validate(reg, [manifest(s)], tmp_path, verify_files=True) == {"train": 1}
    with pytest.raises(ValueError, match="sample rate"):
        validate(reg, [manifest({**s, "sample_rate_hz": 16000})], tmp_path, verify_files=True)


def test_annotation_content_alias_is_rejected(tmp_path: Path) -> None:
    ann = {
        "asset": row()["asset"],
        "format": "mask",
        "labels": ["background"],
        "label_schema_version": "1",
        "label_source": "fixture",
        "review_status": "source",
    }
    target = manifest(row(annotation=ann, dimensions=[2, 2]), role="training_targets")
    with pytest.raises(ValueError, match="exposed"):
        validate(registry(), [target, manifest(row())], tmp_path)


def test_published_schemas_match_contracts() -> None:
    directory = Path(__file__).resolve().parents[2] / "configs/datasets/schemas"
    for model in (Registry, Manifest, Storage):
        schema = directory / f"{model.__name__.lower()}.v1.json"
        assert json.loads(schema.read_bytes()) == model.model_json_schema()


def test_forwarded_evidence_retains_content(tmp_path: Path) -> None:
    a, b = symbolic(1, "train"), symbolic(1, "train")
    b.update(sample_id="forward")
    reg = registry(origin="synthetic")
    assert validate(reg, [manifest(a, b, origin="synthetic")], tmp_path) == {"train": 2}
    b["evidence"][0]["origin"] = "d1"
    with pytest.raises(ValueError, match="provenance"):
        validate(reg, [manifest(a, b, origin="synthetic")], tmp_path)
