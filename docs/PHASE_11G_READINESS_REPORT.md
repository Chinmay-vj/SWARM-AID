# Phase 11G-0: Model 1 training readiness clearance

**Latest ESC-50 status:** the [final release preparation report](PHASE_11G_ESC50_RELEASE_REPORT.md)
supersedes this document's proposed ESC counts, unconfirmed publisher metadata
and two-reviewer requirement. The owner approved a single-reviewer protocol;
the prepared release has 1,927 clips. Rights/privacy and exact training
authorization remain pending. Earlier findings below are preserved as history.

2026-11-26, PC2. **NO-GO for actual dataset training.** No retained source is
cleared. Recommended first task: ESC-50 environmental sound classification,
conditional on the decisions and release preparation below. This is a readiness
ranking, not measured model performance or permission to train.

## UCI Air Quality Phase 11G-3 addendum

The UCI successor release was prepared separately at
`D:\SWARM-AID-DATA\manifests\phase11g3-uci-air-quality-v1`. The corrected
candidate contains 7,603 24-hour windows: 5,052 training, 1,198 validation and
1,353 reserved test. Training remains NO-GO until source rights/privacy
clearance, exact task authorization and separate training-start approval are
received. See [the UCI readiness report](PHASE_11G_UCI_AIR_QUALITY_READINESS_REPORT.md).

## Evidence and scope

Read AGENTS.md, [Phase 10J](PHASE_10J_COMPLETION_REPORT.md),
[Phase 11A-F](PHASE_11A_F_COMPLETION_REPORT.md), the
[active matrix](datasets/TRAINING_READINESS_MATRIX.md), active scope/registry,
authorization implementation, and existing candidate/review artifacts.
Preserved all prior workspace changes. This report is the only new deliverable.

Reused the Phase 10J result: **173,318 matching file hashes**, including the
supplementary UCI workbook. No raw-file hashing, waveform/image decoding, full
inventory audit, training, GPU benchmark, download, approval creation, frozen
release edit, commit or push occurred. Historical integrity is not a claim that
every raw byte was reverified today. Temporary checks/caches stayed on D:.
Only small release/candidate metadata digests, metadata joins and file existence
were checked. Private imagery and review decisions were not printed.

Current typed authorization bundle:
`D:/SWARM-AID-DATA/manifests/phase10i-d1-e1-v2/authorization_bundle.json`:
**zero records**. All eight active registry entries have `version=null`,
`licence_status=unverified`, `verification=unverified`, `privacy_status=pending`,
and empty `label_definitions`. These are substantive release blockers; the
Phase 10G processing version cannot substitute for a publisher version.

## Dataset readiness and recommended order

Every row also needs exact source identity, reviewed scope/privacy/rights,
operational and target manifests, registered task/taxonomy, and checksum-bound
authorization. Effort estimates are qualitative judgments, not schedules.

