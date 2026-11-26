# Phase 10I-A registry reconciliation

## Result

The Phase 10A registry remains unchanged. The Phase 10H-pinned file
`configs/datasets/registry.json` is historical evidence and continues to describe
the candidate registry as it stood at that release.

The additive, typed registry snapshot is
`configs/datasets/registry.phase10i-v1.json`. It validates against the existing
`Registry`/`Dataset` Pydantic contracts and `registry.v1.json` schema. It contains
the original 14 entries and five added public-source entries, for 19 total.
Twelve indexed public sources are marked locally available in this snapshot;
four pre-existing acquisition statuses were updated from stale
`not_downloaded` to `available` based on their verified Phase 10G indexes.
No entry was deleted.

The five previously missing source identifiers are **SARD**, **FLAME**,
**WiSARD**, **HumAID**, and **CrisisMMD**. Their exact local roots and
source-specific metadata are recorded below. A directory inventory or source
index does not establish a publisher release version, rights, privacy approval,
or training suitability.

## Added entries

| Dataset / registry ID | Source version in registry | Local source path | Modality; annotation formats; supported task candidates | Existing source metadata | Split / integrity |
|---|---|---|---|---|---|
| SARD / `sard` | `roboflow-v17` export label; exact upstream release linkage unverified | `D:\SWARM-AID\datasets\raw\rgb\Sard` | Image; COCO JSON boxes and empty annotations; aerial person detection | COCO image/category/annotation records, publisher split labels, filenames identifying a 3x3-tile export. Parent frame, flight and site identity are not verified. | Publisher split recorded; parent-group independence unresolved. Phase 10H referenced hashes matched; unreferenced-file coverage is reported separately. |
| FLAME / `flame` | Unknown / not pinned | `D:\SWARM-AID\datasets\raw\rgb\FLAME` | Image; source Fire/No_Fire labels and PNG masks; frame classification and fire segmentation | Local task/split labels and mask paths. No verified parent-video key or mask-to-frame pair metadata. | 491 near-test training frames; 2,003 masks without verified image pairs. |
| WiSARD / `wisard` | Unknown; local folder label `WiSARDv1` is not treated as an authoritative version | `D:\SWARM-AID\datasets\raw\Multimodal\WiSARDv1` | Visible image and thermal; TXT sidecars; thermal detection and RGB-thermal pairing candidates | Sequence-folder names, file paths, modality, `paired` flag and sidecar fields. These do not prove synchronization or calibration. | No approved split; 1,275 flagged records and zero verified pairs. |
| HumAID / `humaid` | Unknown / not pinned | `D:\SWARM-AID\datasets\raw\model2\HumAID` | Text; Parquet class labels and publisher shard partitions; disaster-context classification | Three Parquet shards with `tweet_text` and `class_label`; shard names encode train/validation/test. Row-level event and post identifiers are absent. | Four normalized text keys cross publisher partitions. |
| CrisisMMD / `crisismmd` | QCRI card identifies v2.0; local source identity is not independently authenticated | `D:\SWARM-AID-DATA\raw\multimodal\CrisisMMD` | Image and text; event/task TSV labels and image/post references; informativeness, humanitarian-context and damage-severity classification | Seven event TSVs include event, post/image references, labels and source partitions; local image paths and content hashes expose repeated media. | Events cross task partitions and pooled task views repeat media; a group-independent evaluation is not established. |

For all five additions, `licence_status` and `verification` remain
`unverified`, `privacy_status` remains `pending`, and no single-file dataset
checksum was invented. The registry's `downloaded_bytes` values for added
sources reflect the prior Phase 10H raw inventory totals, not publisher archive
sizes. Local paths and fields not supported by the typed registry contract are
recorded here rather than added as non-schema properties.

## Reconciled indexed-source inventory

The following inventory records the local source path and current evidence for
all 12 indexed sources. All 12 have an entry in the Phase 10I versioned
registry. Every public source remains unapproved: licence and verification
statuses are `unverified`; privacy status is `pending`.

