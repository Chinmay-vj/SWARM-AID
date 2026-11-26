# Phase 11G-3: UCI Air Quality readiness

PC2, 26 November 2026. **Training status: GO.** The UCI predecessor candidate
has been corrected and prepared as a separately governed release. Rights/privacy,
exact task authorization and separate training-start approval were recorded by
the owner. This readiness snapshot predates model execution; one authorized
training epoch was subsequently completed. No test-partition model selection
has occurred.

## Completed preparation

- Reused the existing Phase 10G UCI index and Phase 10I-B1/C1 candidate audit.
- Did not repeat the full Phase 10 dataset audit or rehash the raw collection.
- Reused the existing audited CSV SHA-256:
  `13277ae5d8581e80b7be09d47c7d3d06fe9b8e957078f2cf6e859f955e62f996`.
- Corrected the historical 25-row window representation to exactly 24 input
  hourly rows. Historical releases and the ESC-50 release were not modified.
- Excluded target/reference-analyzer fields `CO(GT)`, `NMHC(GT)`,
  `C6H6(GT)`, `NOx(GT)` and `NO2(GT)` from model inputs.
- Preserved explicit missingness from `-200` sentinels and decimal-comma
  `-200,0` values as availability masks.
- Fitted normalization statistics only on 5,052 training windows.
- Verified zero source-row overlap across train, validation and test windows.

## Verified release

Release:
`D:\SWARM-AID-DATA\manifests\phase11g3-uci-air-quality-v1`

| Partition | Windows | Target mean mg/m3 | Target range mg/m3 |
|---|---:|---:|---|
| Training | 5,052 | 2.1380 | 0.1–11.9 |
| Validation | 1,198 | 2.4460 | 0.1–9.9 |
| Reserved test | 1,353 | 1.9818 | 0.1–8.4 |

The 7,603 windows match the previously reported local candidate counts.

Final canonical bindings:

- Candidate: `a571518465613b2cac1ded3b598d5a99d192d311ffc0e077d84489a78eeec5f3`
- Operational manifest: `4506ca8d133bc4dc7a30b91a183dc6166aeabb6a89eb1729c817402caf4db1ba`
- Target manifest: `18a18776ecd31bbb57332ee8a026e3653752d6b2c8b8d46ca71440e1a303263a`
- Training config: `296076257292906450046a830ea360a08d6983bcccb7c5506474b96fd502f10e`

Input features:

| Feature | Unit |
|---|---|
| PT08.S1(CO) | instrument response |
| PT08.S2(NMHC) | instrument response |
| PT08.S3(NOx) | instrument response |
| PT08.S4(NO2) | instrument response |
| PT08.S5(O3) | instrument response |
| T | degC |
| RH | percent |
| AH | native absolute-humidity scale |

Target: next-hour `CO(GT)` reference-analyzer concentration in mg/m3.

The official UCI page lists CC BY 4.0 while separately stating that use is
exclusively for research and commercial use is excluded. The conflict remains
recorded, and no more-permissive interpretation was assumed.

## Reused infrastructure

- `CandidateManifest`, `Manifest`, `Registry`, `Annotation`, `Sample`
- `AuthorizedTaskDataset` and `fit_sensor_normalization`
- `SensorSequenceModel`
- `RegressionTask`, `regression_metrics`, checkpoints and authorization gates
- Existing canonical manifest digest and candidate checksum utilities

## Model and training configuration

Model: 24-hour, 8-feature GRU with 128 hidden units and a one-value regression
head. Loss: Huber loss, delta 1.0 mg/m3, chosen because it reduces the influence
of outlier hourly concentrations relative to MSE. Optimizer: AdamW, learning rate
0.001, weight decay 0.0001, gradient clipping 1.0. Batch size 64, 50 epochs,
patience 10, seed 2025, BF16 CUDA, eight-GiB allocator budget and epoch
checkpoints.

