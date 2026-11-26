# Phase 10I-B1/C1 Model 1 candidate readiness

**Decision: NO-GO.** Candidate means prepared for inspection only. It does not
mean training-ready or approved.

| Learning task | Source(s) | Status | Candidate artifact | Remaining blockers |
|---|---|---|---|---|
| RGB person detection | HERIDAL, SARD | BLOCKED | No | Parent flight/site IDs; 1,392 empty annotation rows need source-policy review; category alias and governance review |
| RGB fire classification | FLAME | BLOCKED | Yes, preparation-only | 491 near-test training frames excluded; no parent video/capture grouping; rights and privacy pending |
| FloodNet semantic segmentation | FloodNet | BLOCKED | No | Hurricane Harvey source event known, site/capture grouping absent; rights and privacy pending |
| RescueNet semantic segmentation | RescueNet | BLOCKED | No | Hurricane Michael source event known, site/capture grouping absent; dataset terms and privacy pending |
| RescueNet infrastructure damage assessment | RescueNet | BLOCKED | No | Damage-grade semantics need independent review; grouping and governance unresolved |
| FLAME fire segmentation | FLAME | BLOCKED | No | 2,003 masks lack verified image pairs |
| WiSARD thermal perception | WiSARD | BLOCKED | No | 1,275 flags; 11,542 missing sidecars; display-coded values are not calibrated temperatures |
| WiSARD RGB-thermal pairing | WiSARD | BLOCKED | No | Zero verified pairs; synchronization, alignment, calibration, and capture IDs absent |
| ESC-50 environmental sound classification | ESC-50 | BLOCKED | Yes, official-fold candidate | Nine clips excluded for cross-fold recording reuse; clip-specific terms and attribution need review |
| Smoke Detection IoT time-series classification | Smoke | BLOCKED | No | Five runs collapse to three repeated signatures; run identity and alarm-label provenance unresolved |
| UCI next-hour CO concentration | UCI | BLOCKED | Yes, temporal-only candidate | Single-site limitation; research-only/commercial exclusion language conflicts with CC BY 4.0 metadata |
| USGS interval hydrology | USGS | BLOCKED | No | 36 overlapping interval summaries; no continuous series, verified event label, or split |
| Native symbolic observation processing | Native Model 1 | BLOCKED | No | No native/protected records accessed; independent evaluation and weak-imitation protocol pending |
| Native structured report generation | Native Model 1 | BLOCKED | No | Delivery-selected reports are not independent targets; private pilot/alert data out of scope |

The three candidate manifests are external to the repository:

| Dataset/task | Candidate records | Partition counts | Integrity qualification |
|---|---:|---|---|
| FLAME classification | 47,501 | train 38,884; test 8,617 | Preparation-only; capture grouping blocked |
| ESC-50 sound classification | 1,991 | folds 1-5: 400, 398, 398, 398, 397 | Candidate partition only; source terms pending |
| UCI next-hour CO | 7,603 | train 5,052; validation 1,198; test 1,353 | Temporal-only; no cross-partition raw-row reuse |

Every manifest explicitly denies training approval and requires human review.
The [machine-readable task snapshot](../../configs/datasets/phase10i_b1_c1_model1.json)
and D-drive `model1_candidate_readiness.json` carry the complete dispositions.