| Order / source | Supervision and existing evidence | Remaining task-specific blockers | Clearance effort / disposition |
|---|---|---|---|
| 1. ESC-50 | Environmental classes and publisher recording IDs. 1,991 candidate clips after nine exclusions; all join to local metadata, 50 classes retained. | Bind exact release/commit to local metadata and Phase 10J ledger; review clip terms/attribution, audio privacy and label protocol; approve fold roles; create real targets and taxonomy. Generic sound is not distress. | Lowest relative effort; best first modality, still BLOCKED. |
| 2. UCI Air Quality | Instrument-reference CO; existing 24-hour-lookback/next-hour candidate: 5,052 train, 1,198 validation, 1,353 test. Purging already audited. | Resolve source terms, confirm CO units/features/horizon and missing-value treatment, approve single-site temporal claim; carry forward purge/exclusion evidence into target manifests. No site-generalization claim. | Moderate; strongest sensor candidate, still BLOCKED. |
| 3. FloodNet | 2,343 indexed image/mask pairs; prior pixel checks match historical summaries; 29 queued mask reviews. | Confirm numeric class-to-legend mapping; obtain site/flight/capture groups and leakage-safe partitions; exact release/privacy/rights decisions. | High because capture identities are absent; first proposed RGB task is segmentation. |
| 4. FLAME | Fire/non-fire image folders; 38,884 train and 8,617 test candidate frames after 491 near-test exclusions. | All 47,501 candidate `group_ref` values are null: parent-video independence is unproven. No validation partition yet. Confirm classification labels, release and rights. Keep 2,003 unpaired masks out of segmentation. | High; cannot treat file names or frame numbers as independent capture groups. |
| 5. RescueNet | 4,494 indexed image/mask pairs; 33 queued reviews including damage semantics. | Confirm local numeric taxonomy against exact publisher version; adjudicate damage grades; site/flight groups, privacy and dataset terms. Current publisher list and prior local person-class assumptions require explicit reconciliation. No masks-to-boxes inference. | High; segmentation first, damage task only after semantic review. |
| 6. Smoke Detection IoT | 62,630 indexed rows; source author describes a binary fire-alarm target. | Five apparent runs collapse to three repeated-signature groups. Recover run identities, annotation procedure and exact CSV release; establish independent splits, feature units/horizon and rights/privacy. Keep target, counters and identifiers out of model features. | High; author description does not independently validate labels or split quality. |
| 7. WiSARD | Display-coded visual/thermal imagery and box sidecars. Publisher describes synchronized subsets. | 1,275 flagged annotations, 11,542 missing sidecars, 30 review exemplars; establish format/geometry, authoritative capture groups and splits. Zero locally verified pairs. Review whether any classification targets are actually supported; registered task is thermal person detection. | Very high; no conversion of absent sidecars to negatives, no inferred pairs or physical-temperature labels. |
| 8. USGS Water | Only 36 overlapping interval summaries in the current artifact. | Recover station/parameter/unit/query/time-range provenance and exact snapshot; decide a defensible interval task with independent supervision and partitions. No continuous time series or flood-event labels exist in this artifact. | Not suitable for an initial supervised task; defer rather than invent targets. |

This order favors explicit supervision, usable partition metadata and lower
clearance effort. It can change when authentic source evidence arrives.
HERIDAL/SARD remain excluded. Native Model 1 tasks and Model 2 are outside this
eight-source clearance; historical review items are preserved.

## Targeted automated findings

1. Typed authorization parsing confirms zero approvals. Original review packet
   still has zero completed reviewer slots. Retained queue is exactly
   **92 items / 184 independent slots**: FloodNet 29, RescueNet 33, WiSARD 30.
   The 60 HERIDAL/SARD items require no work for this active scope.
2. Existing ESC-50, FLAME and UCI candidate JSONL digests match their descriptor
   bindings. Candidate counts match the reported partitions. Their
   `dataset_version` and all `target_label` fields are null: these are partition
   descriptors, not executable supervised releases. UCI's numeric targets also
   need a reviewed target manifest; null categorical labels alone do not imply
   that its existing temporal-window evidence is defective.
3. ESC-50's 1,991 candidate rows join by filename to the 2,000-row publisher
   metadata CSV. Fold and `src_file` recording identity agree for every row;
   every retained audio path exists. All 50 categories/target IDs survive, with
   37-40 clips per category; no retained recording group spans folds.
   Excluded recording IDs stay `131943`, `134049`, `209698`, `234879`.
4. Proposed ESC split is folds 1-3 train (1,196), fold 4 validation (398), fold 5
   reserved test (397). This is a proposed fixed holdout, not official five-fold
   cross-validation. No test audio was decoded or used for model selection.
5. Correct ESC metadata location is
   `D:/SWARM-AID-DATA/raw/audio/audio/ESC-50-master/ESC-50-master/meta/esc50.csv`.
   The extra archive directory matters. Resolve candidate `source_path` under
   `D:/SWARM-AID-DATA/raw/audio/audio/ESC-50-master/`, not directly under `raw`.
   Local LICENSE is beside that inner `meta` directory. This resolves path/join
   uncertainty only; frozen paths were not rewritten.
6. FLAME's null groups must not be counted as one identified recording spanning
   train/test. They mean unknown capture identity. UCI candidate day groups do
   not cross partitions; reuse the prior window-purge audit, since day-group
   separation alone cannot prove absence of overlapping temporal windows.

No training blocker was cleared by treating a passing metadata check as a human
decision. Creating successor manifests/taxonomies remains future engineering
work dependent on the reviewed source versions and protocols below.