Validation RMSE selects the best checkpoint. The reserved test partition was
not loaded or evaluated during the validation-only recovery and remains reserved
for a separately authorized final evaluation.

Baselines: persistence (previous hour CO(GT)) and a constant training-target mean.

Progress will be visible in the launcher with initialization, authorization,
dataset loading, epoch, train loss, validation loss, MAE, RMSE, duration, ETA
and best-checkpoint updates.

## Rights, privacy and limitations

The dataset page is at
`https://archive.ics.uci.edu/dataset/360/air+quality`, with DOI
`10.24432/C59K5F`. Attribution is required by the stated CC BY 4.0 terms, while
the research-only/commercial-exclusion wording may impose a narrower restriction.
This release therefore keeps rights and redistribution unresolved.

Privacy is limited to a stationary roadside monitoring site. The local CSV is
retained on D:, no cloud processing or redistribution is authorized, and no
identifiable person review is needed for the numerical dataset. Retention,
attribution and use scope require explicit owner clearance.

Limitations include: source clock timezone is not explicit, AH units are
unresolved in the variable description, one site is insufficient for geographic
generalization, and these stationary urban measurements must not be presented as
drone sensor calibration or disaster/toxic-environment evidence.

## Automated validation

- 32 focused UCI, authorization, preprocessing and sensor-model tests passed.
- Strict MyPy passed for the modified UCI/preprocessing/training files.
- Ruff passed for the modified UCI and sensor/model files.
- Python compilation passed.
- Candidate windows: 7,603; 24 rows each.
- Cross-partition raw-row overlap: zero.
- Synthetic CPU/Model 1 Huber forward/backward pass passed.
- Synthetic CUDA batch-64 forward/backward pass passed; peak allocated memory
  36.2 MiB for this small probe.
- Check-only launcher passed compilation and rejected the pending release at
  `dataset governance review incomplete`, before Torch/data loading/training.

## Files created or modified

Automated preparation code:

- `runs/phase11g3/prepare_uci_release.py`
- `runs/phase11g3/launch_uci.py`

Release files:

- `D:\SWARM-AID-DATA\manifests\phase11g3-uci-air-quality-v1\candidate.json`
- `candidate_records.jsonl`
- `operational.json`
- `targets.json`
- `uci-co-targets.csv`
- `registry.json`
- `preprocessing.json`
- `partition_stats.json`
- `exclusions.json`
- `provenance.json`
- `rights_privacy_review.template.json`
- `authorization_requirements.json`
- `authorization_bundle.json`
- `training_config.json`
- `training_start.template.json`
- `validation.json`
- `checksums.json`

Modified shared model code:

- `evaluation/data/model1_prep.py`: corrected UCI candidate source rows to 24.
- `evaluation/model1/data.py`: retained test-split loader support.
- `evaluation/model1/training.py`: Huber-loss option and optional flushed
  epoch progress.
- `evaluation/data/validation.py`: row-scoped sensor windows may share a source
  file without being treated as cross-split content.
- `tests/unit/test_model1_prep.py`
- `tests/unit/test_phase11_model1.py`

## Initial duration estimate

Assuming 79 train batches per epoch, 50 epochs and no substantial data-I/O
change, the tiny GRU likely requires minutes rather than hours on the RTX PRO
4500. A conservative planning range is 5–30 minutes; this is an assumption,
not a benchmark. It is superseded by the measured follow-up below.

## Owner decisions

The owner approved the restrictive UCI research-use interpretation,
attribution/privacy/retention scope, not-authorized cloud processing,
not-authorized redistribution, exact local training/evaluation authorization,
and separate training-start approval. The completed records are on D drive.

## Performance optimization follow-up

