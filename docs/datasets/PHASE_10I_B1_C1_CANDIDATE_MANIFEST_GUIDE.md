# Phase 10I-B1/C1 candidate manifest guide

## Location and contents

The candidate release is stored privately at
`D:\SWARM-AID-DATA\manifests\phase10i-b1-c1-v1`. It contains:

- `candidate_manifests/`: three versioned JSON descriptors and record JSONL
  files for FLAME classification, ESC-50, and UCI CO forecasting.
- `exclusion_overlays/`: FLAME near-test training paths and ESC-50
  cross-fold-recording paths.
- `source_audit.json`, `coco_annotation_audit.json`,
  `mask_class_distribution.json`, and `sensor_candidate_audit.json`.
- `grouping_and_leakage_audit.json`, `human_review_queue.jsonl`, and
  `governance_evidence.json`.
- `model1_candidate_readiness.json`, `input_bindings.json`,
  `execution.json`, and `checksums.json`.

The checksum manifest covers 18 files and is not self-hashed. Verify every
listed file before inspection. Input bindings include the frozen Phase 10H
release, Phase 10I-A raw-ledger files, registry, source indexes, preparation
code, and the relevant Phase 10G visual audit files.

## Candidate schema and limitations

The JSON descriptors use schema version
`phase10i-candidate-1.0` and artifact kind
`candidate_only_not_approved_training_release`. Each declares:

- `training_approved: false`
- `approved_training_records: 0`
- `human_review_required: true`
- candidate count, partitions, integrity qualification, and input digests

Candidate rows intentionally do not constitute an approved training `Manifest`.
They omit record-level target labels in this stage. The candidate descriptor
type rejects approval, and the existing training-partition safeguards are
unchanged. Do not attach these artifacts to a training loader or treat them as
an authorized release.

Current candidates:

| Descriptor | Records | Qualification |
|---|---:|---|
| `flame-fire-classification-v1.json` | 47,501 | Near-frame exclusions applied; parent video grouping still blocks |
| `esc50-official-folds-v1.json` | 1,991 | Four cross-fold source recording groups fully excluded |
| `uci-co-next-hour-24h-v1.json` | 7,603 | 24-hour lookback / 1-hour horizon; temporal-only, one site |

Candidate paths point to local source records; the candidate artifacts do not
copy or redistribute source media. Preserve the private D-drive boundary and
do not upload them to GitHub. See the [readiness report](PHASE_10I_B1_C1_MODEL1_CANDIDATE_READINESS.md)
before any further pipeline work.