## Source-version and governance evidence

Primary pages were read on 2026-11-26 without downloading payloads. These are
source statements, not legal conclusions or bindings to local bytes. No exact
local publisher version was established for any of the eight datasets.

| Source | Evidence and required interpretation |
|---|---|
| ESC-50 | [Publisher repository](https://github.com/karolpiczak/ESC-50) identifies environmental classes and noncommercial dataset terms, with separate ESC-10 terms and clip attributions. Local LICENSE is available. Steward must pin the exact revision and check retained clip terms; the smaller ESC-10 licence cannot clear all 50 classes. |
| UCI | [Publisher page](https://archive.ics.uci.edu/dataset/360/air%2Bquality) still exposes research-only/commercial-exclusion language alongside CC BY 4.0 metadata. It describes analyzer references and the -200 missing sentinel. Legal/owner reconciliation remains required. |
| FloodNet | [Publisher repository](https://github.com/BinaLab/FloodNet-Supervised_v1.0) supplies a class legend and CDLA-permissive link. The repository name is not proof of local archive version; capture groups/privacy still need evidence. |
| RescueNet | [Publisher repository](https://github.com/BinaLab/RescueNet-A-High-Resolution-Post-Disaster-UAV-Dataset-for-Semantic-Segmentation) gives dataset CC BY-NC-ND terms separately from MIT code. Its visible legend lists 11 categories and no person category; do not resolve local class semantics from earlier prose. Review exact release legend and mask convention. |
| FLAME | [Lab page](https://sites.google.com/g.clemson.edu/is-win-lab/resources/datasets) now exposes FLAME 1/2/3 links. FLAME 1 DataPort fetch was denied by robots.txt; no retry or download. Obtain exact FLAME 1 release/terms evidence matching this local archive; newer FLAME releases are not substitutions. |
| WiSARD | [Publisher page](https://sites.google.com/uw.edu/wisard) now exposes MIT-style text referring to software/documentation and describes 15,453 synchronized pairs. This resolves the earlier unavailable-page-text limitation only. Steward must establish applicability to dataset assets and map the local files to authoritative pair/capture records; zero pairs are locally verified. |
| Smoke | [Author page](https://community.element14.com/products/arduino/arduino-projects/b/blog/posts/real-time-smoke-detection-with-ai-based-sensor-fusion) is now readable, describes 1 Hz acquisition and Fire Alarm=1 for fire. It does not establish local run independence, annotation reliability, exact export version or adequate reuse terms. |
| USGS | [Download documentation](https://api.waterdata.usgs.gov/download/) describes query-based retrieval and station metadata. It does not identify the derivation/version of this local interval-summary CSV. Recover its original query/export receipt and processing record; no new retrieval is needed now. |

## Frozen-release recovery

The release file still hashes to
`81b0ed436ce8e2bc3ec260f85a87dc89c28f95dc585e3309d8ae3e88c57e11b8`.
Existence checks of all 19 recorded evidence paths found exactly one missing:

- Destination: `D:/SWARM-AID-DATA/simulation/field-v1/manifest.json`.
- Required SHA-256: `29a8b1f3d8eeb360b08b7f88dfbe215898580d2d380bb3e8d8d677e3bfa66e5a`.
- Also absent at the old PC2 location
  `D:/SWARM-AID/datasets/simulation/field-v1/manifest.json`.
- Reuse Phase 10J's matches for the other 18 evidence entries. No deeper native
  payload completeness claim is made from manifest existence.

**PC2-only update:** the local search below supersedes the earlier external
recovery plan. No access to another workstation is required or requested.
If a matching local backup is subsequently found, stage a byte-preserving copy at
`D:/SWARM-AID/recovery/phase10h/manifest.json`. Do not regenerate it from a
simulation, normalize line endings, substitute a similarly named manifest or
edit the release checksum. No recoverable matching local copy was found.
If a local custodian supplies a matching copy, the following PowerShell sequence
checks and restores only the missing artifact (not executed here):

```powershell
$staged = 'D:\SWARM-AID\recovery\phase10h\manifest.json'
$destination = 'D:\SWARM-AID-DATA\simulation\field-v1\manifest.json'
$expected = '29a8b1f3d8eeb360b08b7f88dfbe215898580d2d380bb3e8d8d677e3bfa66e5a'
if ((Get-FileHash -LiteralPath $staged -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'Wrong frozen artifact; stop' }
if (Test-Path -LiteralPath $destination) { throw 'Destination exists; inspect without overwriting' }
New-Item -ItemType Directory -Force -Path 'D:\SWARM-AID-DATA\simulation\field-v1' | Out-Null
Copy-Item -LiteralPath $staged -Destination $destination
if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'Recovery checksum mismatch' }
```

Recovery alone will not clear the entire frozen verifier. Phase 10J recorded
37/41 repository-file byte differences: 33 line-ending-only and four substantive
changes in `evaluation/data/{contracts,preprocessing,training_partition,validation}.py`.
The existing `phase10h_successor_changes.json` records only training_partition.
Have the release custodian identify a byte-exact archived historical checkout
or review a **new**, separately versioned successor record covering every
accepted difference, with historical/current digests and reasons. Do not alter
the active checkout or the old successor record merely to make the check pass.
After recovery and that review, the existing verifier command is:

```powershell
.\.venv\Scripts\python.exe -m evaluation.data.phase10h_verify --root D:\SWARM-AID-DATA --repository D:\SWARM-AID --successor-changes D:\SWARM-AID-DATA\manifests\phase11g0-reviewed-v1\phase10h_successor_changes.json
```

The proposed successor file does not exist yet. If the original manifest cannot
be recovered, report irrecoverable evidence and request a separately governed
successor-release decision; do not claim historical verification.

## Human decision queue

Work on ESC-50 first; other-source reviews can wait. Automated hash comparisons,
joins, schema conversion and report generation are engineering tasks, not human
review questions. Do not ask reviewers to repeat them.

| ID / owner | Decision and exact return requirements |
|---|---|
| H1 — release custodian | Supply the missing frozen file and backup provenance; decide whether a documented successor covers the known code differences. Return file/reference, custodian identity and disposition. If unavailable, record that fact; no fabricated replacement. |
| H2 — source steward, per selected dataset | Identify publisher release/commit/export and bind it to the already verified local inventory. Supply archive/receipt, metadata/legend and applicable terms references. For unknown capture/run/station identity, obtain authoritative records or defer the affected task; do not invent IDs. |
| H3 — owner/legal/privacy reviewers, per selected dataset | Decide local training, local evaluation, retention and purpose restrictions; document privacy assessment, attribution and any derived-artifact limits. Keep cloud processing and redistribution unauthorized unless separately decided. Resolve UCI and RescueNet terms explicitly; for WiSARD establish whether displayed licence covers assets. Return identities, timestamps, evidence refs and rationale. |
| H4 — ESC-50 protocol reviewer + independent audio reviewers | Accept/revise the 50-category environmental task and fixed fold roles; confirm exclusions and sorted-label mapping. Approve a risk-based train/validation audio-label/privacy review protocol, then record independent outcomes with clip IDs/digests and adjudication. Do not listen to reserved test clips for development review or infer distress. Existing 92-item visual queue does not cover ESC-50; create separately versioned audio review evidence, not invented prior decisions. |
| H5 — two independent visual reviewers + adjudicator, only if clearing those sources | From the existing packet select `dataset` in `{FloodNet, RescueNet, WiSARD}`: 29/33/30 items. Compare mask/box meaning with the exact publisher legend and permitted source scene. Use original review IDs/digests; fill both reviewer slots independently. Record ACCEPT/REJECT/CORRECTION_REQUIRED/INSUFFICIENT_EVIDENCE/DEFERRED, rationale, evidence, identity and time; adjudicate disagreements. 30 WiSARD exemplars do not clear all 1,275 flags: approve a documented rule or review remaining cases before inclusion. |
| H6 — task/data lead, other modalities | UCI: confirm 24h/next-hour CO, units, predictor whitelist, purge and single-site claim. FLAME: verify parent videos and held-out grouping. FloodNet/RescueNet: approve site/capture holdouts and taxonomy. Smoke: confirm alarm provenance and independent runs. WiSARD: approve supported annotation task/format; defer pairs without mapping. USGS: decide whether current summaries justify any supervised task; otherwise defer. |
| H7 — authorized owner after release preparation | Review the final exact task/release/configuration and issue a schema 1.1 authorization binding candidate, canonical operational manifest and target manifest hashes, with both `local_training` and `local_evaluation` scopes. Provide owner/reviewer identities, evidence refs, timestamp, restrictions and rationale. Then give an explicit Phase 11G training start decision. |

Original packet:
`D:/SWARM-AID-DATA/manifests/phase10i-d1-e1-v2/human_review_packet.jsonl`.
Preserve it. Return a new reviewed packet under an approved D-drive review
directory. Use `source_path` plus the active source-root mapping for relocated
assets; its old `source_evidence.resolved_path` is historical. Any actual label
correction becomes a versioned derived annotation with lineage, never a raw edit.

## Proposed first task and launch recipe — not executed

**ESC-50 single-modality environmental sound classification**, random-initialized
`AudioClassifier`, 50 reviewed categories, no distress/rescue outcome targets.
Proposed initial settings: seed 2025; CUDA BF16; batch 2, accumulation 2; AdamW
learning rate 0.001, weight decay 0.0001; 30 epochs maximum, patience 5; clip norm
1.0; zero workers; 8 GiB allocator budget; checkpoint each epoch. No augmentation
or fitted normalization in the initial baseline. Select by validation macro-F1;
report accuracy, precision/recall and ECE as implemented. Reserve test fold 5 for
a separately approved final evaluation; no benchmark-equivalence claim.

Existing preprocessing downmixes PCM16 audio, resamples to 16 kHz and computes
40-bin log-mel features with 25 ms windows / 10 ms hop. Five seconds yields
approximately `[1,498,40]`, not the earlier `[1,128,64]` synthetic profile shape.
Batch 2 is a conservative proposal, not a measured memory guarantee for this
shape. Exact-shape synthetic validation remains a pre-launch engineering check.

After H2-H4, prepare a **new** release directory
`D:/SWARM-AID-DATA/manifests/phase11g-esc50-v1/` containing `registry.json`,
`operational.json`, `targets.json`, `candidate.json`, its bound records file,
and `authorization_bundle.json`. These are proposed paths, not existing
approvals. Reuse the verified source hashes, official metadata labels and group
exclusions. Populate reviewed exact version, 50 label definitions and registered
task `audio event classification`. Target labels must match registry names;
model indices use their sorted order, not an assumed publisher numeric ordering.
Operational/target sample IDs, source refs and partitions must agree. Keep test
data separate from fitting; no target construction by folder-name guessing.

There is no real-data training CLI in `evaluation.model1.training`. The following
is the exact proposed PowerShell launch through existing public Python APIs,
to run from `D:/SWARM-AID` **only after H1-H7, approved manifests and the explicit
start decision**. It intentionally fails on absent/pending/mismatched release
artifacts. No unsupported `--train` switch or synthetic-loader fallback is used.

```powershell
$env:TEMP = 'D:\SWARM-AID\runs\phase11g\tmp'
$env:TMP = $env:TEMP
$env:TORCH_HOME = 'D:\SWARM-AID\runs\phase11g\torch-cache'
New-Item -ItemType Directory -Force -Path $env:TEMP, $env:TORCH_HOME | Out-Null
@'
import json
from pathlib import Path
import torch
from evaluation.data.contracts import Manifest, Registry
from evaluation.data.release_authorization import AuthorizationBundle
from evaluation.model1.data import AuthorizedTaskDataset, TaskDataConfig, build_task_dataloader
from evaluation.model1.models import ModelConfig, build_model
from evaluation.model1.training import (
    ClassificationTask, TrainingConfig, authorized_training_context, fit, seed_everything,
)

root = Path('D:/SWARM-AID-DATA')
release = root / 'manifests/phase11g-esc50-v1'
registry = Registry.model_validate_json((release / 'registry.json').read_bytes())
inputs = Manifest.model_validate_json((release / 'operational.json').read_bytes())
targets = Manifest.model_validate_json((release / 'targets.json').read_bytes())
bundle = AuthorizationBundle.model_validate_json((release / 'authorization_bundle.json').read_bytes())
if inputs.dataset_id != 'esc50':
    raise ValueError('Expected the reviewed ESC-50 release')
config = TrainingConfig(
    device='cuda:0', seed=2025, batch_size=2, gradient_accumulation=2,
    workers=0, epochs=30, learning_rate=0.001, weight_decay=0.0001,
    early_stopping_patience=5, gradient_clip_norm=1.0,
    mixed_precision=True, amp_dtype='bfloat16', max_gpu_memory_gb=8,
    checkpoint_every=1,
    checkpoint_root=root / 'checkpoints/phase11g-esc50/run-001',
    profile_output_root=root / 'runs/phase11g-esc50/run-001',
)
data_config = TaskDataConfig('audio_classification', batch_size=2, workers=0)
datasets = [
    AuthorizedTaskDataset(
        registry, inputs, targets, root, data_config,
        task_id='audio event classification',
        candidate_manifest_path=release / 'candidate.json',
        authorization_records=bundle.records, split=split,
    )
    for split in ('train', 'validation')
]
train, validation = datasets
if len(train.labels) != 50 or train.labels != validation.labels:
    raise ValueError('Expected the reviewed 50-class taxonomy')
if (len(train), len(validation)) != (1196, 398):
    raise ValueError('Reviewed fold counts changed; reassess protocol before training')
if config.checkpoint_root.exists() or config.profile_output_root.exists():
    raise FileExistsError('Run output exists; do not overwrite or silently resume')
seed_everything(config.seed)
model_config = ModelConfig(task='audio_classification', num_classes=50, input_channels=1)
model = build_model(model_config)
loaders = [build_task_dataloader(d, seed=config.seed, device=torch.device(config.device)) for d in datasets]
result = fit(
    model, loaders[0], loaders[1], ClassificationTask(), config=config,
    context=authorized_training_context(train), model_config=model_config.model_dump(mode='json'),
)
config.profile_output_root.mkdir(parents=True)
(config.profile_output_root / 'summary.json').write_text(json.dumps({
    'best_epoch': result.best_epoch, 'best_score': result.best_score,
    'labels': train.labels, 'config': config.model_dump(mode='json'),
}), encoding='utf8')
'@ | .\.venv\Scripts\python.exe -
if ($LASTEXITCODE -ne 0) { throw 'Training launch rejected or failed; inspect the error' }
```

The launch recipe's Python syntax and imported public APIs were verified without
executing its body; its use of existing signatures was inspected. It has not run
with real data. Dataset construction retains existing mandatory
file-integrity checks at future authorized launch; this readiness task did not
invoke those loaders on real assets. First complete reviewed release preparation
and exact-shape synthetic validation; do not bypass missing input files.

## Gate verification and stop condition

Focused repository-root pytest: **24 passed, 11 deselected, 1 warning in 1.59s**.
Covered authorization failures, stale candidate/records/target bindings, pending
governance, wrong scope/rejection, normalizer gating, reserved seeds, split-group
isolation, frozen verifier behavior and excluded-source handling. Command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/unit/test_release_authorization.py tests/unit/test_phase10j.py tests/unit/test_phase10h_verify.py tests/unit/test_phase11_model1.py -k 'authorization or training_loader or approval or normalizer or reserved or cross_split or phase10j or inventory or successor or release or task_loader or real_training_context'
```

Ruff and `git diff --check` passed; strict MyPy passed for 182 source files.
The warning is the existing
Starlette/httpx deprecation. No full regression or GPU rerun was needed for this
report-only task; reuse Phase 11A-F's 328 passed / 1 skipped and 54/54 synthetic
GPU results. Focused log: `runs/phase11g0/gates.log`.

The gates enforce typed local evidence, not external identity/signature checks.
Their passing tests do not authenticate a human's claims; authorized custodians
remain responsible for genuine source/review/owner evidence. Nothing in this
report changes the gate implementation or grants approval.

**Stop here for genuine human input:** use the PC2-only successor decision and
four operator steps below, then prepare the reviewed release and authorization.
Other datasets remain deferred in the ranked order. Civilian disaster
search-and-rescue simulation only; no physical control or operational accuracy
claim is supported.

## PC2-only continuation: local recovery and minimum decisions

This section supersedes the external-recovery prerequisite above. Phase 10 and
11A-F were not repeated. No dataset file was rehashed. No historical release,
registry, approval or training gate was modified.

### Local recovery result and limits

Searched accessible D-drive names with `rg --files --hidden --no-ignore` for
manifest JSON, ZIP/7z/TAR/TGZ and backup files; enumerated `D:/eScanBackup` and
`D:/handoff_context`. Results are retained in
`D:/SWARM-AID/runs/phase11g1/local-candidates.txt` and `search-errors.log`.

- Found 22 candidate paths, including 12 manifest files outside dependency
  trees and eight ZIP archives. None of those manifest files matches the missing
  SHA-256. ZIP directory listings contain no relevant field-v1/SWARM manifest,
  nor a JSON manifest member to compare. No archive payload dataset was decoded,
  extracted or rehashed, including the large WiSARD archive.
- `git log --all` for the expected paths and `git rev-list --objects --all
  --reflog` found no frozen manifest. Read-only `git fsck --full --no-reflogs
  --unreachable` found four unreachable blobs; none matches its SHA-256. Git
  objects and working files were not changed.
- eScan contains eight `.fil` files and a 176,128-byte catalog. `.fil` files are
  gzip-wrapped, but decoded headers do not identify ZIP/TAR payloads;
  the catalog is not SQLite and contains no plain ASCII/UTF-16 SWARM
  marker. This is **not** proof that its proprietary backup format has no copy.
  No backup was restored or altered. Filenames date through November 23, earlier
  than the recorded November 26 release creation, which is suggestive only.
- Windows denied access to System Volume Information and two recycle-bin
  directories. No recovery assertion is made about those locations. We did not
  elevate access or request another workstation.

**Conclusion: unavailable from the accessible, readable local evidence searched;
global irrecoverability is unproven.** An operator who already has a working
eScan restore interface may search its local catalog for
`simulation/field-v1/manifest.json` and stage a copy using the checksum procedure
above. This optional recovery route is not a requirement to obtain PC1 access.
Do not restore a whole backup over the current project.

### Separately versioned successor proposal

Review [phase11g_esc50_successor_v1.json](proposals/phase11g_esc50_successor_v1.json).
Its status is `PROPOSED_PENDING_OWNER_REVIEW`, `training_approved=false`, with
zero authorization records and blank owner decision. It is deliberately **not**
an operational manifest, authorization bundle or a `phase10h_successor_changes`
record accepted by the old verifier.

The proposed boundary is a new, independently governed ESC-50 audio release.
It reuses the verified ESC ledger and candidate partitions and explicitly
excludes native field simulation evidence, Model 2 and other datasets. It does
not repair the missing historical file, declare the complete Phase 10H release
verified, or authorize an exemption from current training gates. An owner must
decide whether this narrower successor is acceptable, with the missing evidence
and code-successor limitations retained in provenance. The old frozen manifest,
old successor record and raw files remain unchanged.

### Newly completed ESC-50 automated work

Local artifacts under `D:/SWARM-AID/runs/phase11g1/`:

| Artifact | Purpose / measured result |
|---|---|
| `esc50_metadata_clearance.json` | All 1,991 candidate audio hashes agree with the existing per-file ledger; no audio was hashed or opened. Fifty one-to-one category/publisher target IDs mapped to sorted model indices. Reused existing CSV/LICENSE/README digests. |
| `esc50_attribution_index.jsonl` | 1,990 exact attribution-key matches: 861 CC0, 899 CC-BY, 170 CC-BY-NC, 60 CC-Sampling+. These are source tags, not permission determinations. |
| `esc50_review_proposal_v1.jsonl` | 100 proposed reviews: one deterministic train and one validation example per category, each with two blank independent reviewer slots. Zero test items, zero filled decisions. Selection is a proposed initial screen, not proof of label quality or sufficient privacy coverage. |
| `esc50_shape_check.json` | New outstanding-shape check only: synthetic `[2,1,498,40]` input to the audio model gives finite `[2,50]` CUDA BF16 output; peak tensor allocation 10,146,304 bytes. Inference only, zero optimizer steps, no backward pass. This does not measure training memory or accuracy. |

The one attribution mismatch is **`5-141683-A-35.wav`**, in reserved test fold 5.
LICENSE lists **`5-141683-Ad.ogg`** with the same recording number, but equivalence
was not inferred. Human/source clarification or a reviewed exclusion is needed;
do not listen to test audio to resolve a metadata rights question. Excluding it
would change reserved-test count from 397 to 396 and require a new candidate and
authorization binding, not an edit to historical files. Train/validation counts
would remain 1,196/398. Any other rights-based exclusions require recalculation.

Local README documents v2.0.0's transition to WAV, consistent with the local
layout. This does **not** establish the exact downloaded commit or publisher
release of all files. Source identity is still a real evidence/owner decision.
No automatic promotion of `dataset_version=null` occurred.

### Exact operator steps — four decisions, ESC-50 only

1. **Owner: decide the successor scope and source identity.** Open the proposal
   JSON and this section. Accept, reject or defer an independent ESC-50-only
   release with incomplete historical native evidence explicitly excluded.
   Supply available local download receipt/archive metadata, commit/version or
   publisher evidence binding this snapshot. If identity cannot be established,
   record insufficient evidence and remain NO-GO; do not infer it from the
   README version. Optionally inspect the local eScan catalog as described above.
   Save your decision, identity, timestamp, rationale and evidence references in
   `D:/SWARM-AID/runs/phase11g1/owner_response_v1.json`; do not edit the proposal
   or any historical release. A short JSON object with those named fields is
   sufficient for the response; it is not a training authorization.
2. **Rights/privacy reviewer: decide scope and exceptions.** Review the bundled
   LICENSE at `D:/SWARM-AID-DATA/raw/audio/audio/ESC-50-master/ESC-50-master/LICENSE`
   alongside `esc50_attribution_index.jsonl`. Determine local training,
   evaluation, retention and attribution requirements; explicitly resolve the
   60 CC-Sampling+ entries and unmatched test-clip key. Record accepted evidence
   or proposed exclusions; no inferred licence substitution. Review human
   non-speech classes for privacy and approve or revise the listening protocol
   before reviewers access audio. Leave cloud/redistribution unauthorized.
   Save identity, timestamp, decisions, restrictions and evidence references in
   `D:/SWARM-AID/runs/phase11g1/rights_privacy_response_v1.json`.
3. **Protocol owner and independent reviewers: complete only the ESC queue.**
   Approve/revise the 100-item initial screen first. Copy
   `esc50_review_proposal_v1.jsonl` to `esc50_review_completed_v1.jsonl` in the same
   folder. For each permitted clip, compare the supplied environmental category
   to the audio; check corruption, ambiguity and privacy concerns. Preserve
   `record_id`, filename, SHA-256, category and fold. Two different reviewers
   independently fill `reviewer_identity`, `decision`, `rationale`, `reviewed_at`
   (ISO 8601 with timezone), and `evidence_refs`; an adjudicator records resolution
   of disagreements in `adjudication`. Allowed decisions remain ACCEPT, REJECT,
   CORRECTION_REQUIRED, INSUFFICIENT_EVIDENCE or DEFERRED. Do not fill acceptance
   automatically. The owner must approve review adequacy and any expanded
   sampling indicated by failures. Do not review the 92 visual items to clear
   this audio-only task, and do not open test clips for development review.
4. **Return those three response files for release preparation; then authorize
   the concrete release.** Engineering will apply only approved metadata
   mappings/exclusions to new operational/target manifests, verify partitions
   and compute their canonical hashes. Review the resulting exact files and
   issue schema `phase10i-authorization-1.1` inside a
   `phase10i-authorization-bundle-1.1`, binding candidate, input and target
   hashes. Include genuine owner/reviewer identities, evidence refs, timestamp,
   restrictions and both local-training/local-evaluation scopes. Separately
   state the training start decision. Do not create a hashless approval now or
   run the earlier launch recipe while any of these requirements is pending.

No new runtime code was changed. This continuation's focused
`python -m pytest -q tests/unit/test_release_authorization.py` passed **13 tests**
in 0.10s, with one existing Starlette/httpx deprecation warning. Ruff,
strict MyPy (182 files) and `git diff --check` passed. Proposal/packet assertions
verified 100 unique IDs, 50 categories, 200 blank reviewer slots, zero test clips
and zero approvals. No full regression or earlier audit was repeated.
Current work stops at these genuine owner/source,
rights/privacy and independent-review decisions; no training is started.
