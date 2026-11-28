import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from evaluation.data.contracts import Manifest, Registry
from evaluation.data.model1_prep import CandidateManifest
from evaluation.data.release_authorization import (
    AuthorizationRecord,
    manifest_sha256,
)
from evaluation.data.training_partition import approved_training, save_normalizer


def _registry(**updates: object) -> Registry:
    dataset = {
        "dataset_id": "fixture",
        "name": "Fixture",
        "origin": "real",
        "version": "1",
        "licence": "terms",
        "licence_status": "verified",
        "privacy_status": "approved",
        "verification": "verified",
        "privacy_considerations": "synthetic test only",
        "modalities": ["image"],
        "annotation_types": ["boxes"],
        "tasks": ["fixture-classification"],
        "limitations": "synthetic test only",
    }
    return Registry.model_validate(
        {"schema_version": "1.0", "datasets": [{**dataset, **updates}]}
    )


def _manifest(root: Path) -> Manifest:
    image = root / "raw" / "image.jpg"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(b"\xff\xd8\xffsynthetic")
    return Manifest.model_validate(
        {
            "schema_version": "1.0",
            "manifest_version": "training-fixture-v1",
            "dataset_id": "fixture",
            "dataset_version": "1",
            "origin": "real",
            "role": "operational",
            "samples": [
                {
                    "sample_id": "sample-1",
                    "source_ref": "group-1",
                    "source_id": "camera-1",
                    "licence_ref": "terms",
                    "modality": "image",
                    "representation": "physical",
                    "split": "train",
                    "sequence_id": "group-1",
                    "asset": {
                        "path": "raw/image.jpg",
                        "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                        "availability": "available",
                    },
                }
            ],
        }
    )


def _candidate_manifest(root: Path) -> tuple[Path, str]:
    records_path = root / "manifests" / "candidate.jsonl"
    records_path.parent.mkdir(parents=True, exist_ok=True)
    records_path.write_bytes(b'{"sample_id":"sample-1"}\n')
    records_sha256 = hashlib.sha256(records_path.read_bytes()).hexdigest()
    path = root / "manifests" / "candidate.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    candidate = CandidateManifest(
        schema_version="phase10i-candidate-1.0",
        artifact_kind="candidate_only_not_approved_training_release",
        dataset_id="fixture",
        dataset_version="1",
        task="fixture-classification",
        records_file=records_path.name,
        records_sha256=records_sha256,
        candidate_records=1,
        partition_counts={"train": 1},
        target_distribution={"fixture": 1},
        partition_integrity="CANDIDATE_ONLY",
        source_index_sha256="b" * 64,
        raw_inventory_sha256="c" * 64,
    )
    path.write_text(candidate.model_dump_json(), encoding="utf-8")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _authorization(manifest: Manifest, candidate_sha256: str) -> AuthorizationRecord:
    return AuthorizationRecord(
        schema_version="phase10i-authorization-1.0",
        authorization_id="synthetic-auth-fixture",
        dataset_id="fixture",
        dataset_version="1",
        task_id="fixture-classification",
        candidate_manifest_sha256=candidate_sha256,
        training_manifest_sha256=manifest_sha256(manifest),
        approved_usage_scopes=("local_training",),
        governance_decision="approved",
        governance_evidence_refs=("synthetic-governance-fixture",),
        privacy_decision="approved",
        cloud_processing_decision="not_authorized",
        redistribution_decision="not_authorized",
        human_review_evidence_refs=("synthetic-review-fixture",),
        authorizing_owner_identity="synthetic-test-owner",
        owner_authorization_ref="synthetic-test-authorization",
        reviewer_identity="synthetic-test-reviewer",
        authorized_at=datetime.now(UTC),
        decision="APPROVE",
        decision_rationale="Synthetic unit-test approval only; not a real dataset decision.",
        restrictions=("Synthetic fixture only; no model training.",),
    )


