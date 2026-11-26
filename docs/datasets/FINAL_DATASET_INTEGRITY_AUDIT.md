# Final dataset integrity and leakage audit

**Disposition: NO-GO for training.** This report distinguishes verified local byte/structure checks from unresolved source rights, privacy, semantic quality and human review. The private source files remain on D:; no raw dataset content is included here.

## Registry reconciliation

The 12 indexed sources are HERIDAL, SARD, FloodNet, RescueNet, FLAME, WiSARD, ESC-50, HumAID, CrisisMMD, Smoke, UCI and USGS. Seven map to entries in the frozen Phase 10A candidate registry: HERIDAL, FloodNet, RescueNet, ESC-50, Smoke, UCI and USGS. All seven have unverified licence/verification status and pending privacy status. SARD, FLAME, WiSARD, HumAID and CrisisMMD have no registry entry. The Phase 10G quality manifest pins the registry digest, so this audit records the discrepancy rather than silently changing that historical registry. No source was promoted or approved.

## Public data and leakage findings

The Phase 10G index covers **288,906 first-pass rows** across 12 sources; the 12 first-pass quarantine files were empty. The visual pass scanned 120,317 rows and flagged 1,275 WiSARD records. Quality and leakage results in the frozen indexes include:

- FLAME: 491 training frames are within three difference-hash bits of a test frame; 2,003 masks do not have verified image pairs.
- ESC-50: four recording IDs cross official folds. HumAID: four normalized whole-text keys cross publisher partitions; event IDs are unavailable.
- CrisisMMD: publisher events cross partitions and pooling task views repeats image hashes across splits. Exact-media checks do not exclude perceptual or event overlap.
- Smoke and USGS remain unassigned to independent splits; UCI's draft chronological split needs task-specific lookback purging.
- The acquisition inventory does not establish a signed, task-scoped licence or privacy decision for any public training release.

These are measured risks and source limitations, not evidence that similar records are independent. See the [final leakage audit](FINAL_DATASET_LEAKAGE_AUDIT.md) and [governance audit](FINAL_DATASET_GOVERNANCE_REPORT.md).

## Native episode and evidence exclusion

The Phase 10H native audit was recomputed against the frozen releases and exactly matched its saved checkpoint. It checked 288 field checksums and verified 9,465 Model 1 reports/observations across the six field batches. The expanded field data has zero evidence-ID overlap with the pilot. Pilot evidence UUID reuse crosses partitions in 259 keys; the saved episode-level exclusion overlay removes all 13 affected pilot episodes from pooled development comparisons. Seeds 42–46 remain in pilot test only; development loaders reject protected mixed releases.

The first-look queue has 100 unique pending examples from 69 episodes. The recheck found zero submitted first-look forms, zero adjudications and zero independently reviewed labels. This confirms queue state only; it is not an annotation or approval.

## Raw checksums, loaders and storage

The completed read-only Phase 10H audit covered 216,889 files (89,934,298,892 bytes) across the 12 indexed source roots. All 12 inventory fingerprints matched the Phase 10G source summaries. The source/index digest checks matched **122,350** referenced files; the raw audit does not claim content SHA-256 coverage for every file in the inventory. Source-specific image, mask, audio and CrisisMMD checks remain as recorded in Phase 10G. No source file was changed.

| Source | Inventory files | Bytes | Referenced content hashes matched |
|---|---:|---:|---:|
| CrisisMMD | 36,205 | 1,949,568,138 | 19 |
| ESC-50 | 2,011 | 884,047,129 | 2,002 |
| FLAME | 49,995 | 1,593,347,032 | 49,995 |
| FloodNet | 7,031 | 13,056,205,581 | 2,343 |
| HERIDAL | 1,604 | 4,441,161,162 | 1,603 |
| HumAID | 3 | 7,223,756 | 3 |
| RescueNet | 13,483 | 23,769,513,801 | 4,494 |
| SARD | 5,760 | 655,254,689 | 5,758 |
| Smoke | 1 | 5,834,376 | 1 |
| UCI | 1 | 785,065 | 1 |
| USGS | 1 | 12,299 | 1 |
| WiSARD | 100,794 | 43,571,345,864 | 56,130 |

All 12 public loader previews decoded successfully in the current Python 3.12 environment. The check opened one-record and two-record batches for every source: RGB, thermal, paired image/text, WAV, sensor, COCO and segmentation paths were exercised as applicable. All six field releases and the pilot passed the recomputed native audit; Model 1 and Model 2 preview loaders returned valid batches, and protected seeds remained rejected. The declared Pillow and DuckDB packages were restored to the D-drive virtual environment with package caching disabled.

The release manifest records D: capacity 456,782,770,176 bytes and 279,997,775,872 bytes free (260.77 GiB), above the 20 GiB reserve. External-root storage includes 1,949,568,138 raw bytes, 191,090,593 processed bytes, 22,843,943 manifest bytes, 433,295 annotation bytes, 3,463,652 simulation bytes and a 178,819,525-byte local cache. The repository-local D-drive raw tree contains another 87,986,028,951 bytes.

**Storage measurement is partial.** Access to `D:\SWARM-AID\datasets\processed\model2\pilot-1` was denied. The release manifest marks the repository `processed` total as `partial` and records that path; no total for that tree is claimed. The D-drive storage directory was not altered to work around the ACL.

## Important-alert review limitation

The existing [final alert-preservation report](../research/FINAL_ALERT_PRESERVATION_AUDIT.md) reports 1,163 matched observations, 203 individual-only reports and 44 same-cell cases requiring independent review. This run could not re-read or recompute the private alert journals: Windows denied access to `runs/phase10g-alert-v2` and `runs/phase10h-alert-v1`. The report's conclusions are therefore preserved as prior audit findings, not represented as independently revalidated here. The 44 cases remain pending human review; no missed-rescue rate is inferred.

## Release status

The machine-readable audit is frozen at `D:\SWARM-AID-DATA\manifests\phase10h-v1\release.json` (SHA-256 `81b0ed436ce8e2bc3ec260f85a87dc89c28f95dc585e3309d8ae3e88c57e11b8`). It binds 19 D-drive evidence files and 41 repository code/configuration files. Freeze and `--verify` both passed. The manifest itself records the partial storage measurement described above.

There are zero approved records for each of the 20 planned learning tasks. Public and native training remain **BLOCKED**. Preview-only CPU inspection is conditional and is not training authorization. The overall training decision is **NO-GO**. See the [training readiness matrix](TRAINING_READINESS_MATRIX.md) and [dataset release manifest](DATASET_RELEASE_MANIFEST.md).

## Phase 10I-A addendum

The Phase 10I-A follow-up preserves every Phase 10H measurement above as
historical evidence. Its current per-file hash classification and coverage,
including any changed inventory fingerprints or inaccessible files, is
reported separately in
[`RAW_INTEGRITY_COVERAGE_REPORT.md`](RAW_INTEGRITY_COVERAGE_REPORT.md).
The additive typed registry, Windows access diagnosis, and current native
exclusion/seed checks are summarized in the
[Phase 10I-A completion report](../PHASE_10I_A_COMPLETION_REPORT.md). No
training approval or human annotation was added.
