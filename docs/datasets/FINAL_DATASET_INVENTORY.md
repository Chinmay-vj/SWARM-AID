# Final dataset inventory

All 12 public datasets are BLOCKED for training and CONDITIONAL for private inspection. Original and indexed rows use the unit selected by the source adapter. They exclude metadata, visualization copies and blank CSV lines. Both counts are equal in every row. First-pass quarantine files were empty.

| Dataset and source version | Raw files | Original = indexed | Structurally valid | Supplementary flags | Exact repeats¹ | Raw bytes | Index bytes |
|---|---:|---:|---:|---:|---:|---:|---:|
| CrisisMMD · QCRI 2.0 / 10a5626 | 36,205 | 18,082 | 18,082 | 0 | 2024 | 1,949,568,138 | 10,514,015 |
| ESC-50 · master export, commit unknown | 2,011 | 2,000 | 2,000 | 0 | 0 | 884,047,129 | 453,022 |
| FLAME · unversioned components | 49,995 | 49,995 | 49,995 | 0 | 39 | 1,593,347,032 | 12,859,488 |
| FloodNet · Supervised_v1.0 folder | 7,031 | 2,343 | 2,343 | 0 | 0 | 13,056,205,581 | 780,581 |
| HERIDAL · Roboflow v1 HERIDAL_RAW_V1 | 1,604 | 1,600 | 1,600 | 0 | 0 | 4,441,161,162 | 965,623 |
| HumAID · QCRI three-shard export | 3 | 76,484 | 76,484 | 0 | 6 | 7,223,756 | 15,380,172 |
| RescueNet · unversioned export | 13,483 | 4,494 | 4,494 | 0 | 0 | 23,769,513,801 | 1,375,504 |
| SARD · Roboflow v17 TILES_3x3 | 5,760 | 5,755 | 5,755 | 0 | 0 | 655,254,689 | 2,963,107 |
| Smoke · CSV, edition unknown | 1 | 62,630 | 62,630 | 0 | unmeasured | 5,834,376 | 44,573,563 |
| UCI · CSV + equivalent XLSX | 2 | 9,357 | 9,357 | 0 | unmeasured | 2,083,262 | 6,939,429 |
| USGS · one station export | 1 | 36 | 36 | 0 | unmeasured | 12,299 | 28,616 |
| WiSARD · WiSARDv1 folder, edition unpinned | 100,794 | 56,130 | 54,855 | 1,275 | 27 | 43,571,345,864 | 19,132,381 |

¹ Media bytes or normalized whole text beyond the first occurrence. CrisisMMD repeats refer to text; 18,082 media references have 17,777 distinct byte hashes. FLAME includes 2,003 unpaired masks. WiSARD lacks 11,542 sidecars in addition to its box flags. The UCI workbook contributes zero extra hours. NASA POWER and additional CrisisNLP collections were postponed.

Eleven sources use repository staging under `datasets/raw`. CrisisMMD uses external `raw/multimodal/CrisisMMD`. The [source map](../../evaluation/data/phase10g.py) gives every relative location. Private audit metadata binds each resolved source to its checksum. [Labels and distributions](FINAL_CLASS_BALANCE_REPORT.md) · [Task dispositions](TRAINING_READINESS_MATRIX.md)

| Native source | Original / exported unit | Groups | Storage and status |
|---|---|---|---|
| Model 1 field | 9,465 delivered reports / 9,465 symbolic records | 9,465 distinct observation and report IDs, 72 episodes | Embedded in six field batches. Mock outputs, zero approved. |
| Model 2 pilot-2 | 1,138 delivered envelopes / 510 presentations | 13 episodes, 509 distinct report sets, 505 native and five controlled presentations | 36 files, 6,385,696 bytes. All pending. Mixed reserved pilot restricted to integrity/evaluation. |
| Model 2 field-v1 | 9,465 delivered reports / 4,975 presentations | 72 episodes, 4,969 distinct within-batch report sets, 24 controlled presentations | Six batches, 68,739,396 bytes. All pending. Development previews only. |

Native validators accepted seven batches with zero structural rejects. Duplicate relationships and controlled variants are labeled research cases. Their parents determine independence.
