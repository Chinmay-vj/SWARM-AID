# Dataset gaps and optional collection decisions

## Phase 10D sensor findings

Physical environmental records are now present for experimental air sensing, roadside chemistry, and one streamgage. They narrow the physical-data gap recorded below. Remaining needs include calibration and verified smoke-event provenance, independent recording groups, UCI release-use clarification, continuous water readings and site-specific flood thresholds. None of the three supplies onboard telemetry or paired mission captures. [Sensor validation report](SENSOR_DATASET_VALIDATION_REPORT.md)

The seven downloads are owner-reported, with zero releases inspected. The following collection decisions are conditional on file-level results. Empty optional folders remain pending.

| Requirement | Open question | Value of additional data |
|---|---|---|
| RGB people, occlusion and negatives | Check full-frame counts, explicit negatives, target sizes, occlusion labels and cross-flight diversity in HERIDAL, SARD and WiSARD. | VisDrone can broaden aerial scenes and distractors. NOMAD specifically evaluates occluded, multi-scale aerial human detection. Consider only after identifying the actual gap. [VisDrone](https://github.com/VisDrone/VisDrone-Dataset) · [NOMAD paper](https://arxiv.org/abs/2309.09518) |
| Thermal perception | WiSARD edition, labelled thermal examples and spatial calibration are unknown. A single flight cannot establish cross-flight robustness. | HIT-UAV could broaden thermal detection conditions. It cannot fill a missing aligned visual/thermal pair merely by adding thermal frames. [HIT-UAV](https://github.com/suojiashun/HIT-UAV-Infrared-Thermal-Dataset) |
| Fire and smoke | FLAME segmentation frame availability is unresolved. Explicit smoke labels and negatives require evidence. | Consider additional smoke-labelled scenes only if verified FLAME labels leave this task uncovered. |
| Distress audio and drone noise | ESC-50 clip classes support general acoustic events. Verified distress calls, in-flight ego-noise and microphone/throttle metadata remain gaps. | FSD50K may broaden event labels after item-level rights and source checks. Dedicated drone-acoustic data would address motor noise more directly. [FSD50K](https://zenodo.org/records/4060432) · [DroneAudioSet paper](https://proceedings.nips.cc/paper_files/paper/2025/hash/adececbc73a58724db0f3c0d5c77f338-Abstract-Datasets_and_Benchmarks_Track.html) |
| Physical environmental sensors | No confirmed calibrated environmental time series with sensor units, sampling times, calibration and missing-value records. | RGB segmentation and thermal imagery do not substitute for instrument readings. |
| Disaster diversity and missing-person missions | Flood/damage imagery and person boxes do not establish independent disaster events or complete missing-person mission trajectories. | Verify event/site groups before selecting additional releases. Missing-person mission simulation and expert-reviewed incident outcomes remain separate project gaps. |

The review point is access to the seven releases. Release identity, annotation coverage, rights and grouping evidence should determine any later collection. No acquisition or model selection follows from this report.
