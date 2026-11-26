# Phase 10G processing and verification

26 November 2026. The external release root is `D:/SWARM-AID-DATA`. This phase produced review indexes and validation evidence. Public training approvals stand at zero. Source rights, privacy decisions, split independence and human adjudication remain open.

## Recovery checkpoint

All 12 extracted sources already had published `processed/phase10g-v1/<source>` directories. All six visual sources had supplementary scan summaries, frame-hash files and flags in `manifests/phase10g-visual-v1`. The field review queue and matched alert audit also existed. The missing combined quality manifest and the unverified CrisisMMD pixel decode were the remaining data checks. Recovery reused the original partitions, index versions and raw assets. The prior diff-size estimate was not used to decide which jobs to rerun.

## Public-source coverage

The row count is the number admitted to the first-pass review index. Each of the 12 first-pass quarantine files had zero rows. The supplementary visual pass checked every indexed row of the six visual sources, including FLAME's mask-only component.

| Source | Indexed rows | Verification result |
|---|---:|---|
| HERIDAL | 1,600 | 3,194 boxes and 560 images with empty annotation lists. All images decoded. |
| SARD | 5,755 | 7,424 boxes and 832 images with empty annotation lists. All images decoded. Empty lists in either collection lack independent negative labels. |
| FloodNet | 2,343 | Checked every paired mask's dimensions and class indices 0–9, covering 28,857,531,648 pixels. |
| RescueNet | 4,494 | Checked every paired mask's dimensions and class indices 0–10, covering 53,993,387,520 pixels. |
| FLAME | 49,995 | 39,375 training frames, 8,617 test frames and 2,003 unpaired mask files. Unverified mask pairing excludes those files from paired previews. |
| WiSARD | 56,130 | 1,275 records flagged by the full sidecar check. The review loader excludes flagged paths. RGB/thermal synchronization and registration remain unverified. |
| ESC-50 | 2,000 | WAV payloads read against declared frame counts. Four source recording IDs occur in multiple official folds. |
| Smoke | 62,630 | Indexed source alarm and grouped measurements. Related sequences constrain temporal splits. |
| UCI | 9,357 | The CSV contains 16,244 literal `-200` cells and 457 spelled `-200,0`. Numeric sentinel masking preserves all 16,701 as missing. |
| USGS | 36 | Preserved period summaries, units and 10 missing measurements. |
| HumAID | 76,484 | Four normalized whole-text keys cross publisher partitions. Event identifiers are unavailable. |
| CrisisMMD | 18,082 | Event-level post/image records. The three publisher tasks supply 39,690 additional views of those records. |

The FLAME frame scan found 491 training frames within three difference-hash bits of at least one test frame. This counts training frames, not independent flights or confirmed duplicates. Use the publisher partition labels for traceability. FLAME, ESC-50, HumAID and CrisisMMD have measured overlap risks. Unknown flight, site and event identity also limits independence claims for the visual sources. [Source label mappings](datasets/DATASET_LABEL_MAPPING.md) · [Split policy](datasets/DATA_LEAKAGE_PREVENTION.md)

## Frozen field release and independent review

The operational replay indicates that 59 of the 100 queued examples have an incomplete focal report. Missing modalities are visible to the reviewer. The evaluator's same-cell references stay outside the blinded queue.

The saved Phase 10F verification covered 288 checksums across 72 episodes, with 9,465 Model 1 reports and 4,975 pending Model 2 examples. The field split contains 3,321 training-partition and 1,654 validation-partition candidates. The field and pilot share zero sample IDs or evidence IDs, while 20 field examples repeat a simplified development-pilot presentation pattern. Seeds 42–46 remain reserved. [Field release](PHASE_10F_FIELD_REPORT.md)

