# Phase 10I-B corrective task inventory

This is a handoff inventory only. Phase 10I-B has **not** started. No split
reconstruction, data modification, model training, rights approval, annotation
or dataset release was performed. The machine-readable source of truth is
[`phase10i_b_tasks.json`](../../configs/datasets/phase10i_b_tasks.json).

| Source(s) | Blocker to resolve | Existing metadata that may help | Constraint |
|---|---|---|---|
| HERIDAL, SARD | Parent-flight/site grouping; interpretation of empty annotations | Per-image COCO IDs, categories, boxes and source splits; SARD 3x3 tile export names; publisher/export documentation | Do not infer parent IDs or treat empty labels as negatives without evidence. |
| FLAME | 491 train frames near test; 2,003 masks without verified image pairs | Frame filenames, source split/task labels, mask paths, local component directories and original FLAME release documentation | Do not pair from filename similarity alone or reconstruct large splits in 10I-A. |
| FloodNet, RescueNet | Site/event grouping | Source image paths, publisher split, class IDs, mask associations, publisher acquisition metadata | No site/event key is verified in the reviewed index. |
| WiSARD | 1,275 flagged records; zero verified RGB-thermal pairs | Sequence folders, modality, paired flag, sidecar annotations, possible source timestamps/calibration/synchronization records | Folder names do not prove synchronized/calibrated pairs; do not invent capture identities. |
| ESC-50 | Four recording IDs span official folds | Official metadata CSV `filename`, `fold`, `src_file`, `take`, and class fields | Preserve publisher folds; group complete source recordings. |
| HumAID | Four normalized whole-text keys cross partitions; row event/post IDs absent | Parquet shard partition names, text and label columns, QCRI dataset card | Do not infer event or author identity from text. |
| CrisisMMD | Events cross partitions; pooled tasks repeat post/image media | Seven event TSVs, event and post/image references, task labels, source splits, local image hashes | Select a task and resolve rights before any grouped evaluation/release. |
| Smoke Detection IoT, USGS | Missing split assignments | Sensor timestamps/channels/alarm target; USGS station, parameter and qualifier metadata; source project/API documentation | No split policy is approved; do not assign in 10I-A. |
| Smoke Detection IoT, UCI, USGS | Prediction horizon, units and window overlap are not specified | CSV headers/time fields, UCI data dictionary and missing sentinel, Smoke project/schema documentation, USGS parameter/qualifier metadata | Define causal horizons and purge shared measurements only after 10I-B authorization. |

Every item is `NOT_STARTED`, with `training_approved=false` and
`large_scale_split_reconstruction_allowed=false`. Read the JSON for detailed
evidence, source fields and future actions. This inventory does not make
identifiers, group assignments, publisher permissions or independent
assessments.
