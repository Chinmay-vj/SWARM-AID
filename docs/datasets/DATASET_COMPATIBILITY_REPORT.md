# Task compatibility and leakage review

For measurements from the extracted 12-source inventory, see the [Phase 10G completion report](../PHASE_10G_COMPLETION_REPORT.md). The availability statements below describe the earlier Phase 10D audit.

## Phase 10D measured sensor compatibility

The sensor CSVs can be indexed as environmental research assets. Smoke has duplicated recording patterns, UCI requires per-channel sentinel masking, and USGS contains fixed-station summary intervals. None supplies own-drone measurements or verified cross-modal synchronization. The following earlier assessment covers imagery and audio. [Column-level validation and Model 1 mapping](SENSOR_DATASET_VALIDATION_REPORT.md)

No media, annotations, source manifests, partitions or archive members were accessible. The checks below are the criteria for assessing the actual downloads. All local compatibility decisions remain pending.

| Research task | Candidate | Evidence needed |
|---|---|---|
| RGB human detection | HERIDAL, SARD, WiSARD RGB | Parse each annotation export and category map. Match image IDs to decodable originals and compare dimensions; verify finite, positive in-frame COCO xywh boxes and orphan annotations. Count train, validation and test images, annotated people and explicitly reviewed negatives separately. An empty annotation list can also mean incomplete labelling. |
| Environmental classification | FloodNet, RescueNet, FLAME | Preserve source semantics. Scene-level labels require a documented mapping and review, especially when one image contains multiple classes. |
| Flood segmentation | FloodNet | Publisher lists background, two building flood states, two road flood states, water, tree, vehicle, pool and grass. Compare split-specific RGB and mask keys both ways, dimensions, palette/index decoding and ignore IDs. Preserve masks. [Publisher](https://github.com/BinaLab/FloodNet-Supervised_v1.0) |
| Structural damage segmentation | RescueNet | Identify original training masks; verify dimension and pixel-index agreement for each split. Map building damage grades and clear/blocked road labels from the matching release. Check whether debris is a distinct label or only contextual evidence. Color previews are optional if indexed originals exist. |
| Fire classification and segmentation | FLAME | Count Fire and Non-Fire images by supplied split. Verify segmentation frame IDs and mask dimensions independently against original segmentation images. Classification folder names and masks alone cannot establish those pairs. Separate smoke labels remain unverified. |
| Thermal human detection and multimodal fusion | WiSARD | Establish release identity from documentation, structure, flight count and modality totals. The publisher describes a 40.54 GB full release and a 971.6 MB single-flight multimodal sample. Compare pair metadata, timestamps, unmatched frames, annotation coordinates and calibration or spatial transforms. Temporal synchronization alone does not establish pixel registration. [Publisher](https://sites.google.com/uw.edu/wisard) |
| Audio event classification | ESC-50 | Check metadata keys, source recording IDs, official folds and one-to-one WAV correspondence. Compare header sampling rates, channels and frame-derived durations against release specifications (typically mono 44.1 kHz, five seconds). Relevant examples include rain, thunderstorm, siren, breathing and coughing. These labels do not identify a person calling for rescue. Audio remains research-only under Phase 10A. [Publisher](https://github.com/karolpiczak/ESC-50) |

## Split and overlap checks

Preserve supplied split assignments and ESC-50 official folds. First compare content digests within and across splits, especially HERIDAL/SARD exports and WiSARD multimodal subsets versus single-stream material. Exact duplicate counts and negative counts are unknown. Re-encoded images, crops and adjacent video frames need parent-frame/flight/site metadata and similarity review. A matching basename alone proves neither duplication nor pairing.

Keep FLAME frames from a source video together, WiSARD pairs and their parent flight together, ESC-50 excerpts from each recording together, and correlated FloodNet/RescueNet sites and disaster events together in evaluation design. Missing grouping metadata limits independence claims. Validate the full proposed manifest collection together, retain original split provenance, and preserve reserved synthetic evaluation seeds 42–46. The Phase 10A validator checks declared groups and exact digests; it cannot recover absent provenance or independently label a negative.
