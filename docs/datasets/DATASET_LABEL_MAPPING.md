# Source-to-target mapping

| Source annotation | Retained target and interpretation |
|---|---|
| HERIDAL and SARD COCO categories | Source category ID and name, with boxes in original pixel coordinates. Person presence supports a detection task. Empty image annotations are recorded as empty. |
| FloodNet indices 0–9 | Background, flooded building, non-flooded building, flooded road, non-flooded road, water, tree, vehicle, pool, grass, in that order. |
| RescueNet indices 0–10 | Background, water, undamaged building, minor damage, major damage, total destruction, vehicle, clear road, blocked road, tree, pool. The local note enumerates 11 IDs despite describing ten classes. |
| FLAME Fire / No_Fire | Source frame classification. The mask-only component has no verified matching source frames. |
| WiSARD native labels | Retain the original per-frame sidecar class ID where valid. Sequence tokens distinguish infrared and visible folders. |
| ESC-50 category / target | Original environmental sound class and numeric target. Clip origin is retained independently. |
| Smoke Fire Alarm | Source-provided experimental alarm target with unresolved generation method, stored apart from measurement features. eCO2 denotes estimated equivalent concentration. |
| UCI and USGS | Measurement and period-summary tasks. Event labels are unavailable. |
| CrisisMMD | Per-task informativeness, humanitarian context and damage severity. Preserve raw per-modality labels and ordinal severity. Shared higher-level context labels are supplementary. |
| HumAID | Original disaster-context classification label from each Parquet row. An event identifier is unavailable. |
| Symbolic Model 1 | A reported local finding with evidence, uncertainty and observation time. |
| Structured Model 2 | Assessment, relationship, urgency, uncertainty, review requirement and a revision-bound recommendation have separate fields. A duplicate report can still contain a potentially urgent observation. Insufficient evidence supports abstention. |

Priority and rescue need require independent evidence. Public context labels and alarm signals have no approved mapping to a confirmed rescue incident. [Model 2 taxonomy](MODEL2_LABEL_TAXONOMY.md) · [CrisisMMD contextual mapping](CRISISMMD_COMPATIBILITY_REPORT.md)