The blinded batch contains 100 pending examples from 69 episodes. The queue SHA-256 is `46f4b4e8da20bd563d1d7997039447e308e0694bea69abb97bded903a2e90d25`. There are zero paired human judgments, so reviewer agreement is unavailable. The preserved matched audit covers 1,163 reports. Individual-mode updates alone cited 203, including 44 possible-human reports with a same-cell evaluator reference. Those 44 require independent review. They count reports and do not establish missed rescues. The matched journal checksum agreed with its saved summary. [Independent review instructions](datasets/HUMAN_ANNOTATION_QUEUE_REPORT.md) · [Alert preservation audit](research/ALERT_PRESERVATION_AUDIT.md)

## Combined quality and split verification

All 12 source inventory fingerprints (relative path, size and modification time), processing code hashes, index hashes and quarantine hashes matched their saved summaries. The six visual audits matched the index and scanning code identities, flag files, frame-hash files and expected row counts. The cross-source pass verified the recorded source-table digests and loaded one preview from every public index and three records each through the native Model 1 and Model 2 loaders. These checks establish checkpoint continuity. The inventory fingerprint does not authenticate original media against a publisher.

* FloodNet and RescueNet each had zero unmatched class-index masks. WiSARD had 11,542 frames without an annotation sidecar, in addition to the 1,275 flagged for invalid normalized boxes.
* All 17,777 distinct CrisisMMD image byte hashes decoded across 18,082 event references. Zero matched any indexed image digest in the other six visual sources. The six sources also shared zero exact media keys with each other. Perceptual or event overlap is still possible.
* The published task-view file contains 39,690 rows. Readback reproduced the per-task and per-split counts. Pooling tasks puts 7,605 image hashes under multiple split names. HumAID and CrisisMMD share zero normalized whole-text keys, while the earlier passage audit identified 220 HumAID rows for review. [CrisisMMD compatibility](datasets/CRISISMMD_COMPATIBILITY_REPORT.md)
* UCI's draft chronological split contains 6,558 train, 1,392 validation and 1,407 test rows. Grouping related Smoke sequences and overlapping USGS periods left all 62,630 Smoke and 36 USGS rows unassigned. USGS had four repeated station/time/parameter/period keys. These summaries retain their source statistics. No learned transform was fitted.

## Storage and reproducibility

| External artifact directory | Bytes |
|---|---:|
| `processed/phase10g-v1` | 115,965,501 |
| `manifests/phase10g-visual-v1` | 5,496,939 |
| `manifests/phase10g-v1` | 17,125,579 |
| `manifests/phase10g-crisis-decode-v1` | 512 |
| `annotations/model2/phase10g-field-v1` | 433,295 |

The public indexes and audit manifests total 138,588,531 bytes, within the 1,024 MiB index budget. The final D-drive check measured 280,054,870,016 bytes free, above the 20,480 MiB reserve. The two private files in `runs/phase10g-alert-v2` occupy a further 1,007,630 bytes. The 12 saved source indexing times sum to 5,162.25 seconds, excluding supplementary scans and recovery. [Raw inventory and storage policy](datasets/DATASET_STORAGE_REPORT.md) · [Reproduction commands](datasets/DATASET_PREPROCESSING_SPECIFICATION.md)

| New artifact | SHA-256 at readback |
|---|---|
| `manifests/phase10g-v1/quality.json` | `38b7e87d60757e3ad4b709b236f6fb49e183c9c7c6a0568a25a618123a024b95` |
| `manifests/phase10g-v1/crisis-task-views.jsonl` | `3791b413ce189ddb922d0a6da00aaf34ec25095207ce1f71d65cd93a344de9be` |
| `manifests/phase10g-crisis-decode-v1/summary.json` | `afea52e3120f1c70de5109159fbda6617f25393f5cc8d4fb87f7883a066f712b` |

## Regression verification

From the repository root, pytest reported **270 passed, one skipped and three deprecation warnings** in 144.47 seconds. The PostgreSQL/PostGIS integration test skipped because `SWARM_TEST_POSTGRES_URL` was unset. Ruff passed. Strict mypy passed across 153 source files. Regression coverage includes a corrupted CrisisMMD image fixture, repeated references, exact cross-source matches and protection of existing output. The release ran no model training or Phase 10H work.