The authorized first epoch took 978.10 seconds. Its preserved checkpoint is
`D:\SWARM-AID-DATA\checkpoints\phase11g3-uci-air-quality\run-001\authorized-training\epoch-0001.pt`,
with SHA-256
`04c922b60fdf1dbc6cd47d0443442e8aa4f22f69299184d6462cef55961f70ce`.
Its sidecar digest matches. The full run was not restarted or resumed during
the optimization benchmark; it was subsequently resumed by the owner from the
epoch-1 checkpoint and stopped at epoch 26.

### Measured cause and changes

Before optimization, an authorized runtime probe measured three individual
sample loads at 0.1658, 0.1630 and 0.1634 seconds. The sensor loader reparsed
the complete UCI CSV for every temporal window. Applying the measured mean
(0.1641 seconds) to all 6,250 train and validation windows predicts about
1,025 seconds of CSV parsing per epoch, consistent with the reported 978.10
second epoch. This is measured sample cost extrapolated to the epoch, not a
stage trace from the historical run.

The loader now indexes the source CSV once per process, materializes each
authorized temporal window once, and caches normalized sensor tensors. The
normalization statistics remain fitted only on training windows. Regression
validation now reuses a single forward pass for prediction and loss. Training
progress reports batches and ETA, and epoch logs include loader, transfer,
forward/loss, backward/optimizer, validation and checkpoint stage timings.
The approved training configuration and its SHA-256 remain unchanged.

### Corrected short benchmark

The benchmark used the existing authorization and owner-start approval, ten
training batches and three validation batches. It did not load or access the
reserved test partition; the partial validation metrics are diagnostic only
and were not used for model selection.

- Dataset counts: 5,052 train and 1,198 validation windows.
- Train and validation dataset construction: 32.34 and 15.63 seconds. These
  include integrity validation; the complete CSV parse itself took 0.176
  seconds and the process cache recorded one miss and one hit.
- Train-only normalization and cached normalization setup: 0.177 seconds;
  resulting statistics matched the approved preprocessing record.
- Ten-batch training wall time: 0.619 seconds; DataLoader wait/batch
  construction was 0.0094 seconds total.
- Three-batch validation wall time: 0.084 seconds; DataLoader wait was 0.0030
  seconds total.
- CUDA event totals over ten training batches: host-to-device 0.0026 seconds,
  forward/loss 0.3001 seconds, backward/optimizer 0.3025 seconds. Validation
  forward/loss was 0.0790 seconds over three batches.
- Benchmark checkpoint serialization: 0.132 seconds.
- Device/runtime: NVIDIA RTX PRO 4500 Blackwell, CUDA 12.8, PyTorch 2.11.0;
  BF16 was supported. CUDA peak allocated memory was 40.5 MiB, below the
  configured 8-GiB cap. `nvidia-smi` point samples showed 2–7% utilization;
  CUDA event timings independently confirm the model executed on the GPU.

The measured short-run projection is 5.55 seconds per full epoch, including
validation and checkpoint serialization. That projects to 277.7 seconds for
the full 50-epoch budget or 272.1 seconds for epochs 2–50 from the preserved
epoch-1 checkpoint, before launcher integrity/dataset initialization. This is
an extrapolation from ten train and three validation batches, not a full-epoch
measurement; early stopping may shorten the run. The two measured train and
validation dataset initializations alone took 48 seconds.

The final profile and its separate benchmark-only checkpoint are under
`D:\SWARM-AID-DATA\runs\phase11g3-uci-air-quality\performance-profile-001`.
The original epoch-1 checkpoint and sidecar remain byte-for-byte unchanged.

### Completed training and validation-only recovery

The owner resumed the authorized run from epoch 1. It stopped at epoch 26 after
10 stale epochs; epoch 16 was selected at validation RMSE 0.972842 mg/m3 after
2,054 optimizer steps. The original epoch-1 and epoch-16 checkpoints, the
epoch-26 recovery checkpoint and their digest sidecars remain intact. Total
wall-clock duration was not persisted; the summary leaves it null rather than
inventing a total.

