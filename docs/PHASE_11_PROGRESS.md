# Phase 11 progress - Model 1 development on PC2

## Active: Phase 11G-4C/4D FloodNet

- Final governance update (2026-11-27, supersedes earlier pending-clearance notes):
  chinmay explicitly approved consolidated items 1-5 as owner and reviewer,
  including licence acceptance, residual privacy risks and retention through
  project completion plus 12 months. Typed release authorization:
  `floodnet-pc2-chinmay-20261127T090921Z`. Candidate/input/target/config digests
  unchanged. Mandatory metadata-only readiness exited 0; log:
  `runs/phase11g4/authorized-readiness.log`. No audits, tests or GPU benchmarks
  repeated. Separate training-start approval remains pending; no training started.
  Draft snapshot preserved under `runs/phase11g4/pre-authorization-20261127T090921Z`.

- Resume verification (2026-11-27): existing implementation and saved synthetic GPU
  evidence inspected; no newer clearance record found. Focused pytest rerun: 43
  passed, one existing Starlette warning (34.25 s). Ruff and strict mypy passed
  for the same six changed implementation/test files. Metadata-only readiness
  still exits 1 with `dataset governance review incomplete`, before raw access.
  Consolidated owner clearance requested; no real processing or training started.
  Existing GPU benchmarks reused rather than repeated; all staged work preserved.

- Current request authorizes implementation and synthetic profiling, not full FloodNet training.
- Existing 15 annotation reviews and 45 accepted RGB-only EXIF corrections reused.
- Owner approved excluding 10169 and the limited publisher-partition/single-reviewer scope
  in this conversation; owner name supplied as chinmay. Rights/privacy and source-clearance
  decisions were not supplied and remain pending.
- Local DATASET-VERSION-NOTE-v1.0.txt explicitly confirms numeric mask IDs 0-9;
  publisher README confirms ten categories and CDLA-Permissive-1.0 link.
- Implemented vectorized mask remapping, development-only validation with session integrity
  reuse, atomic lossless cache, opt-in CE+Dice, streaming validation and live logs.
- Focused tests: 43 passed; Ruff and strict mypy passed for six changed/new files.
  CPU and BF16 CUDA segmentation fixture resumes match uninterrupted runs.
- Synthetic actual-model GPU smoke passed; batches 8/16/32 passed. Batch 16 BF16
  recommended (98.10 samples/s; 3.87 GiB reserved in the bounded synthetic probe).
- Draft successor deployed at D:/SWARM-AID-DATA/manifests/phase11g4-floodnet-v1:
  1445 train / 449 validation / 448 reserved test. Readiness gate rejects pending
  governance before raw access. No real processing/training was started.
- STOP for source/rights/privacy clearance, bound release authorization and separate
  explicit start approval. Owner name alone is not clearance. Commands/evidence:
  docs/PHASE_11G4_FLOODNET_PREPARATION_REPORT.md. Do not repeat historical inventories
  or visual reviews. Local launch/preparation helpers are in runs/phase11g4.

**11A-11F software/synthetic validation implemented. Real-data training: NO-GO.**
The user's Phase 11A-11F request explicitly authorizes development, synthetic
optimizer tests and CUDA profiling. It does not authorize dataset training.

- Reused the existing PC1 models, task loaders, metrics and provider interface.
- Added agent-owned temporal context, missing/invalid input handling, Phase 10J
  exclusions in loaders and verifier, epoch resume and checkpoint provenance.
- CPU/CUDA resume equivalence tested, including shuffled batches, dropout,
  accumulation, optimizer/scheduler state, FP16 scaler and RNG restoration.
- Bounded GPU profile completed: 54/54 synthetic cases passed across nine
  components, batches 2/8 and FP32/BF16/FP16. No accuracy claim.
- Configured eight source task profiles; all remain BLOCKED. No raw sources,
  frozen manifests, historical reviews or approvals were changed or rehashed.
- Resumed final verification: 328 passed, 1 skipped, 6 warnings; Ruff,
  strict MyPy (182 files), pip check and diff whitespace checks passed.
  The saved test typing correction is verified; stale GPU handoff status
  now points to measured PC2 results. Prior GPU measurements were reused.

Current results, architecture, commands and remaining gates are maintained in
[Phase 11A-F completion report](PHASE_11A_F_COMPLETION_REPORT.md).

## Phase 11G-3 UCI Air Quality — PC2

The separately authorized UCI Air Quality baseline completed 26 epochs and
early-stopped with epoch 16 selected (validation RMSE 0.972842 mg/m3). The
launcher performance fix reduced the owner-reported epoch duration from 978.10 s
to 0.51 s while preserving live progress and stage timings.

Post-training recovery is now evaluation-only. It restores the selected model
from the integrity-checked epoch-26 checkpoint, evaluates validation data only,
and does not open the reserved test partition. Validation metrics and both
baselines use the same 1,118 valid windows; 80 all-missing windows are excluded.
Whitespace-only trailing timestamps are safely skipped by the shared UCI
preprocessor; malformed timestamps with measurements are rejected explicitly.