| Dataset / ID / known version | Local path | Modalities; annotation format; task candidates | Source metadata available / gap | Split status | Integrity status |
|---|---|---|---|---|---|
| HERIDAL / `heridal` / unknown | `D:\SWARM-AID\datasets\raw\rgb\HERIDAL` | Image; COCO JSON boxes; person detection | Image/category/box records and publisher split. Parent flight/site linkage unresolved. | Publisher split retained; independence unresolved. | Phase 10H: 1,603 of 1,604 inventory files had matching historical hash references. |
| SARD / `sard` / Roboflow export `v17` | `D:\SWARM-AID\datasets\raw\rgb\Sard` | Image; COCO JSON boxes; person detection | COCO records and tile-export naming. Parent capture, flight/site, and empty-label policy unresolved. | Publisher split retained; parent groups unresolved. | Phase 10H: 5,758 of 5,760 files had matching historical hash references. |
| FloodNet / `floodnet` / unknown | `D:\SWARM-AID\datasets\raw\rgb\FloodNet` | Image; class masks; semantic segmentation | Image/mask associations, source classes and publisher split. Site/event groups unresolved. | Publisher split retained; site independence unresolved. | Phase 10H: 2,343 of 7,031 files had matching historical hash references. |
| RescueNet / `rescuenet` / unknown | `D:\SWARM-AID\datasets\raw\rgb\RescueNet` | Image; class masks; semantic segmentation / damage observation | Image/mask paths, source classes and publisher split. Site/event groups unresolved. | Publisher split retained; site independence unresolved. | Phase 10H: 4,494 of 13,483 files had matching historical hash references. |
| FLAME / `flame` / unknown | `D:\SWARM-AID\datasets\raw\rgb\FLAME` | Image; frame class labels and PNG masks; fire classification / segmentation | Local task/split labels and mask paths. Parent video and mask-pair keys unresolved. | 491 near-test training frames; mask pairs unresolved. | Phase 10H: 49,995 of 49,995 files had matching historical hash references. |
| WiSARD / `wisard` / unknown | `D:\SWARM-AID\datasets\raw\Multimodal\WiSARDv1` | Image and thermal; sidecar labels/boxes; thermal detection / paired learning | Sequence-folder, modality, `paired` and annotation fields. Authoritative edition, sync, calibration and pair identity unresolved. | No approved split; 1,275 flagged rows; zero verified pairs. | Phase 10H: 56,130 of 100,794 files had matching historical hash references. |
| ESC-50 / `esc50` / unknown | `D:\SWARM-AID\datasets\raw\audio\ESC-50-master` | Audio; official CSV class/fold/source recording IDs; sound classification | Official filename, fold, class, `src_file` and `take` fields. | Four recording IDs cross official folds. | Phase 10H: 2,002 of 2,011 files had matching historical hash references. |
| HumAID / `humaid` / unknown | `D:\SWARM-AID\datasets\raw\model2\HumAID` | Text; Parquet class labels; disaster-context classification | Three publisher-partitioned shards with text/label; row-level event/post IDs absent. | Four normalized text keys cross partitions; no event-disjoint proof. | Phase 10H: all 3 files had matching historical hash references. |
| CrisisMMD / `crisismmd` / QCRI v2.0 card | `D:\SWARM-AID-DATA\raw\multimodal\CrisisMMD` | Image and text; event/task TSV labels; three source classification tasks | Event TSVs, post/image references, labels and splits; repeated media identified by hashes. | Events cross task partitions; pooled views repeat media. | Phase 10H: 19 referenced source hashes matched; 36,205 files inventoried. |
| Smoke Detection IoT / `smoke-detection-iot` / unknown | `D:\SWARM-AID\datasets\raw\sensors\smoke_detection_iot.csv` | Environment; CSV measurements/alarm target; sensor interpretation | Timestamp, channels and published alarm target; run provenance, units and label generation need resolution. | No approved split. | Phase 10H: 1 of 1 file had a matching historical hash reference. |
| UCI Air Quality / `uci-air-quality` / unknown | `D:\SWARM-AID\datasets\raw\sensors\AirQualityUCI.csv` and `D:\SWARM-AID\datasets\raw\sensors\AirQualityUCI.xlsx` | Environment; CSV/XLSX measurements; sensor characterization | Timestamp, channels, measurement metadata and missing sentinel; horizon/window policy unresolved. | Draft day groups; task-specific purge required. | Phase 10H: indexed CSV hash matched; the workbook was separately checksum- and CRC-checked. |
| USGS Water Data / `usgs-water-data` / unknown | `D:\SWARM-AID\datasets\raw\sensors\USGSWater.csv` | Environment; CSV period summaries/qualifiers; hydrological context | Station/parameter/period fields; source API can describe units/qualifiers. | No approved split. | Phase 10H: 1 of 1 file had a matching historical hash reference. |

These are counts of files with Phase 10H hash references, not source approval
or publisher authentication. For the Phase 10I-A current per-file coverage and
historical comparisons, see
[`RAW_INTEGRITY_COVERAGE_REPORT.md`](RAW_INTEGRITY_COVERAGE_REPORT.md).

## Governance and version notes

- The original registry and frozen `phase10h-v1` release were not overwritten.
- The versioned snapshot is additive and uses the existing typed contract.
- Locally indexed availability is not release approval. The registry's
  verification, licence and privacy gates remain unresolved for every public
  source.
- SARD's export label, WiSARD's folder label, and the CrisisMMD local card are
  recorded as provenance clues, not as proof of the complete publisher release
  or its licensing terms.
- The five additions do not authorize any public dataset use for training.

See the machine-readable Phase 10I-B blocker inventory in
[`phase10i_b_tasks.json`](../../configs/datasets/phase10i_b_tasks.json) and the
[Phase 10I-A completion report](../PHASE_10I_A_COMPLETION_REPORT.md).
