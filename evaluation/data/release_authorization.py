"""Typed, checksum-bound human authorization for dataset training releases."""

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from agents.shared.domain import Id, Record
from evaluation.data.contracts import Manifest, Registry

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
UsageScope = Literal[
    "local_training",
    "cloud_training",
    "local_evaluation",
    "cloud_evaluation",
    "redistribution",
    "retention",
]
ReadinessStatus = Literal[
    "READY",
    "CONDITIONAL",
    "BLOCKED",
    "NOT_APPLICABLE",
]


class WiSARDProjectPermission(Record):
    """Owner attestation; the underlying publisher correspondence stays external."""

    project: Literal["SWARM-AID"]
    owner_identity: Id
    external_reference: Id
    confirmed_at: AwareDatetime
    publisher_permission_confirmed: Literal[True]
    imagery_and_annotations_covered: Literal[True]
    scope: Literal["local_noncommercial_training_and_evaluation"]
    general_dataset_licence_verified: Literal[False] = False

    @model_validator(mode="after")
    def confirmation_time(self) -> Self:
        if self.confirmed_at > datetime.now(UTC):
            raise ValueError("permission confirmation cannot be in the future")
        return self


class AuthorizationRecord(Record):
    schema_version: Literal["phase10i-authorization-1.0", "phase10i-authorization-1.1"]
    authorization_id: Id
    dataset_id: Id
    dataset_version: Id
    task_id: Id
    candidate_manifest_sha256: Digest
    training_manifest_sha256: Digest
    training_targets_manifest_sha256: Digest | None = None
    approved_usage_scopes: tuple[UsageScope, ...] = Field(min_length=1)
    governance_decision: Literal["approved", "rejected", "pending"]
    governance_evidence_refs: tuple[Id, ...] = ()
    privacy_decision: Literal["approved", "rejected", "pending"]
    cloud_processing_decision: Literal["approved", "rejected", "pending", "not_authorized"]
    redistribution_decision: Literal["approved", "rejected", "pending", "not_authorized"]
    human_review_evidence_refs: tuple[Id, ...] = ()
    authorizing_owner_identity: Id
    owner_authorization_ref: Id
    reviewer_identity: Id
    authorized_at: AwareDatetime
    decision: Literal["APPROVE", "REJECT"]
    decision_rationale: Annotated[str, Field(min_length=1)]
    restrictions: tuple[Annotated[str, Field(min_length=1)], ...]
    wisard_project_permission: WiSARDProjectPermission | None = None

    @model_validator(mode="after")
    def approval_is_explicit_and_complete(self) -> Self:
        permission = self.wisard_project_permission
        if permission is not None and (
            self.dataset_id != "wisard"
            or permission.owner_identity != self.authorizing_owner_identity
            or self.schema_version != "phase10i-authorization-1.1"
            or set(self.approved_usage_scopes) - {"local_training", "local_evaluation", "retention"}
            or self.cloud_processing_decision != "not_authorized"
            or self.redistribution_decision != "not_authorized"
        ):
            raise ValueError("project permission is restricted to owner-confirmed local WiSARD use")
        if self.schema_version == "phase10i-authorization-1.0":
            if self.training_targets_manifest_sha256 is not None:
                raise ValueError("Phase 10I authorization cannot bind a target manifest")
        elif self.training_targets_manifest_sha256 is None:
            raise ValueError("Phase 11 task authorization requires a target manifest checksum")
        if self.authorized_at > datetime.now(UTC):
            raise ValueError("authorization date cannot be in the future")
        if self.decision == "APPROVE" and (
            self.governance_decision != "approved"
            or self.privacy_decision != "approved"
            or "local_training" not in self.approved_usage_scopes
            or (
                "cloud_training" in self.approved_usage_scopes
                and self.cloud_processing_decision != "approved"
            )
            or (
                "redistribution" in self.approved_usage_scopes
                and self.redistribution_decision != "approved"
            )
            or not self.governance_evidence_refs
            or not self.human_review_evidence_refs
            or not self.owner_authorization_ref.strip()
            or not self.restrictions
        ):
            raise ValueError(
                "approval requires governance, privacy, review, owner and scope evidence"
            )
        return self