See the [UCI Air Quality readiness and training report](PHASE_11G_UCI_AIR_QUALITY_READINESS_REPORT.md)
for measured timings, validation results, command and limitations. The
validation-only summary and all checkpoints remain on D:.

## Phase 11G-8 WiSARD pipeline preparation (2026-11-27)

- Implemented tracked equivalents of the requested helpers in
  `evaluation/model1/{prepare_wisard,detection_cache,wisard}.py`, reusing the
  authorized loader, Faster R-CNN MobileNetV3, AdamW engine, metrics and checkpoints.
  Prepared releases: `D:/SWARM-AID-DATA/runs/phase11g8/prepared-v1/{visual,thermal}`.
  RGB train/validation/test: 9839/3311/3424; thermal: 8218/2514/2563.
- Existing cleaned candidates, partition assignments, annotation reconciliation,
  publisher evidence, owner policy/research decision and GPU benchmark were reused.
  Metadata preparation took 27.87 s. Sidecars were read once per preparation pass
  and checked against the saved ledger; image hashes/dimensions were reused.
  Fixed floating-point edge rounding in normalized YOLO to pixel xywh conversion.
  Publisher class 0 maps to human foreground 1; model class 0 is background.
- Separate models use 512x512 display RGB tensors (including thermal display
  imagery), batch 32, BF16, AdamW LR .001/weight decay .0001, 30 epochs, patience 7,
  seed 2025 and validation mAP50 selection. No augmentation or external weights.
- Atomic uint8 memory-mapped caches bind release/target/authorization/transform
  provenance, verify cache hashes once per opening, detect subsequent file changes,
  and reject test partitions. Existing session integrity verification is retained.
  Real caches are deferred until authorization. Validation shares one backbone
  pass, uses evaluation proposals for metrics and separate sampled head passes
  for diagnostic losses; BatchNorm stays frozen and validation sampling preserves
  RNG. Predictions move to CPU for metrics. No repeated validation backbone pass.
- Verification: focused pytest 30 passed (17.76 s); affected WiSARD tests after
  typing/thermal coverage changes: 5 passed (12.62 s). Synthetic CUDA BF16 uses
  64x64, batch 2, two epochs across a verified resume, not a new GPU benchmark.
  Covered annotation contracts, RGB/thermal loading, cache create/hit/corruption,
  reserved-test rejection, authorization rejection, training/validation, perfect
  metric fixture, checkpoint checksum rejection/resumption and progress fields.
  Strict mypy and Ruff passed for six implementation/test files; pip check passed.
  Final live-terminal end-to-end rerun: 1 passed (12.51 s), with a forwarding
  capture verifying at least ten flushes while showing progress during execution.
  Final strict mypy, Ruff and diff whitespace checks passed.
  Existing Starlette deprecation and CUDA ROI Align nondeterminism warnings remain;
  bitwise GPU resume equivalence is not claimed. No real-data performance result.
- Both deployed metadata readiness commands fail closed with `dataset governance
  review incomplete`, before source image access. Saved preparation approval is
  preserved; empty authorization bundles do not assert review or training approval.
  Genuine bound release authorization and separate owner training-start approval
  remain required. The launcher checks both train and evaluation scopes and binds
  the start decision to owner, authorization, input/target/candidate/config digests.
- Restrictions: local non-commercial academic research, attribution, no cloud
  uploads, raw redistribution or personal identification. Publisher imagery licence
  scope remains ambiguous; no individual permission or definitive legal clearance
  is claimed. Candidates contain positive human annotations only: false alarms are
  not adequately established. Locations are provisional, not verified flight IDs.
  Thermal display imagery is not calibrated temperature; presence is not distress.
- No downloads, raw modifications, test-image decoding, actual WiSARD training or
  commits. An initial incomplete local draft remains ignored at
  `runs/phase11g8/prepared`; only `prepared-v1` is the completed release.

Next step is genuine governance/release review, then metadata readiness (these
commands currently return NO-GO and do not train):

```powershell
.\.venv\Scripts\python.exe -u -m evaluation.model1.wisard --release D:\SWARM-AID-DATA\runs\phase11g8\prepared-v1\visual
.\.venv\Scripts\python.exe -u -m evaluation.model1.wisard --release D:\SWARM-AID-DATA\runs\phase11g8\prepared-v1\thermal
```

After separate start authorization, the same launcher accepts `--execute` and,
for verified epoch-boundary continuation, both `--resume <checkpoint.pt>` and
`--resume-sha256 <trusted-metadata-sha256>`. Do not create approvals from templates
or infer training authority from the preparation decision.

### WiSARD external publisher permission authorization update

- Owner approved the external-permission workflow in this session. Reused the
  newer `publisher_permission.json`, privacy acceptance by chinmay and completed
  sampled annotation review. Original publisher correspondence remains external;
  independent sender authentication is not claimed. No email archive is required.
- Generated both prepared-v1 authorization bundles with exact candidate/input/
  target checksums, owner confirmation, evidence digests and local-use restrictions.
  Registry general licence remains unverified; privacy/review statuses reflect the
  existing accepted review. Historical preparation/permission records are unchanged.
