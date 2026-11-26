# Model 2 training readiness

Every proposed training task below has **zero approved records** and is **BLOCKED**. Private CPU pipeline inspection is CONDITIONAL. The loader column of the [integrity report](FINAL_DATASET_INTEGRITY_AUDIT.md) gives actual batch results per source; the [governance report](FINAL_DATASET_GOVERNANCE_REPORT.md) gives source restrictions.

| Task | Source and modality | Input → target | Split status | Label limitation or corrective action |
|---|---|---|---|---|
| Disaster text classification | HumAID, text | normalized source text → publisher context class | Four whole-text keys cross splits; missing event IDs | Resolve source terms and construct an independent evaluation. |
| Image-text disaster classification | CrisisMMD, image + text | source post/image pair → per-task source label | Events cross partitions; pooled tasks repeat media | Select one task, group posts/media/events, review rights. |
| Report relevance classification | native Model 2, structured | as-of receipt and context → independent relevance decision | pilot and expanded separate | Define relevance taxonomy and label a held-out sample. |
| Evidence relationship classification | native Model 2, structured | as-of evidence group → weak relationship | Keep episode, evidence and controlled parents together | Review independent strata and resolve identity collisions. |
| Duplicate evidence identification | native Model 2, structured | source evidence and context → duplicate relationship | Repeated or forwarded records share origins | Validate duplicate decisions independently. |
| Contradiction recognition | native Model 2, structured | conflicting evidence group → conflicting relationship | Rare and partly controlled examples | Review contrary evidence and expand independent cases. |
| Incident assessment | native Model 2, structured | as-of evidence group → weak assessment | development scenarios and separately protected pilot | Adjudicate alert preservation and define independent outcomes. |
| Uncertainty representation | native Model 2, structured | receipt, age, missing modalities → uncertainty and abstention | development only | Label uncertainty independently and assess calibration. |
| Structured recommendation generation | native Model 2, structured | evidence with incident revision and expiry → human-reviewed recommendation | zero independent recommendation targets | Collect evidence-backed, revision-specific human decisions. |

Public publisher labels are candidates for source-task supervision after approval. Native rules could support explicitly weak supervision. The mixed pilot is integrity/evaluation only. Operational assessment and recommendation generation remain blocked pending independent labels and evidence-preservation review.
