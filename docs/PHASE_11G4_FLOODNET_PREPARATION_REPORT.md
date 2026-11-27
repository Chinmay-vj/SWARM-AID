# Phase 11G-4C/G4D: FloodNet preparation on PC2

**Current execution readiness: NO-GO pending separate training-start approval.**
On 2026-11-27 chinmay explicitly cleared consolidated governance items 1-5 as
owner and reviewer. Typed authorization `floodnet-pc2-chinmay-20261127T090921Z`
now binds the unchanged candidate, input and target digests. Mandatory readiness
passed (exit 0, `authorized_metadata_only`, `training_started=False`), recorded in
`runs/phase11g4/authorized-readiness.log`. Source byte integrity remains enforced
at an authorized processing launch; this check is not a new raw-data audit.
Approved risks/restrictions, owner statement and evidence digests are saved in
the deployed release, including `rights_privacy_review.approved.json`,
`privacy_assessment.json`, `owner_governance_approval.json` and
`governance_evidence_digests.json`. Retention is project completion plus 12 months.
Exact upstream archive identity and geographic/flight independence remain
unverified. The schema's registry verification status is scoped to the accepted
local successor and existing evidence, not upstream archive verification.
Original draft licence identifiers in unchanged manifests resolve through the
approved registry/review; they do not indicate a remaining clearance blocker.
Prior pending-clearance descriptions below are historical preparation records,
superseded by this update. No completed tests, reviews or profiling were repeated.
The separate training-start template is bound but remains unapproved.
No actual FloodNet training,
raw-data hashing, image decoding, test evaluation, downloads, commits or pushes
were performed in this preparation session.

## Release and preserved evidence

Resume check on 2026-11-27 confirmed the clearance template remains pending and
the deployed release has no newer approved clearance file. Focused tests rerun:
43 passed, one existing Starlette warning, 34.25 seconds. Ruff and strict mypy
passed for the same six files. Metadata-only readiness again exited 1 with
`dataset governance review incomplete`. Prior synthetic smoke and GPU benchmark
artifacts were inspected and reused. No real-data processing or training occurred.
The consolidated source/rights/privacy decision remains with the owner.

Prepared draft: `D:\SWARM-AID-DATA\manifests\phase11g4-floodnet-v1`.
Local staging copy: `D:\SWARM-AID\runs\phase11g4\phase11g4-floodnet-v1`.
This is a separately governed successor, not recovery or certification of the
incomplete historical release. The draft is not an authorized frozen release.

| Partition | Pairs | Use |
|---|---:|---|
| Training | 1,445 | Proposed training and normalization |
| Validation | 449 | Proposed selection and validation |
| Reserved test | 448 | Metadata only; untouched for development |
| Total | 2,342 | Ten source classes |

The user explicitly approved excluding validation `10169.jpg/10169_lab.png`,
the publisher-partition baseline, reduced single-reviewer protocol and RGB-only
EXIF corrections. Their second response supplied the identity **chinmay** only;
it did not approve source identity, licence, privacy or processing permissions.
`scope_approval.json` records this distinction without inventing a review timestamp.

The original 15 annotation decisions (13 ACCEPT, one REJECT, one
CORRECTION_REQUIRED) are preserved. All 45 existing accepted corrected overlays
(30 train, 15 validation), including `7369`, are reused with original evidence.
RGB is EXIF-transposed before resizing; masks are never transposed. Raw files
and historical releases remain unchanged. Source-image identities are checked
for partition separation; they are **not** geographic or flight-group identities.
Geographic/flight independence remains unestablished and is not claimed.

