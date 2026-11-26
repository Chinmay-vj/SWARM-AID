# Phase 11G: ESC-50 successor release preparation

2026-11-26, PC2. **Training readiness: NO-GO.** Release metadata is prepared;
rights/privacy clearance, exact task authorization and explicit training-start
approval remain pending. No training, audio decoding, dataset rehashing,
downloads, repeated publisher checks, historical-release edits, commits or
pushes occurred.

## Completed

- Validated `runs/phase11g1/owner_response_v1.json`: correct proposal and
  publisher commit, identified owner, timezone-aware nonfuture timestamp,
  successor scope and **single-reviewer protocol approved**. Local research
  training/evaluation scope is approved in principle, but the same record
  explicitly says rights/privacy `PENDING` and `training_authorized=false`.
  This is an owner statement, not cryptographic identity verification.
- Reused the supplied confirmation that README, LICENSE and esc50.csv match
  publisher commit `33c8ce9eb2cf0b1c2f8bcf322eb349b6be34dbb6`. Did not repeat it.
  Audio remains bound to the Phase 10J local ledger; exact publisher audio
  revision was not independently compared, as acknowledged by the owner.
- Preserved the original 20 reviews byte-for-byte (18 ACCEPT, two REJECT) and
  verified their clip IDs, metadata and existing hashes. Added the six exact
  user-reported decisions separately: five ACCEPT, one REJECT. Combined total:
  **26 reviewed, 23 ACCEPT, three REJECT**. Missing identity, timestamp,
  rationale and reviewer-evidence fields for the six remain null/empty. Their
  provenance is the user's explicit message; no independent reviews invented.
- Excluded 60 CC-Sampling+ clips, unmatched `5-141683-A-35.wav`, and rejected
  `3-129264-A-9.wav`, `3-155556-A-31.wav`, `1-45645-A-31.wav`: **64 distinct
  exclusions from the 1,991-row candidate**. Earlier nine recording-leakage
  exclusions remain in force. No raw files were deleted or modified.
- Generated versioned candidate, registry, operational and target manifests
  using existing `CandidateManifest`, `CandidateRow`, `Registry`, `Manifest`,
  `Sample`, `Annotation`, validation and canonical authorization-hash utilities.
  Labels remain source metadata, with separate review evidence; the manifests
  do not mark all clips as human-reviewed.

## Final candidate counts and checks

| Partition | Official folds | Clips | Categories |
|---|---|---:|---:|
| Training | 1-3 | 1,134 | 50 |
| Validation | 4 | 397 | 50 |
| Reserved testing | 5 | 396 | 50 |
| Total | 1-5 | **1,927** | **50** |

Recording groups and inherited content hashes cross **zero** partitions.
Metadata joins, unique sample IDs, input/target lineage, class membership and
asset path existence passed. `validate(..., verify_files=False)` passed for
each manifest and the combined collection. This deliberately does not claim
fresh raw-byte verification. Reused all 1,927 audio hashes from prior evidence;
only new artifact/review-file digests were calculated.

Retained attribution tags: 859 CC0, 898 CC-BY, 170 CC-BY-NC. These are source
tags, not automated permission determinations. The owner still needs to clear
the retained material under the dataset-wide noncommercial terms, clip terms,
attribution obligations, privacy and retention conditions.

## Generated files

Dataset version: `esc50-33c8ce9-pc2-successor-v1`.
Release directory: **`D:/SWARM-AID-DATA/manifests/phase11g-esc50-v1/`**.
Prepared staging copy: `D:/SWARM-AID/runs/phase11g2/phase11g-esc50-v1/`.
Historical releases and the original owner/review files remain unchanged.

| Files within the release | Purpose |
|---|---|
| `candidate.json`, `candidate_records.jsonl` | Schema-valid, explicitly unapproved successor candidate and inherited audio hashes |
| `registry.json`, `operational.json`, `targets.json` | Versioned task/taxonomy, scoped inputs and source labels; governance stays pending |
| `exclusions.json`, `class_coverage.json`, `provenance.json`, `validation.json`, `checksums.json` | Exclusion reasons, per-class counts, lineage/limitations and new-artifact integrity |
| `reviews/initial_20_original.json`, `reviews/owner_response_original.json` | Exact original bytes, not rewritten reviews |
| `reviews/additional_six_user_reported.json`, `reviews/review_ledger_v1.json` | Six supplied decisions and complete provenance-preserving ledger |
| `rights_privacy_review.template.json` | Concise actual-owner review record; all clearance decisions remain unset |
| `authorization_requirements.json`, `authorization_bundle.json` | Exact schema 1.1 bindings/required fields and an **empty** schema 1.1 bundle |
| `training_config.json`, `training_start.template.json` | Proposed initial settings and blank start approval bound to release/configuration hashes |

Preparation script: `runs/phase11g2/prepare_release.py` (one-shot; refuses an
existing staging directory). Launcher: `runs/phase11g2/launch_esc50.py`.
Neither changes core runtime code or default simulation behavior.

