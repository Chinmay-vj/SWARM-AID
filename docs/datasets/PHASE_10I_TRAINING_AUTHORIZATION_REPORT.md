# Phase 10I training authorization safeguards

**Current state: no authorization records; no training release.** The
machine-readable bundle at
`D:\SWARM-AID-DATA\manifests\phase10i-d1-e1-v2\authorization_bundle.json`
contains zero records. Candidate manifests remain explicitly
`training_approved=false`.

## Authorization contract

`evaluation/data/release_authorization.py` adds typed authorization,
bundle, and task-readiness records. An approval binds:

- dataset ID, exact version, and registered task;
- SHA-256 of the candidate descriptor and canonical training manifest;
- explicit usage scope, including separate cloud and redistribution
  decisions when requested;
- approved governance and privacy decisions with evidence references;
- human-review evidence, authorizing owner identity/reference, and reviewer;
- timestamp, rationale, and explicit restrictions.

`evaluation/data/training_partition.py` requires exactly one matching
approval before `approved_training` or `save_normalizer` proceeds. It rejects
candidate-only/untyped manifests, unknown versions/origins, unregistered
tasks, non-operational manifests, candidate descriptors outside the data
root, stale descriptor/records checksums, pending registry governance,
missing/multiple/stale authorization records, rejected or wrong-scope
decisions, and missing review/owner evidence. Collection-wide validation
continues to verify local asset checksums and group/split constraints.
Training eligibility still rejects non-training rows and reserved seeds
42-46.

The human-review and pipeline-development loaders are not promoted to
training loaders. No approval requirement was weakened. The record is a
typed local authorization evidence object, not a cryptographic signature or
identity-provider attestation; authorized owners remain responsible for
authentic evidence and secure handling.

## Verification

Synthetic-only tests exercise missing authorization, candidate-only inputs,
candidate and asset checksum changes, training-manifest changes, pending
governance, rejected/wrong-scope approval, missing review evidence,
normalizer gating, reserved seed rejection, and cross-split grouping. These
fixtures do not authorize any actual dataset.

No real dataset currently satisfies the required conditions. Do not add a
real authorization until owner/legal/privacy evidence and the independent
review decisions are complete and the exact release and training manifest
have been frozen.