class AuthorizationBundle(Record):
    schema_version: Literal[
        "phase10i-authorization-bundle-1.0", "phase10i-authorization-bundle-1.1"
    ]
    records: tuple[AuthorizationRecord, ...]

    @model_validator(mode="after")
    def unique_authorizations(self) -> Self:
        ids = [record.authorization_id for record in self.records]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate authorization identifier")
        if self.schema_version == "phase10i-authorization-bundle-1.0" and any(
            record.schema_version != "phase10i-authorization-1.0" for record in self.records
        ):
            raise ValueError("Phase 10I authorization bundle cannot contain Phase 11 records")
        return self


class TaskReadiness(Record):
    schema_version: Literal["phase10i-task-readiness-1.0"]
    task_id: Id
    dataset_id: Id
    source_dataset_ids: tuple[Id, ...] = Field(min_length=1)
    status: ReadinessStatus
    blockers: tuple[str, ...] = ()
    blocker_categories: tuple[str, ...] = ()
    candidate_manifest_sha256: Digest | None = None
    authorization_id: Id | None = None
    approved_training_records: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def approval_matches_readiness(self) -> Self:
        if self.status == "READY" and (
            self.blockers
            or self.candidate_manifest_sha256 is None
            or self.authorization_id is None
            or not self.approved_training_records
        ):
            raise ValueError("READY requires no blockers and an approved nonempty release")
        if self.status in {"BLOCKED", "NOT_APPLICABLE"} and self.approved_training_records:
            raise ValueError("blocked or not-applicable tasks cannot contain training records")
        if self.status == "CONDITIONAL" and (not self.blockers or self.approved_training_records):
            raise ValueError("CONDITIONAL requires explicit conditions and no training records")
        return self


class TaskReadinessReport(Record):
    schema_version: Literal["phase10i-task-readiness-report-1.0"]
    tasks: tuple[TaskReadiness, ...]

    @model_validator(mode="after")
    def unique_tasks(self) -> Self:
        ids = [task.task_id for task in self.tasks]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate task readiness identifier")
        return self