The existing index and verified ledger supply paths, splits and hashes. Metadata
validation passed; no new full inventory or raw hash audit was run. Local
`DATASET-VERSION-NOTE-v1.0.txt` explicitly supports numeric mask IDs 0–9.
The [publisher README](https://github.com/BinaLab/FloodNet-Supervised_v1.0)
lists the ten categories and links [CDLA-Permissive-1.0](https://cdla.io/permissive-1-0/).
These establish supporting evidence, not exact local publisher snapshot identity
or automatic owner clearance. No exact upstream snapshot is asserted.

| Raw ID | Label | Model index (alphabetical) |
|---:|---|---:|
| 0 | background | 0 |
| 1 | building_flooded | 1 |
| 2 | building_non_flooded | 2 |
| 3 | road_flooded | 5 |
| 4 | road_non_flooded | 6 |
| 5 | water | 9 |
| 6 | tree | 7 |
| 7 | vehicle | 8 |
| 8 | pool | 4 |
| 9 | grass | 3 |

Training class pixel frequencies reuse the historical full audit because training
membership is unchanged: grass 55.7106%, tree 17.4634%, water 11.1206%,
road_non_flooded 5.4300%, building_non_flooded 3.2171%, road_flooded 3.1421%,
building_flooded 1.7896%, background 1.7354%, pool 0.2079%, vehicle 0.1833%.
All ten classes have training support. Revised validation pixel frequencies and
rare-class performance are not fabricated; authorized streaming validation will
report them. Manifest label lists describe the allowable taxonomy, not a claim
that every image contains every class. No automatic weighting or oversampling.

## Artifacts and implementation

The draft contains `candidate.json`, `candidate_records.jsonl`, `registry.json`,
`operational.json`, `targets.json`, `exclusion_overlay.json`, `taxonomy.json`,
`class_frequencies.json`, `provenance.json`, `scope_approval.json`, `review/`,
`validation.json`, `checksums.json`, `rights_privacy_review.template.json`,
`authorization_requirements.json`, `authorization_bundle.json`,
`training_config.json`, `objective.json` and `training_start.template.json`.
The authorization bundle has **zero records**; it grants no permission.
Templates contain unanswered decisions, not approvals.

Reusable changes:

- `evaluation/model1/data.py`: vectorized strict mask mapping, including rejection
  of unknown IDs before downsampling; explicit development-only train/validation
  access; session-bound integrity reuse after successful verification.
- `evaluation/data/validation.py`: deduplicates identical path/hash/stat verification
  within one validation call. New executions still verify required source bytes;
  this is not a persistent integrity waiver. Session reuse detects size/mtime
  changes and assumes a non-adversarial local filesystem.
- `evaluation/model1/segmentation_cache.py`: authorized train/validation-only,
  uint8 memory-mapped RGB and mask arrays, atomic installation, completion marker,
  shape/dtype/hash checks and changed-file detection. Keys bind manifests,
  candidate, authorization, source identities, code, resolution, EXIF policy and
  taxonomy. Incompatible bindings create a different cache; corrupted existing
  caches fail closed. Stochastic joint augmentation stays outside the cache.
- `evaluation/model1/segmentation.py`: FP32 cross-entropy plus multiclass soft Dice,
  with ignored pixels excluded; streaming confusion matrix and sufficient
  statistics, without retaining full-partition logits.
- `evaluation/model1/training.py`: opt-in Dice weight (default remains zero),
  one segmentation validation forward per batch, live flushed losses, metrics,
  learning rate, memory, timing, checkpoint and stopping information.
- `tests/unit/test_floodnet_preparation.py`: synthetic regression coverage.

The proposed objective is CE + 1.0 Dice, background included, ignore ID 255,
epsilon 1e-6. Soft Dice averages target-supported classes. Validation loss uses
whole-partition sufficient statistics. Hard IoU/Dice average classes with nonzero
prediction/target union; absent-both classes are flagged and excluded from macro
averages. Per-class pixels/fractions, IoU/Dice and flattened confusion entries
are saved, allowing rare-class interpretation without batch-average bias.

Local reproducible helpers (under ignored `runs/`, preserve separately if moving
the workspace): `prepare_floodnet_release.py`, `floodnet.py`,
`profile_preprocessing.py`, all in `D:\SWARM-AID\runs\phase11g4`.
The launcher reuses the existing model, fit, authorization and checkpoint APIs.

## Verification and measurements

Focused pytest: **43 passed**, one existing Starlette/httpx deprecation warning,
5.39 seconds. Suites: `test_floodnet_preparation.py`, `test_phase11_pc2.py`,
`test_phase11_model1.py`, `test_release_authorization.py`.
Ruff passed and strict mypy passed for the six changed/new implementation and
test files above. Full historical audits and unrelated suites were not repeated.

Tests cover EXIF-without-mask-rotation, strict source labels, cache reuse and
invalidation, corruption rejection, train-only normalization, reserved-test
isolation even with test files absent, stochastic joint flips, CE/Dice arithmetic,
streaming versus combined statistics, one-forward validation, live logging and
exact epoch resume on CPU and BF16 CUDA for the synthetic segmentation fixture.
The actual randomly initialized DeepLabV3/MobileNetV3-Large completed a 512-square
BF16 synthetic fit/checkpoint smoke test. Exact resume of a full FloodNet model
run is not claimed; the segmentation fixture and existing framework resume tests
passed. Final smoke has no deterministic-loss warning.

Final evidence: `runs/phase11g4/smoke-final.log`, `smoke-final/smoke.json`,
`profile-final.log`, `profile-final/summary.json`,
`preprocessing-profile/profile.json`, `blocked-readiness-final.log`.

GPU: NVIDIA RTX PRO 4500 Blackwell, 31.86 GiB reported, BF16 supported,
PyTorch 2.11.0+cu128. Each fresh profiling process used two warm-up and three
measured optimizer steps, one streaming validation batch and a checkpoint save.

| Batch | Samples/s | Forward s | Backward+step s | Peak allocated GiB | Peak reserved GiB | Validation batch s | Save s |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 8 | 84.55 | 0.0417 | 0.0529 | 1.92 | 2.03 | 0.0514 | 1.18 |
| 16 | 98.10 | 0.0697 | 0.0934 | 3.67 | 3.87 | 0.0657 | 1.28 |
| 32 | 95.45 | 0.1591 | 0.1762 | 7.15 | 7.31 | 0.1624 | 1.11 |

Recommend **batch 16, BF16, 512 square**, zero workers, conservative allocator cap
of at most half VRAM and 16 GiB. Other settings: random initialization, ten
classes, AdamW 0.001, weight decay 0.0001, seed 2025, maximum 50 epochs,
patience 10, checkpoint every epoch, selection by validation macro IoU.
Short synthetic profiles measure throughput, not accuracy or sustained training.

Synthetic 4000x3000 random JPEG/PNG preprocessing measured RGB decode/EXIF/resize
0.140–0.144 s and mask decode/strict check/resize/remap 0.095–0.103 s per pair.
Normalization reduction measured 0.00437 s/image. These imply roughly 7.4–7.8
minutes to transform 1,894 development pairs **if** real source sizes/compression
and storage behave similarly. This excludes mandatory initial integrity checks,
cache writes/checksums, and launch overhead; actual preprocessing is unmeasured
until owner clearance. Compact cache payload is about 1.85 GiB, plus headers.

Batch-16 GPU arithmetic suggests 14.7 s training + 1.9 s validation + 1.3 s save,
about 18 s/epoch or 15 minutes/50 epochs, **excluding** loader/augmentation/H2D,
startup, cache creation/integrity, final-batch differences and real storage effects.
This is a component-based estimate, not an end-to-end promise. The final actual
fit smoke separately measured loader wait 0.004 s, H2D 0.006 s, forward/loss
0.512 s, backward/optimizer 0.336 s, validation 0.042 s and checkpoint 2.216 s
across two small batches. Real authorization/dataset/cache initialization stages
are instrumented but deliberately not benchmarked through an unapproved release.

Actual live log excerpt:

```text
[batch 2/2] epoch=1/1 loss=3.302924 lr=0.001 elapsed_s=0.9 eta_s=0.0 allocated_MiB=137.9 reserved_MiB=628.0 peak_MiB=600.7 utilization=unavailable
[epoch 1/1] train_loss=3.302924 val_loss=3.204803 val_mIoU=0.010006 val_mDice=0.018192 pixel_accuracy=0.100060 epoch_s=3.18 ... best_epoch=1 best_score=0.010006
[final] reason=maximum_epochs best_epoch=1 best_score=0.010006 duration_s=3.19 ...
```

GPU utilization is explicitly unavailable; it is not guessed. Epoch logs contain
checkpoint paths, patience state and stage durations; final output names report
and best-checkpoint locations. Synthetic metrics are not FloodNet results.

## Minimum owner actions and authorization boundary

1. Copy `rights_privacy_review.template.json` to
   `rights_privacy_review.approved.json` **only when actually reviewed**. Chinmay
   must supply the real reviewer, timezone-aware review time and evidence refs;
   answer each source snapshot, numeric taxonomy, CDLA terms, privacy, local
   preprocessing, training and evaluation field. Specify retention restrictions.
   If exact publisher identity cannot be established, explicitly decide whether
   the ledger-defined local snapshot is acceptable for this limited baseline,
   recording that limitation; do not assert an unverified upstream commit.
   If any decision remains pending/rejected, leave NO-GO. No repeated overlay
   reviews or request for PC1 is necessary.
2. After those decisions, finalize the **draft successor's** registry governance
   fields (`licence_status=verified`, `privacy_status=approved`,
   `verification=verified`) with genuine evidence refs. Do not change historical
   releases or infer these values merely from the owner's name. Have the clearance
   workflow create a schema `phase10i-authorization-1.1` record using the exact
   candidate/input/target digests in `authorization_requirements.json`. Required
   record fields are defined in `evaluation/data/release_authorization.py`:
   unique authorization ID, dataset/version/task, the three digests, local_training
   and local_evaluation scopes, approved governance/privacy, real evidence refs,
   owner identity and authorization ref, reviewer identity, real authorized_at,
   APPROVE decision, rationale and explicit restrictions. Cloud processing and
   redistribution remain not_authorized. Bind the original scope and review
   evidence; refresh draft checksums and validate before freezing. The owner may
   provide these decisions as a recorded response and ask the workflow to perform
   the schema serialization; they need not hand-author a complex bundle.
3. Run the readiness command below. Once it passes and the finalized release and
   proposed config are reviewed, separately copy `training_start.template.json`
   to `training_start.approved.json`, fill `APPROVE_TRAINING_START`, owner,
   matching authorization ID and genuine timezone-aware approved_at. Preserve
   its exact current input/target/candidate/config digests. **This decision has
   not been supplied.** Then, and only then, the operator may run training.

The deployed draft's readiness command exited **1**, specifically
`dataset governance review incomplete`, before raw data access. Existing tests
also verify missing/mismatched authorization rejection. Authorization and start
checks precede real preprocessing/training. `--execute` alone cannot authorize it.

## Copy-paste PowerShell commands

Common setup (all configurable paths on D):

```powershell
Set-Location D:\SWARM-AID
$env:PYTHONPATH = 'D:\SWARM-AID'
$env:TEMP = 'D:\SWARM-AID\runs\phase11g4\tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
$python = 'D:\SWARM-AID\.venv\Scripts\python.exe'
$launcher = 'D:\SWARM-AID\runs\phase11g4\floodnet.py'
$release = 'D:\SWARM-AID-DATA\manifests\phase11g4-floodnet-v1'
& $python -u $launcher --mode check --release $release
```

Readiness is metadata/authorization-only; required train/validation asset
integrity is checked on an authorized processing launch. It never opens test
pixels. The following commands are prepared, **not executed**:

```powershell
# Only after genuine clearance, bound authorization and explicit start approval:
& $python -u $launcher --mode train --release $release --execute

# Resume: choose an existing epoch checkpoint from the approved run.
$checkpoint = 'D:\SWARM-AID-DATA\checkpoints\phase11g4-floodnet\run-001\REPLACE_AUTHORIZATION_ID\epoch-0001.pt'
$checkpointHash = (Get-Content -Raw ([IO.Path]::ChangeExtension($checkpoint, '.json')) | ConvertFrom-Json).sha256
& $python -u $launcher --mode train --release $release --execute --resume $checkpoint --resume-sha256 $checkpointHash

# Validation-only finalization of the checkpoint's best state; no optimizer steps:
& $python -u $launcher --mode finalize --release $release --resume $checkpoint --resume-sha256 $checkpointHash
```

Use the **actual checkpoint path printed by the launcher**, replacing the indicated
authorization-ID segment (checkpoint subdirectories follow the existing framework).
Finalization verifies checkpoint digest/context/config and evaluates validation
only; it currently reloads authorized train/validation caches and recomputes
training-only normalization for binding before evaluation. It never evaluates
reserved test data. Resume uses zero workers and rejects inconsistent bindings.

Expected output roots: `D:\SWARM-AID-DATA\cache\phase11g4-floodnet-v1`,
`D:\SWARM-AID-DATA\checkpoints\phase11g4-floodnet\run-001`,
`D:\SWARM-AID-DATA\runs\phase11g4-floodnet\run-001`.

Stop here for genuine owner clearance. Existing scope approval is sufficient for
the prepared exclusion/proposal but does not authorize local data processing or
training. No further historical audit is needed to answer the pending decisions.