def test_synthetic_authorized_release_loads_in_bounded_batches(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    candidate_path, candidate_sha256 = _candidate_manifest(tmp_path)
    auth = _authorization(manifest, candidate_sha256)

    batches = approved_training(
        _registry(),
        (manifest,),
        tmp_path,
        size=1,
        task_id="fixture-classification",
        candidate_manifest_paths={"fixture": candidate_path},
        authorization_records=(auth,),
    )

    assert [[sample.sample_id for sample in batch] for batch in batches] == [["sample-1"]]


def test_training_loader_requires_an_explicit_authorization(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    candidate_path, _ = _candidate_manifest(tmp_path)

    with pytest.raises(ValueError, match="missing explicit dataset training authorization"):
        next(
            approved_training(
                _registry(),
                (manifest,),
                tmp_path,
                task_id="fixture-classification",
                candidate_manifest_paths={"fixture": candidate_path},
            )
        )


def test_training_loader_rejects_candidate_only_manifest(tmp_path: Path) -> None:
    candidate = CandidateManifest(
        schema_version="phase10i-candidate-1.0",
        artifact_kind="candidate_only_not_approved_training_release",
        dataset_id="fixture",
        dataset_version="1",
        task="fixture-classification",
        records_file="records.jsonl",
        records_sha256="a" * 64,
        candidate_records=1,
        partition_counts={"train": 1},
        target_distribution={},
        partition_integrity="CANDIDATE_ONLY",
        source_index_sha256="b" * 64,
        raw_inventory_sha256="c" * 64,
    )

    with pytest.raises(TypeError, match="candidate-only"):
        next(approved_training(_registry(), (cast(Manifest, candidate),), tmp_path))


def test_training_loader_rejects_changed_candidate_manifest(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    candidate_path, candidate_sha256 = _candidate_manifest(tmp_path)
    auth = _authorization(manifest, candidate_sha256)
    candidate_path.write_text(candidate_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="does not match"):
        next(
            approved_training(
                _registry(),
                (manifest,),
                tmp_path,
                task_id="fixture-classification",
                candidate_manifest_paths={"fixture": candidate_path},
                authorization_records=(auth,),
            )
        )


def test_training_loader_rejects_changed_training_manifest(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    candidate_path, candidate_sha256 = _candidate_manifest(tmp_path)
    auth = _authorization(manifest, candidate_sha256)
    changed = manifest.model_copy(update={"manifest_version": "changed"})

    with pytest.raises(ValueError, match="does not match"):
        next(
            approved_training(
                _registry(),
                (changed,),
                tmp_path,
                task_id="fixture-classification",
                candidate_manifest_paths={"fixture": candidate_path},
                authorization_records=(auth,),
            )
        )


def test_training_loader_rejects_changed_candidate_records(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    candidate_path, candidate_sha256 = _candidate_manifest(tmp_path)
    auth = _authorization(manifest, candidate_sha256)
    (candidate_path.parent / "candidate.jsonl").write_bytes(b'{"sample_id":"changed"}\n')

    with pytest.raises(ValueError, match="candidate records checksum mismatch"):
        next(
            approved_training(
                _registry(),
                (manifest,),
                tmp_path,
                task_id="fixture-classification",
                candidate_manifest_paths={"fixture": candidate_path},
                authorization_records=(auth,),
            )
        )


def test_training_loader_rejects_pending_governance(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    candidate_path, candidate_sha256 = _candidate_manifest(tmp_path)
    auth = _authorization(manifest, candidate_sha256)
    pending = _registry(privacy_status="pending")

    with pytest.raises(ValueError, match="governance"):
        next(
            approved_training(
                pending,
                (manifest,),
                tmp_path,
                task_id="fixture-classification",
                candidate_manifest_paths={"fixture": candidate_path},
                authorization_records=(auth,),
            )
        )


def test_training_loader_rejects_rejected_wrong_scope_authorization(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    candidate_path, candidate_sha256 = _candidate_manifest(tmp_path)
    rejected = _authorization(manifest, candidate_sha256).model_copy(
        update={
            "decision": "REJECT",
            "approved_usage_scopes": ("local_evaluation",),
        }
    )

    with pytest.raises(ValueError, match="not approved"):
        next(
            approved_training(
                _registry(),
                (manifest,),
                tmp_path,
                task_id="fixture-classification",
                candidate_manifest_paths={"fixture": candidate_path},
                authorization_records=(rejected,),
            )
        )


def test_approval_record_requires_human_review_evidence(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    _, candidate_sha256 = _candidate_manifest(tmp_path)
    payload = _authorization(manifest, candidate_sha256).model_dump()
    payload["human_review_evidence_refs"] = ()

    with pytest.raises(ValidationError, match="approval requires"):
        AuthorizationRecord.model_validate(payload)


def test_normalizer_fitting_requires_authorization_before_writing(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    manifest_path = tmp_path / "training-manifest.json"
    manifest_path.write_text(manifest.model_dump_json(), encoding="utf-8")
    destination = tmp_path / "normalizer.json"

    with pytest.raises(ValueError, match="candidate manifest path is required"):
        save_normalizer(
            destination,
            manifest_path,
            _registry(),
            tmp_path,
            (("train", True, None, "sample-1", 1.0),),
            task_id="fixture-classification",
        )

    assert not destination.exists()


def test_training_loader_verifies_media_checksums_after_authorization(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    candidate_path, candidate_sha256 = _candidate_manifest(tmp_path)
    auth = _authorization(manifest, candidate_sha256)
    (tmp_path / "raw" / "image.jpg").write_bytes(b"\xff\xd8\xffchanged")

    with pytest.raises(ValueError, match="checksum mismatch"):
        next(
            approved_training(
                _registry(),
                (manifest,),
                tmp_path,
                task_id="fixture-classification",
                candidate_manifest_paths={"fixture": candidate_path},
                authorization_records=(auth,),
            )
        )


def test_training_loader_protects_reserved_evaluation_seeds(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    sample = manifest.samples[0].model_copy(update={"seed": 42})
    protected = manifest.model_copy(update={"samples": (sample,)})
    candidate_path, candidate_sha256 = _candidate_manifest(tmp_path)
    auth = _authorization(protected, candidate_sha256)

    with pytest.raises(ValueError, match="protected seeds"):
        next(
            approved_training(
                _registry(),
                (protected,),
                tmp_path,
                task_id="fixture-classification",
                candidate_manifest_paths={"fixture": candidate_path},
                authorization_records=(auth,),
            )
        )


def test_training_loader_rejects_cross_split_group_assignments(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    test_sample = manifest.samples[0].model_copy(
        update={
            "sample_id": "sample-2",
            "source_ref": "group-2",
            "split": "test",
        }
    )
    conflicting = manifest.model_copy(
        update={"samples": (manifest.samples[0], test_sample)}
    )
    candidate_path, candidate_sha256 = _candidate_manifest(tmp_path)
    auth = _authorization(conflicting, candidate_sha256)

    with pytest.raises(ValueError, match="cross-split"):
        next(
            approved_training(
                _registry(),
                (conflicting,),
                tmp_path,
                task_id="fixture-classification",
                candidate_manifest_paths={"fixture": candidate_path},
                authorization_records=(auth,),
            )
        )


def test_external_permission_is_wisard_only(tmp_path: Path) -> None:
    from evaluation.data.release_authorization import WiSARDProjectPermission

    manifest = _manifest(tmp_path)
    _, checksum = _candidate_manifest(tmp_path)
    record = _authorization(manifest, checksum)
    permission = WiSARDProjectPermission(
        project="SWARM-AID", owner_identity=record.authorizing_owner_identity,
        external_reference="Externally held publisher reply; synthetic fixture",
        confirmed_at=datetime.now(UTC), publisher_permission_confirmed=True,
        imagery_and_annotations_covered=True,
        scope="local_noncommercial_training_and_evaluation")
    payload = record.model_dump()
    payload.update(schema_version="phase10i-authorization-1.1",
                   training_targets_manifest_sha256="a" * 64,
                   wisard_project_permission=permission.model_dump(),
                   cloud_processing_decision="not_authorized",
                   redistribution_decision="not_authorized")
    with pytest.raises(ValidationError, match="restricted"):
        AuthorizationRecord.model_validate(payload)
    payload["dataset_id"] = "wisard"
    accepted = AuthorizationRecord.model_validate(payload)
    assert accepted.wisard_project_permission is not None
    assert not accepted.wisard_project_permission.general_dataset_licence_verified
    payload["approved_usage_scopes"] = ["local_training", "cloud_training"]
    with pytest.raises(ValidationError, match="restricted"):
        AuthorizationRecord.model_validate(payload)
    payload["approved_usage_scopes"] = ["local_training"]
    payload["authorizing_owner_identity"] = "different-owner"
    with pytest.raises(ValidationError, match="restricted"):
        AuthorizationRecord.model_validate(payload)
