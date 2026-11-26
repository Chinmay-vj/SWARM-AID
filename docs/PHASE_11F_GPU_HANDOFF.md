# Phase 11F — PC2 GPU handoff

**Status: prepared, not GPU-verified.** This document describes compatibility
checks and synthetic smoke/profile runs only. It does not authorize or start
training.

## Target and storage

Target supplied by the operator: Windows, Python 3.12.10, NVIDIA RTX PRO 4500
Blackwell (32 GB VRAM), 64 GB RAM, Xeon 636 (12 cores / 24 threads), about
1.7 TB available storage, Torch 2.11.0+cu128, TorchVision 0.26.0, and
TorchAudio 2.11.0. Basic CUDA computation was reported as verified by the
operator; this checkout has not independently verified that hardware.

Use the storage policy:

- GitHub: source code and configurations only.
- Google Drive: only permitted dataset/model backups.
- PC2 `D:`: active approved datasets and checkpoints.

Do not copy private alert or review artifacts into the repository. Existing
`.gitignore` exclusions cover datasets, model weights, checkpoints, caches,
temporary files, credentials, and experiment outputs.

## Preserve the CUDA installation

From `D:\SWARM-AID`, in PowerShell, point temporary and cache output to D: and
check the currently installed environment before changing packages:

```powershell
$env:TEMP = 'D:\SWARM-AID-DATA\tmp'
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = 'D:\SWARM-AID-DATA\cache\pip'
New-Item -ItemType Directory -Force -Path $env:TEMP, $env:PIP_CACHE_DIR | Out-Null

.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -c "import torch, torchvision, torchaudio; print(torch.__version__, torch.version.cuda, torch.cuda.is_available()); print(torchvision.__version__, torchaudio.__version__); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CUDA unavailable')"
```

Stop if the active interpreter is not Python 3.12, any installed library
version differs from the intended CUDA stack, or `torch.cuda.is_available()`
is false. Do not run `pip install .[ml]` on PC2 unless the operator has first
confirmed that doing so will preserve the CUDA wheel build. The optional extra
pins versions but does not choose a CUDA wheel index.

## Synthetic GPU verification

Run only after the environment checks pass. These commands create synthetic
inputs and do not access datasets or start a training job:

```powershell
.\.venv\Scripts\python.exe -m evaluation.model1.gpu smoke `
  --device cuda --batch-size 1 `
  --output D:\SWARM-AID-DATA\runs\phase11\gpu-smoke.json

.\.venv\Scripts\python.exe -m evaluation.model1.gpu profile `
  --device cuda --batch-size 8 `
  --output D:\SWARM-AID-DATA\runs\phase11\gpu-profile-b8.json
```

The smoke check performs one synthetic classification optimizer step and checks
TorchVision CUDA NMS. The profile command reports peak allocated and reserved
CUDA memory for that synthetic step. Start with batch size 1; increase only
after reviewing the recorded memory headroom. The example batch size 8 is a
conservative profiling point, not a recommended real training batch size.
Store outputs under the external D: dataset/run root, not in Git.

## Profiles and release verification

The repository includes
[conservative](../configs/model1_training_conservative.json) and
[standard](../configs/model1_training_standard.json) CUDA profiles. Both point
checkpoint and profile paths to `D:\SWARM-AID-DATA`. They are configuration
examples only; do not launch their training loops as part of this handoff.

When and only when a dataset has completed governance and task authorization,
the verification CLI can validate a task-bound release without training:

```powershell
.\.venv\Scripts\python.exe -m evaluation.model1.verify_task `
  --registry D:\SWARM-AID-DATA\manifests\<release>\registry.json `
  --input-manifest D:\SWARM-AID-DATA\manifests\<release>\operational.json `
  --target-manifest D:\SWARM-AID-DATA\manifests\<release>\targets.json `
  --candidate-manifest D:\SWARM-AID-DATA\manifests\<release>\candidate.json `
  --authorization-bundle D:\SWARM-AID-DATA\manifests\<release>\authorization_bundle.json `
  --dataset-root D:\SWARM-AID-DATA --task-id <authorized-task-id>
```

The placeholders are not existing approvals. The current Phase 10I-E1 bundle
has zero records and all 14 readiness tasks remain blocked; the command should
not produce an authorized status for those datasets.

## Handoff boundary

- PC1 CPU-only dependencies and synthetic smoke were verified. PC2 CUDA,
  peak-memory behavior, and the reported target configuration remain
  unverified until the operator runs the commands above.
- Do not download data or weights, modify raw or frozen releases, expose test
  data, train a model, or alter authorization on PC2 as part of this handoff.
- Real-data training remains NO-GO until the independent reviews, governance,
  exact release checksums, and explicit task authorization are complete and
  separately reviewed.