The post-training failure came from whitespace-only `Date`/`Time` cells in
trailing UCI CSV records. The shared `sensor_rows` parser now skips rows with no
timestamp and no valid measurements, while nonblank malformed timestamps and
timestamp-less rows containing measurements raise explicit errors. Baseline
evaluation no longer reparses or joins the raw CSV by timestamp: it reuses the
authorized dataset's cached source-row index and validation samples.

The epoch-26 checkpoint was integrity-checked and its saved best state restored;
no training was run. The model validity mask identified 1,118 usable validation
windows and excluded 80 all-missing windows. Model and baseline metrics use
exactly the same 1,118 target records. Persistence uses the previous `CO(GT)`
reading from the last historical source row, falling back to the training mean
for 25 windows with no previous CO reading. Normalization remains fitted only
on the training partition. The reserved test partition was not loaded or
evaluated by this recovery.

| Validation result | MAE mg/m3 | RMSE mg/m3 | R2 |
|---|---:|---:|---:|
| Selected model, epoch 16 | 0.6833 | 0.9728 | 0.6237 |
| Training-mean baseline | 1.2254 | 1.6039 | -0.0228 |
| Persistence baseline | 0.5772 | 0.8573 | 0.7078 |

Selected-checkpoint validation Huber loss is 0.364215. Training loss at the
best epoch was 0.149029. The persistence baseline outperforms the model on this
validation partition; that result is retained without reinterpretation. The
full 26-epoch history and full-precision validation results are in
`D:\SWARM-AID-DATA\runs\phase11g3-uci-air-quality\run-001-validation-only\summary.json`.

### Measured training performance

The first epoch took 978.10 seconds because the original sample loader reparsed
the complete source CSV for each temporal window. Caching the indexed source
rows, temporal windows and normalized tensors reduced that redundant work;
the owner-reported epoch-26 duration was 0.51 seconds (about 1,918x faster than
the first epoch). Live batch/epoch progress, flushed ETA, and stage timings
remain enabled.

Epoch 26 reported: loader wait 0.047 s, host-to-device 0.028 s,
forward/loss 0.130 s, backward/optimizer 0.197 s, validation 0.022 s and
checkpoint save 0.064 s. These stage durations are from the epoch log. The
separate ten-train-batch/three-validation-batch CUDA benchmark projected 5.55
seconds per full epoch; it was a conservative short-run projection and is
superseded by the measured 0.51-second epoch. CUDA event profiling confirmed
GPU execution, with 40.5 MiB peak allocated memory in the benchmark. Dataset
initialization for the validation-only recovery took 32.38 s for train and
16.10 s for validation, including integrity checks.

### Focused verification and recovery command

- 25 focused Model 1, UCI preprocessing, baseline and finalizer tests passed.
- Ruff and strict MyPy passed for the modified implementation files.
- The gated launcher passed check-only authorization validation.
- The actual validation-only recovery logged `no training will run`, loaded
  only train and validation datasets, and wrote a summary with no reserved-test
  metrics.
- The epoch-16 and epoch-26 checkpoint SHA-256 sidecars were verified.

The evaluation-only recovery command (it does not retrain or open the reserved
test partition) is:

```powershell
& 'D:\SWARM-AID\.venv\Scripts\python.exe' 'D:\SWARM-AID\runs\phase11g3\launch_uci.py' `
  --release 'D:\SWARM-AID-DATA\manifests\phase11g3-uci-air-quality-v1' `
  --root 'D:\SWARM-AID-DATA' `
  --start-approval 'D:\SWARM-AID-DATA\manifests\phase11g3-uci-air-quality-v1\training_start.approved.json' `
  --finalize-checkpoint 'D:\SWARM-AID-DATA\checkpoints\phase11g3-uci-air-quality\run-001\authorized-training\epoch-0026.pt' `
  --summary-root 'D:\SWARM-AID-DATA\runs\phase11g3-uci-air-quality\run-001-validation-only' `
  --execute
```
