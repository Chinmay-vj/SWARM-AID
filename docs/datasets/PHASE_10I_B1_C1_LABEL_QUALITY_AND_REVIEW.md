# Phase 10I-B1/C1 label quality and human review

No human annotations, adjudications, or corrected labels were created.
Recorded counts are automated audits, not proof that source labels are true.

## Detection labels

| Source | Indexed images | Boxes | Empty annotation rows | Invalid boxes | Reported class count |
|---|---:|---:|---:|---:|---|
| HERIDAL | 1,600 | 3,194 | 560 | 0 | `person`: 3,194 |
| SARD | 5,755 | 7,424 | 832 | 0 | `human`: 7,424 |

Both exports use category IDs 0 and 1 named `person` or `human`, while boxes
occur under category ID 1. This is an alias/label-policy issue, not permission
to merge labels silently. Empty rows require source-policy review before
being treated as verified negative images. The review queue contains a
deterministic sample, not all 1,392 empty rows.

## Segmentation labels

The audit decoded all 6,837 FloodNet and RescueNet class-index masks. Per-class
pixel and image-presence counts reproduce the frozen Phase 10G visual
summaries. The publisher README class names were used as descriptive metadata;
they were not independently adjudicated. RescueNet damage grades, especially
rare categories, require independent review before use.

## Other label/record quality flags

- FLAME: 491 near-test training frames are listed in an exclusion overlay;
  2,003 masks remain without verified image pairs.
- WiSARD: 1,275 invalid normalized-box flags remain unadjudicated; 11,542
  records lack sidecars. Missing sidecars are not negative labels.
- ESC-50: the four shared-recording groups are excluded, but the audit does
  not relabel sound classes or assert distress semantics.
- UCI: all 16,701 parser-flagged missing cells are retained as missingness
  evidence, including 16,244 `-200`/`-200.0` and 457 `-200,0` sentinels.
  No imputation was proposed.

## Review queue

The private queue contains **152 pending examples**, estimated at **426
reviewer-minutes**:

| Source | Queue entries | Review purpose |
|---|---:|---|
| HERIDAL | 30 | Empty annotation review |
| SARD | 30 | Empty annotation and category review |
| WiSARD | 30 | Flagged normalized-box/source-format review |
| FloodNet | 29 | Deterministic per-class/split mask inspection examples |
| RescueNet | 33 | Deterministic per-class/split mask inspection examples |

Queue records include source-relative paths and pending status only. They are
stored outside Git at
`D:\SWARM-AID-DATA\manifests\phase10i-b1-c1-v1\human_review_queue.jsonl`.
Reviewers should record independent decisions separately, retain provenance,
and avoid turning human presence or environmental audio into confirmed
distress without an appropriate label protocol.