## Exact remaining owner actions

1. Copy `rights_privacy_review.template.json` to
   `rights_privacy_review.completed.json` in the release directory. Complete the
   actual decisions on retained rights, privacy, retention, accepted source
   snapshot limitations and sufficiency of the approved single-reviewer
   evidence. Record reviewer identity, actual decision time with timezone,
   evidence references, rationale and restrictions. Confirm the `reviewer1`
   alias/evidence provenance as appropriate. **Do not reconstruct missing old
   timestamps or commission a second reviewer solely because the obsolete
   proposal had two slots.** Reject/defer unresolved items instead of approving
   them automatically. Cloud processing and redistribution remain unauthorized.
2. Return the completed clearance for finalization of this newly prepared
   registry. A responsible steward may mark licence/privacy/source verification
   cleared only when supported by that decision and its evidence. The historical
   active registry and frozen Phase 10 records must not be edited. This narrow
   successor does not assert complete historical native-release verification.
3. Review `authorization_requirements.json` and issue a genuine
   `phase10i-authorization-1.1` record in a
   `phase10i-authorization-bundle-1.1` bundle, with dataset/version/task exactly
   as supplied. Bind its candidate SHA-256 and **canonical** operational/target
   hashes, include both `local_training` and `local_evaluation`, approved
   governance/privacy decisions, owner/reviewer identities, actual timestamp,
   review and governance evidence refs, rationale and restrictions. Raw
   `Get-FileHash` values for input/target JSON are not the canonical manifest
   digests. Use the prepared requirements. Any changed candidate/target/split
   requires new bindings and approval; do not reuse stale hashes.
4. Separately copy `training_start.template.json` to
   `training_start.approved.json`. Only if you intend training to start, set
   `decision` to `APPROVE_TRAINING_START`, give the matching `authorization_id`,
   owner identity, actual timezone-aware `approved_at` and rationale. Preserve
   the exact release and configuration hashes. The launcher compares these
   against the authorized release. Refresh the new package checksum inventory
   after finalization; preserve the prepared provenance and decisions.

No formal approval is requested for material not yet reviewed. The current
empty bundle and pending registry must remain blocked until those actions are
complete. Scope approval alone is insufficient. Missing review timestamps are
recorded limitations, not invitations to invent evidence.

## Exact PowerShell commands

From `D:/SWARM-AID`, this default mode checks authorization and metadata only.
It performs no audio hashing, decoding, optimization or training:

```powershell
.\.venv\Scripts\python.exe runs\phase11g2\launch_esc50.py --release D:\SWARM-AID-DATA\manifests\phase11g-esc50-v1
```

It is expected to reject the currently pending release. After all four owner
steps are genuinely completed, use this explicit launch (not executed here):

```powershell
$env:TEMP = 'D:\SWARM-AID\runs\phase11g2\tmp'
$env:TMP = $env:TEMP
$env:TORCH_HOME = 'D:\SWARM-AID\runs\phase11g2\torch-cache'
New-Item -ItemType Directory -Force -Path $env:TEMP, $env:TORCH_HOME | Out-Null
.\.venv\Scripts\python.exe runs\phase11g2\launch_esc50.py --release D:\SWARM-AID-DATA\manifests\phase11g-esc50-v1 --start-approval D:\SWARM-AID-DATA\manifests\phase11g-esc50-v1\training_start.approved.json --execute
if ($LASTEXITCODE -ne 0) { throw 'Launch rejected or failed; inspect the error before retrying' }
```

Settings: random-initialized 50-class audio model, CUDA BF16, batch 2,
accumulation 2, zero workers, AdamW 0.001 / weight decay 0.0001, 30 epochs
maximum, patience 5, seed 2025, 8 GiB allocator budget, epoch checkpoints,
validation macro-F1 selection. No pretrained downloads or test-fold fitting.
Checkpoint/run outputs use new D-drive `phase11g-esc50/run-001` directories;
existing outputs are refused. Future authorized dataset loaders retain their
mandatory file-integrity checks; those checks were not invoked now and must
not be disabled to save launch time. Checkpoint resume remains available through
the framework but is not silently attempted by this first-run launcher.

## Focused verification

- **17 passed, seven deselected, one existing Starlette/httpx warning**, 1.51s:
  authorization and task-loader focused tests.
- Ruff passed; strict MyPy passed for 182 repository source files.
- Candidate/manifest schema validation, new artifact hashes, 20-review byte
  preservation, six-record missing-provenance assertions, counts and canonical
  authorization digest comparisons passed. Launcher syntax compiled.
- Installed package hashes were verified after copying to the dataset root.
  The actual launcher in default check-only mode rejected it with
  `dataset governance review incomplete` before Torch import or audio access,
  as required. No training was invoked.

No Phase 10/11A-F audits or full regression/GPU profiles were repeated. Current
checks establish release metadata consistency and closed gates, not legal
clearance, full audio-label accuracy or real-world performance.
