# Model 1 training readiness

Every proposed training task below has **zero approved records** and is **BLOCKED**. Private CPU pipeline inspection is CONDITIONAL. The loader column of the [integrity report](FINAL_DATASET_INTEGRITY_AUDIT.md) gives actual batch results per source; the [governance report](FINAL_DATASET_GOVERNANCE_REPORT.md) gives source restrictions.

| Task | Source and modality | Input → target | Split status | Label limitation or corrective action |
|---|---|---|---|---|
| RGB person detection | HERIDAL, SARD, RGB | image + COCO xywh → person class and box | Publisher splits; tile and flight parents incomplete | Review empty annotations and recover parent-flight/site groups. |
| RGB fire classification | FLAME, RGB | frame → Fire / No_Fire | 491 train frames near test frames | Recover parent videos and freeze a group-disjoint comparison. |
| Semantic segmentation | FloodNet, RescueNet, RGB | image + paired index mask → source pixel class | Official partitions; site independence unknown | Verify class semantics and site holdouts. |
| Fire segmentation | FLAME, RGB | unpaired mask → fire mask | 2,003 masks lack verified image pairs | Recover matching original segmentation frames. |
| Infrastructure damage assessment | RescueNet, RGB | image + index mask → source building damage grade | Publisher split; correlated sites possible | Review damage labels and site holdout. |
| Thermal perception | WiSARD, thermal preview | display-coded frame + native sidecar → source class and normalized box | sequence folders; no approved split | Review flagged boxes, equipment and capture groups. |
| RGB-thermal learning | WiSARD, RGB + thermal | registered or synchronized pair → task-specific paired label | zero verified pairs | Obtain capture IDs, timing accuracy and alignment evidence. |
| Environmental audio classification | ESC-50, audio | PCM or log-Mel → environmental sound category | Five official folds; four shared recording IDs | Review clip terms and apply recording-level exclusion. |
| Sensor time-series learning | Smoke, UCI, USGS, stationary sensors | time or interval, channels, missingness → alarm, concentration or interval statistic | UCI day blocks; Smoke and USGS unassigned | Specify prediction horizon and units; purge overlapping windows. |
| Symbolic observation processing | native Model 1, symbolic | agent-local readings → mock finding and cited evidence | 72 development episodes | Define weak imitation protocol and separate human evaluation. |
| Structured report generation | native Model 1, symbolic | agent-local readings → native report envelope | Outcome sampled on delivery | Review target quality and quantify selection bias. |

Physical temperature regression, emergency distress detection and synchronous cross-source fusion lack eligible targets. Native findings can exercise structured pipelines; symbolic readings cannot establish physical perception accuracy.

## Phase 10I-B1/C1 addendum

The candidate-only Model 1 audit produced three inspection manifests, but all
14 listed task dispositions remain **BLOCKED**, with zero approved training
records. The candidate release and source-specific blockers are described in
the [Phase 10I-B1/C1 readiness report](PHASE_10I_B1_C1_MODEL1_CANDIDATE_READINESS.md).
This addendum does not supersede the readiness findings above or grant approval.
