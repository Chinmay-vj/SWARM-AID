# Phase 11A-F completion report

PC2, 2026-11-26. **Software development and synthetic validation completed;
actual dataset training remains NO-GO.** Phase 11G is not started or approved
for dataset training. The user's explicit request supersedes the earlier
implementation hold but does not grant any source or task-use approval.

## Compatibility and architecture

Reused the existing `evaluation/model1/` implementation already committed
from PC1. The current work extends it rather than replacing the working
simulation. Read AGENTS.md, Phase 10J, the Phase 11 handoff, active readiness
matrix, system architecture and existing providers. Phase 10J integrity results
were reused; no Phase 10 data audit or raw-file hashing was repeated. Existing
uncommitted Phase 10J changes were preserved.

| Component | Implementation and boundary |
|---|---|
| RGB and thermal | Randomly initialized MobileNetV3 Small; 3-channel RGB and 1-channel display thermal. No pretrained downloads or temperature claims. |
| Segmentation | DeepLabV3/MobileNetV3; source-verified mask taxonomy required. |
| Detection | Faster R-CNN/MobileNetV3; exercised with synthetic boxes only. No retained approved RGB person-box supervision. |
| Audio | Compact log-mel CNN for environmental classes; no distress labels inferred. |
| Sensors | GRU over values and explicit per-value availability; classification/regression heads and all-missing abstention. Windows require explicit features, rows, units and horizon. |
| Fusion | Named feature projections and learned attention with boolean availability. Missing NaN payloads are zeroed before encoding; present nonfinite values are rejected. FP32 attention normalization avoids FP16 sentinel overflow. |
| Temporal context | `TemporalHead` GRUCell and `AgentTemporalContext`: shared weights, independent detached hidden tensors, checked agent identity and increasing mission ticks, explicit reset. Missing evidence preserves state and yields an invalid prediction. |
| Uncertainty | Validity masks, softmax scores, entropy, calibration/missingness metrics. These are uncalibrated synthetic outputs, not validated confidence estimates. |
| Provider integration | Existing opt-in `TrainedPerceptionProvider` implements `interfaces.providers.PerceptionProvider`, preserves evidence lineage and stable observation IDs, checks ownership and retains possible-human uncertainty. |

Torch and transport/model SDKs remain outside core domain/provider ports.
ML stays optional through the existing `ml` extra; no dependencies were
installed or replaced. Default deterministic simulation, safety validation,
human decisions, Model 2 and transport contracts are unchanged. Temporal
contexts are opt-in local components; they do not share or centralize memory.
The current runtime evidence wire type has no audio modality: audio remains
an offline task component. No incompatible wire extension or automatic live
multimodal deployment was introduced.

## Dataset pipeline and task scope

`configs/model1_task_profiles.json` maps the eight retained sources to task
families and blockers. Existing `AuthorizedTaskDataset`/`AuthorizedFusionDataset`
consume reviewed operational and target manifests, not unreviewed raw folder
names. They validate authorization, taxonomy, annotations, asset checksums,
paired identifiers, partition lineage and train-only normalization/augmentation.
Existing source parsing and preprocessing are reused. Real source mappings and
head dimensions still require reviewed releases; none were invented here.

HERIDAL and SARD now fail at Model 1 loader/verifier entry even if a caller
passes a historical registry. Other authorization restrictions remain intact.
Input/target hashes and candidate descriptors bind task/use-scope approvals;
test rows and reserved evaluation seeds 42-46 remain protected. No unrelated
modalities are paired. Variable batch sizes are supported; within a sensor
batch, windows must share the task's configured length and feature schema.

| Source | Prepared task family | Actual-data disposition |
|---|---|---|
| FloodNet | Semantic segmentation | BLOCKED: reviewed taxonomy, site groups, rights/privacy and authorization |
| RescueNet | Semantic segmentation / reviewed damage labels | BLOCKED: label/site review; person masks do not imply detection boxes |
| FLAME | Fire classification | BLOCKED: parent video groups, rights and near-frame exclusions; unpaired segmentation masks remain unsupported |
| WiSARD | Thermal classification / explicit-pair fusion infrastructure | BLOCKED: annotation review, thermal representation, capture identity; zero verified cross-modal pairs |
| ESC-50 | Environmental sound classification | BLOCKED: clip terms, recording exclusions and authorized folds; no distress supervision |
| Smoke Detection IoT | Sensor classification | BLOCKED: run identity, split and target provenance |
| UCI Air Quality | Horizon-bound CO regression | BLOCKED: reviewed temporal windows/units/rights and authorization |
| USGS Water | Interval sensor processing | BLOCKED: interval summaries are not continuous series or flood-event labels |

All remain zero-approved-record tasks. RGB person detection is synthetic-only
because HERIDAL/SARD are excluded. No raw data or real training loader was run.
Synthetic unit-test approvals represent fixtures only, never actual owners.

## Training, checkpoints and resume

Reused task losses/metrics, AdamW or caller-supplied optimizer, scheduler,
AMP, gradient accumulation, clipping, validation and early stopping. Added
nonfinite-gradient rejection, an enforced CUDA allocator budget, and integrated
epoch checkpoints with metadata logging. Final in-memory weights still restore
the best validation epoch; checkpoint files retain the exact saved epoch.