def manifest_sha256(manifest: Manifest) -> str:
    canonical = json.dumps(
        manifest.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def require_training_authorization(
    registry: Registry,
    manifest: object,
    *,
    task_id: str | None,
    candidate_manifest_paths: Mapping[str, Path] | None,
    authorization_records: Iterable[AuthorizationRecord],
    dataset_root: Path,
    training_targets_manifest: Manifest | None = None,
    required_scope: UsageScope = "local_training",
) -> AuthorizationRecord:
    if not isinstance(manifest, Manifest):
        raise TypeError("candidate-only or untyped manifests cannot enter the training loader")
    dataset = next(
        (
            entry
            for entry in registry.datasets
            if (entry.dataset_id, entry.version) == (manifest.dataset_id, manifest.dataset_version)
        ),
        None,
    )
    if dataset is None or dataset.origin != manifest.origin:
        raise ValueError("unknown dataset version or origin mismatch")
    if task_id is None or not task_id.strip():
        raise ValueError("explicit task identifier is required for training authorization")
    if task_id not in dataset.tasks:
        raise ValueError("task is not registered for this dataset version")
    if candidate_manifest_paths is None or manifest.dataset_id not in candidate_manifest_paths:
        raise ValueError("candidate manifest path is required for checksum-bound authorization")
    if manifest.role != "operational":
        raise ValueError("training loader accepts only operational input manifests")
    if training_targets_manifest is not None and (
        training_targets_manifest.role != "training_targets"
        or (
            training_targets_manifest.dataset_id,
            training_targets_manifest.dataset_version,
            training_targets_manifest.origin,
        )
        != (manifest.dataset_id, manifest.dataset_version, manifest.origin)
    ):
        raise ValueError("training targets must match the input dataset, version and origin")

    candidate_path = candidate_manifest_paths[manifest.dataset_id].resolve()
    root = dataset_root.resolve()
    if not candidate_path.is_relative_to(root) or not candidate_path.is_file():
        raise ValueError("candidate manifest must be a readable file under the dataset root")
    candidate_sha256 = _file_sha256(candidate_path)
    from evaluation.data.model1_prep import CandidateManifest

    candidate = CandidateManifest.model_validate_json(candidate_path.read_bytes())
    if candidate.dataset_version is None or (
        candidate.dataset_id,
        candidate.dataset_version,
    ) != (manifest.dataset_id, manifest.dataset_version):
        raise ValueError("candidate dataset identity/version does not match training manifest")
    if candidate.training_approved:
        raise ValueError("candidate descriptor cannot grant training approval")
    records_relative = Path(candidate.records_file)
    if records_relative.is_absolute() or any(
        part in {"", ".", ".."} for part in records_relative.parts
    ):
        raise ValueError("candidate records path must remain within its descriptor directory")
    candidate_directory = candidate_path.parent.resolve()
    candidate_records_path = (candidate_directory / records_relative).resolve()
    if (
        not candidate_records_path.is_relative_to(candidate_directory)
        or not candidate_records_path.is_file()
    ):
        raise ValueError("candidate records must be readable under the descriptor directory")
    if _file_sha256(candidate_records_path) != candidate.records_sha256:
        raise ValueError("candidate records checksum mismatch")

    if (
        dataset.privacy_status != "approved"
        or dataset.verification != "verified"
    ):
        raise ValueError("dataset governance review incomplete")
    current_manifest_sha256 = manifest_sha256(manifest)
    scoped = [
        record
        for record in authorization_records
        if (record.dataset_id, record.dataset_version, record.task_id)
        == (manifest.dataset_id, manifest.dataset_version, task_id)
    ]
    if not scoped:
        raise ValueError("missing explicit dataset training authorization")
    exact = [
        record
        for record in scoped
        if record.candidate_manifest_sha256 == candidate_sha256
        and record.training_manifest_sha256 == current_manifest_sha256
    ]
    if not exact:
        raise ValueError(
            "authorization does not match the current candidate and training manifests"
        )
    if len(exact) != 1:
        raise ValueError("multiple matching authorization records are ambiguous")
    authorization = exact[0]
    if dataset.licence_status != "verified" and not (
        dataset.dataset_id == "wisard" and authorization.wisard_project_permission is not None
    ):
        raise ValueError("dataset licence or WiSARD project-specific permission required")
    if training_targets_manifest is not None:
        if (
            authorization.schema_version != "phase10i-authorization-1.1"
            or authorization.training_targets_manifest_sha256
            != manifest_sha256(training_targets_manifest)
        ):
            raise ValueError("authorization does not match the training targets manifest")
    elif authorization.schema_version == "phase10i-authorization-1.1":
        raise ValueError("task authorization requires its bound training targets manifest")
    if authorization.decision != "APPROVE":
        raise ValueError("dataset training authorization is not approved")
    if (
        authorization.governance_decision != "approved"
        or authorization.privacy_decision != "approved"
        or required_scope not in authorization.approved_usage_scopes
        or (
            "cloud_training" in authorization.approved_usage_scopes
            and authorization.cloud_processing_decision != "approved"
        )
        or (
            "redistribution" in authorization.approved_usage_scopes
            and authorization.redistribution_decision != "approved"
        )
        or not authorization.governance_evidence_refs
        or not authorization.human_review_evidence_refs
        or not authorization.owner_authorization_ref
    ):
        raise ValueError("authorization is missing mandatory governance or review evidence")
    if authorization.authorized_at > datetime.now(UTC):
        raise ValueError("authorization date cannot be in the future")
    return authorization


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