- Both RGB and thermal metadata readiness commands passed (exit 0). Release
  authorization is ready; separate training-start approval remains required by the
  launcher. No training-start record was fabricated and no training was run.
- Focused authorization pytest: 14 passed; Ruff and strict mypy passed (five files).
  Existing Starlette warning only. No dataset audits, image reviews or GPU profiling
  repeated. Full byte integrity checks remain mandatory on actual loader startup.
- Added WiSARD-only external-permission scope, owner and cloud/redistribution
  rejection tests. Existing integrity, checksum and reserved-evaluation tests pass.

### WiSARD explicit training-start approval recorded (2026-11-27)

Owner explicitly approved local RGB and thermal training under the existing
research restrictions. Created and read-back verified `training_start.approved.json`
in both `D:/SWARM-AID-DATA/runs/phase11g8/prepared-v1/{visual,thermal}` releases,
bound to the existing `wisard-{visual,thermal}-external-permission-v1` authorization
IDs and exact candidate/input/target/configuration checksums. Both local-training
and local-evaluation authorization checks passed before either record was written.
Existing restrictions were copied unchanged. No reviews/audits repeated and no
training process launched. Mandatory source integrity checks remain in the loader.

## Phase 11H-C/D/E: preparation only

Added frozen feature adapters for authorized, strictly restored audio/sensor/flood/
fire/damage models (128/128/960/576/960). Adapters inject existing preprocessing,
retain checkpoint/preprocessing/source digests and authorization identity, freeze
parameters and evaluation state, and never load or modify checkpoints. Caller must
supply the verified model and exact authorized preprocessor; no new inference over
real artifacts was performed. WiSARD is excluded.

Separate simulator-only environmental fusion uses existing Engine/sense observations,
named motion/corruption seed streams, and 128-D MissingAwareFusion. Features are
three modality vectors (image/thermal/environment), each containing four weighted
category votes, mean confidence and count. Separate targets are simulator reference
terrain categories: routine/water/fire/damage. IDs, seeds, split and truth never enter
the model. Episode seeds cannot overlap; 42-46 and test splits are rejected. Native,
missing, noisy and injected-conflict variants share their parent episode and target.
All-missing and contradictory evidence abstain; outputs are untrained/uncalibrated.
This is environmental reference classification, not distress or rescue authority.

Generated releases contain inputs.npz, targets.npy, provenance.json and checksum-bound
release.json, cached by configuration/code identity under D:/SWARM-AID-DATA only.
Generation is bounded to 100 episodes/2000 ticks; artifacts are local synthetic data,
not synchronized real multimodal samples. No training or Phase 11H-F work authorized.

Verification: focused pytest 3 passed (1.77 s), strict mypy passed for all three new
Python files, pip check passed. Ruff formatting findings were fixed only in the
new files and the affected Ruff check passed. Existing Starlette warning remains.
Generated a bounded synthetic release under `D:/SWARM-AID-DATA/runs/phase11h/`;
no real checkpoints, reserved test data, training or Phase 11H-F were accessed.
Remaining: real adapter wiring uses caller-supplied authorized preprocessors/models;
symbolic model remains untrained and needs class-coverage and calibration assessment
under separately authorized later work. Routine means other reference terrain,
not a declaration of safety. Frozen real encoder features are not paired with this
symbolic dataset.

Corrected generation to sample all locally sensed cells, rather than only drone
positions. Affected dataset test: 1 passed; affected Ruff/strict mypy passed.
Current release: `dcf48c9339de5c1cfc8e2f85772c8ea88fadc22eab74348b006c3e057d59b02c`
under the environmental-fusion directory. 10,640 examples: 10,636 routine, 4 fire,
zero water/damage. This bounded preparation fixture is NOT training-ready: class
coverage and imbalance remain blockers. Earlier 1,152-row fixture is superseded.
No training was run; no performance or reliability claims are made.

## Phase 11I: pipeline prepared (2026-11-27)

Standalone orchestrator and thermal-detector training block implemented; see PHASE_11I_HANDOFF.md.
Validation-only results: UCI model MAE 0.687920 vs persistence 0.556908 on 1,093 identical samples
(persistence has CO history the model lacks); symbolic fusion stress test shows no neural advantage over
deterministic voting. 28 focused tests, affected Ruff and strict mypy passed. Optimization training has not
run and awaits an owner training-start decision. Phase 11I is not complete.

## Phase 11I and 11J closure (2026-11-27)

Supersedes the "pipeline prepared" note above: the owner-approved optimization ran and Phase 11I completed.
Phase 11J integrated the selected models, structured evidence and deterministic fusion with the simulator and
Model 2: 18 focused tests passed; full suite 374 passed, 1 skipped. Phase 11 is closed within its revised
simulation and validation-only scope. Migration is prepared, not executed; RTX 2060 and reserved-test evaluation
are unverified. See PHASE_11J_COMPLETION_REPORT.md and PHASE_12_HANDOFF.md.