Checkpoint payloads contain model, optimizer, scheduler, AMP scaler, epoch,
step, early-stopping/best-state history, Python/NumPy/CPU/CUDA RNG and loader
shuffle-generator states. Resume verifies checksum, task/release context,
configuration and framework compatibility. CPU deserialization keeps RNG
byte tensors on CPU when restoring CUDA runs. Source-tree SHA-256 accompanies
Git revision and dependency versions so uncommitted model code is identifiable.

Writes use a same-directory temporary file, flush/fsync and atomic replacement;
existing checkpoint filenames are refused. Synthetic and authorized artifacts
remain in separate directories. JSON summaries contain metrics, context and
checkpoint checksum, never imagery or private artifacts. The checkpoint hash
must be supplied from trusted local metadata; it is not an owner signature.
Existing checkpoint schema 1.0 accepts optional loop state; legacy standalone
checkpoints remain loadable but cannot resume `fit` without that state.

Exact resume is supported at epoch boundaries with zero loader workers and
matching loader configuration, environment and data. Mid-epoch continuation,
custom stateful sampler restoration and cross-hardware bitwise equivalence
are not claimed. CUDA CPU and FP16 resume tests compare uninterrupted and
resumed histories and final weights, including dropout, shuffling, incomplete
accumulation groups and a stepped scheduler. Bad checkpoint hashes fail closed.

## Measured synthetic GPU profile

Command: `.venv/Scripts/python.exe -m evaluation.model1.profile_components`.
Detailed local results: `runs/phase11/gpu.json`; no dataset assets are opened.
RTX PRO 4500 Blackwell, PyTorch 2.11.0+cu128, CUDA 12.8. Batches 2 and 8,
FP32/BF16/FP16, one warmup and two measured optimizer steps per case. Visual
inputs are 128x128; audio is 128x64 log-mel; sensors are 24x6. Fusion and
single-step temporal probes use small feature vectors. All **54/54** cases
passed finite-loss and gradient checks under an 8 GiB allocator limit.

Timing includes forward, backward and AdamW, with CUDA synchronization.
It excludes disk I/O, source preprocessing and data-loader workers. These short
measurements are indicative, not steady-state performance or accuracy results.
The allocator cap excludes CUDA context/driver overhead; maximum hardware
batch size was deliberately not sought.

| Component | Batch-8 BF16 examples/s | Peak allocated MiB |
|---|---:|---:|
| image_classification | 327.71 | 61.7 |
| thermal_classification | 420.92 | 60.6 |
| audio_classification | 1375.05 | 48.6 |
| sensor_classification | 1307.60 | 27.5 |
| sensor_regression | 2211.23 | 27.5 |
| semantic_segmentation | 302.16 | 272.6 |
| object_detection | 119.06 | 508.3 |
| fusion | 1371.78 | 18.3 |
| temporal | 2814.72 | 18.0 |

Maximum allocated memory across all measured cases was 0.614 GiB. Batches 2
and 8 are demonstrated working bounds at these shapes, not maximum safe
batches for real inputs. Initial config profiles now use BF16, 128x128,
zero workers, an 8 GiB cap and batch 2 with accumulation 2 (conservative) or
batch 8 with accumulation 1 (standard). Use these only after task authorization;
re-profile larger resolutions and long sequences before raising limits.

An initial profiler invocation rejected an unindexed `cuda` device at memory
budget setup. It was corrected to `cuda:0` before the successful profile.
No installation changes or repeated dataset audits were used to resolve it.

## Verification and Phase 11G readiness

Focused tests: 44 passed (models, masks, exclusions, authorization and existing
Model 1 simulation); subsequent CPU/CUDA resume tests: 6 passed.

Final verification resumed on 2026-11-26 using the existing `.venv` from the
repository root:

| Check | Actual result |
|---|---|
| `python -m pytest -q` | 328 passed, 1 skipped, 6 warnings in 82.32 seconds |
| `python -m ruff check .` | All checks passed |
| `python -m mypy --strict` | Success; no issues in 182 source files |
| `python -m pip check` | No broken requirements found |
| `git diff --check` | Passed |

The interrupted run's MyPy log recorded an untyped Torch `unique` call in
the mask fixture assertion. The saved correction enumerates the tensor values
using `tolist`; the resumed checks above verify that correction. Logs are in
`runs/phase11/pytest-resumed.log` and `runs/phase11/mypy-resumed.log`.
Temporary files and type/lint caches were kept under `runs/phase11/` on D:.
The existing `gpu.json` measurements were inspected and reused without
repeating the completed profile or any Phase 10 dataset audit.

The skip requires the unconfigured PostgreSQL/PostGIS integration service.
Warnings are Starlette/httpx, Pygame/pkg_resources, two PettingZoo API
deprecations and two Pillow `getdata` deprecations. They do not establish
PostgreSQL compatibility or real-world model accuracy. The older GPU handoff
now links to these completed PC2 measurements.

Ready for review: modular software, synthetic fixtures, epoch resume and
bounded GPU execution. NOT READY for actual dataset training, real accuracy
claims or operational deployment. The Phase 10J missing frozen evidence
(`simulation/field-v1/manifest.json`), source-version uncertainty, independent
reviews, grouping/leakage issues and empty authorization bundle remain open.
Obtain exact task/release approvals and a separate Phase 11G decision before
actual training. No Model 2 training, Phase 12, physical control, commits,
pushes, downloads, raw modifications or frozen-release changes occurred.
