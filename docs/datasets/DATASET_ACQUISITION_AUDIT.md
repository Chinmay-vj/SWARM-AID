# Phase 10B–10D acquisition audit | 25 November 2026

## Corrected storage location and Phase 10D sensor inspection

The owner subsequently identified the data root as `D:\SWARM-AID\datasets`. The earlier path-not-found findings below concern the previously supplied external path only. The current sensor audit verified four files under `raw/sensors`, totaling 7,929,937 bytes. The registry now has 14 source entries. Smoke Detection IoT has 62,630 rows, UCI has 9,357 hourly records represented twice, and USGS has 36 period summaries. Local availability is verified; release-specific governance is pending. The seven earlier imagery/audio releases have not been re-audited in this sensor-only review. [Sensor validation report](SENSOR_DATASET_VALIDATION_REPORT.md)

**Disposition: blocked at file inspection.** The owner reports seven manual downloads. Both the workspace check and a separate read-only Windows host check failed to resolve `D:\SWARM-AID-DATA`. The host reported path not found for the root and could not enumerate any of the seven specified directories. No other drive directories were searched. Zero inspected releases does not establish zero downloaded bytes.

## Release inventory for review

Paths below are exact owner-supplied locations. For every row, archive names (except the three expected FLAME names), formats on disk, stored bytes, expanded bytes, image/audio counts, release version, download URL, incomplete files, byte duplicates and missing-file lists are **unknown**. Licence and privacy verification are pending for all seven. Labels below are intended tasks or publisher descriptions. Local class lists, annotations and completeness remain unverified.

| Dataset and supplied absolute path | Candidate annotations and classes | Local compatibility and next inspection |
|---|---|---|
| HERIDAL · `D:\SWARM-AID-DATA\raw\rgb\HERIDAL` | RGB person regions, expected COCO export | Pending. Identify full frames versus crops, inspect category IDs, boxes, dimensions, negatives and split manifests. Recover source/export versions and flight/site groups. |
| SARD · `D:\SWARM-AID-DATA\raw\rgb\SARD` | Aerial person boxes, expected COCO export | Pending. Read actual categories and resolutions. Compare image digests, parent frames, flights and sites against HERIDAL. |
| FloodNet · `D:\SWARM-AID-DATA\raw\rgb\FloodNet` | Semantic masks for flooded/dry roads and buildings, water and scene categories | Pending. Count images, masks and unmatched keys per split. Verify pixel IDs, palette and ignore values. |
| RescueNet · `D:\SWARM-AID-DATA\raw\rgb\RescueNet` | Semantic building-damage and road-condition masks | Pending. Inspect original training masks, source class map and dimensional correspondence separately from optional visualizations. |
| FLAME · `D:\SWARM-AID-DATA\raw\rgb\FLAME` | Fire/non-fire image classes and separate fire masks | Classification and segmentation pending independently. Expected Training.zip, Test.zip, Masks.zip. Matching segmentation images may be unavailable. |
| WiSARD · `D:\SWARM-AID-DATA\raw\multimodal\WiSARD` | RGB and thermal human annotations; release-dependent pairing | Edition unresolved. Inspect archive roots, stream counts, flight IDs, authoritative pairing records, timing, and calibration. |
| ESC-50 · `D:\SWARM-AID-DATA\raw\audio\ESC-50` | WAV clips, category/source/fold CSV, environmental and human sounds | Research audio pending. Join metadata and files, check WAV headers, duration, clip rights and official folds. |

## Provenance and governance

The existing Phase 10A registry covers HERIDAL, FloodNet, RescueNet and ESC-50. Its historical download fields predate this owner report. SARD, FLAME and WiSARD lack entries. Add release-specific records when the actual distributions are identified. The registry's status vocabulary has no value for an owner-reported download that is unavailable to the auditor. This report retains that distinction without marking releases available or approved.

| Dataset | Primary source for release matching | Attribution, usage and privacy evidence to resolve |
|---|---|---|
| HERIDAL | [University of Split project authors](https://doi.org/10.1007/s11263-019-01177-1) | Trace any COCO re-export to original terms and citation. Review people and location metadata. |
| SARD | [University of Rijeka project announcement](https://raass.uniri.hr/?p=646) | Identify IEEE DataPort release versus re-export. Retain author credit and review participant, video and location terms. |
| FloodNet | [FloodNet supervised v1.0](https://github.com/BinaLab/FloodNet-Supervised_v1.0) | Publisher identifies CDLA Permissive. Match the archive to that release and preserve its notices. Review private properties and coordinates. |
| RescueNet | [Authors’ data distribution](https://github.com/BinaLab/RescueNet-A-High-Resolution-Post-Disaster-UAV-Dataset-for-Semantic-Segmentation) | The authors identify CC BY-NC-ND for the dataset and request citation of their paper. Match the exact downloaded release, preserve credit and review restrictions on commercial use and sharing adaptations. Review post-disaster properties and locations. |
| FLAME | [Originating research group](https://sites.google.com/g.clemson.edu/is-win-lab/resources/datasets) | Match the first FLAME release, component terms and citation. Check incidental people, property and location disclosure. |
| WiSARD | [University of Washington release page](https://sites.google.com/uw.edu/wisard) | Pin sample/full edition and scope of terms for imagery and labels. Review participant imagery, flight paths and location metadata. |
| ESC-50 | [Author's release and attribution ledger](https://github.com/karolpiczak/ESC-50/blob/master/LICENSE) | The full collection lists CC BY-NC 3.0, with separate terms for ESC-10. Retain dataset and clip credits and source-level terms. Review recognizable voices and redistribution scope. |

For all seven, exact acquisition source and date, applicable media and annotation terms, permitted research use, attribution notices, permissions for derivatives and redistribution, and privacy reviewer decisions require reconciliation with the downloaded release. No sample manifest was fabricated. The Phase 10A validator read 11 candidate entries and zero sample rows. Archive integrity, label quality and cross-release leakage still need file evidence.

See the [storage measurements](DATASET_STORAGE_AUDIT.md), [archive inspection and extraction plan](DATASET_EXTRACTION_PLAN.md), [task and leakage assessment](DATASET_COMPATIBILITY_REPORT.md), and [gap analysis](DATASET_GAP_ANALYSIS.md).

Repository verification from the project root yielded 249 Python tests passed, one skipped and three deprecation warnings. Ruff passed and strict mypy passed across 130 files. The three stored JSON Schemas matched the Phase 10A models. These checks exercised repository code and fixtures; none inspected a downloaded release.
