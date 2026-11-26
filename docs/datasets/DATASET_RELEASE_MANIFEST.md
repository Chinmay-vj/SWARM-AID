# Phase 10H dataset release manifest

## Frozen audit release

The private, machine-readable manifest is `D:\SWARM-AID-DATA\manifests\phase10h-v1\release.json`. It records the audit version, task dispositions, overall decision, zero approved training records, evidence-file checksums, repository code/configuration checksums, storage totals, D: free-space snapshot, and the UCI workbook digest/ZIP integrity result.

The frozen file is 18,025 bytes with SHA-256 `81b0ed436ce8e2bc3ec260f85a87dc89c28f95dc585e3309d8ae3e88c57e11b8`. It binds 19 D-drive evidence files and 41 repository code/configuration files. Freeze and `--verify` both passed. The storage table explicitly records the repository `processed` total as partial because access to `datasets\processed\model2\pilot-1` was denied; no ACL workaround was used.

This is an **audit manifest**, not a training approval or a distributable dataset. It indexes existing files in place; it does not copy, transform, upload or alter raw source data. The six `field-v1-*` releases and `pilot-2` remain governed separately. Protected pilot evaluation partitions are excluded from development loaders.

## Evidence bound by the manifest

The release command binds:

- Per-source Phase 10H raw content/inventory checks, the Phase 10H public-loader/split audit and the native episode/split audit.
- The Phase 10G combined quality index, CrisisMMD decode summary and task-view index.
- The field simulation and annotation-queue manifests.
- Dataset registry and task configuration, field matrix, Model 2 pilot configuration, field scenarios and experiment plans.
- Every `evaluation/data/*.py` audit module and the storage/file totals present at freeze time.

Per-source raw paths and hashes remain in the D-drive private manifest tree. The 12 inventory fingerprints matched; referenced content checksums matched for 122,350 source files. This is not a content checksum for every file in the raw inventory. Protected evaluation examples, private annotations and imagery are not reproduced here.

## Gate and verification

Run from the repository root with the approved Python environment, setting `TEMP` and `TMP` to a directory on D:.

```powershell
.\.venv\Scripts\python.exe -m evaluation.data.final_release --root D:\SWARM-AID-DATA
.\.venv\Scripts\python.exe -m evaluation.data.final_release --root D:\SWARM-AID-DATA --verify
```

The freeze refuses a non-D: root, less than 20 GiB free, an existing release directory, incomplete or mismatched audit evidence, changed public source scope, or any task disposition that is not `BLOCKED` with zero approved records. Verification rechecks the frozen task file and every evidence/code/configuration checksum. The current gate is **NO-GO for training**. Review-only previews do not change that gate.

No human annotations, rights approvals, group identities or training records are inferred by this manifest. See the [final training matrix](TRAINING_READINESS_MATRIX.md), [final integrity audit](FINAL_DATASET_INTEGRITY_AUDIT.md) and [Phase 10H completion report](../PHASE_10H_COMPLETION_REPORT.md).
