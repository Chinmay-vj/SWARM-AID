# CrisisMMD compatibility and local source audit

The external source at `D:\SWARM-AID-DATA\raw\multimodal\CrisisMMD` is the QCRI Hugging Face distribution identified by its local dataset card as version 2.0. All 18,101 indexed files (1,940,966,383 payload bytes) matched the sizes and Git blob or LFS SHA-256 digests in the cached snapshot index at revision `10a5626ba112ab9c50369c473a2062bcf205d708`. This is an extracted snapshot. Archive CRC is inapplicable. Verification used the local index and did not independently authenticate the publisher. [Source card at the inspected revision](https://huggingface.co/datasets/QCRI/CrisisMMD/blob/10a5626ba112ab9c50369c473a2062bcf205d708/README.md)

## Source coverage

The subsequent full decode checked all 17,777 distinct image hashes across the event references. Every image decoded. Semantic annotation accuracy still requires review. [Phase 10G verification](../PHASE_10G_COMPLETION_REPORT.md)

Seven event TSVs contain 18,082 distinct post/image pairs from 16,058 posts. They cover California wildfires (1,589 pairs), hurricanes Harvey (4,434), Irma (4,504) and Maria (4,556), the Iraq–Iran earthquake (597), Mexico earthquake (1,380) and Sri Lanka floods (1,022). All 18,082 image paths resolve. The images have 17,777 distinct byte hashes. All benchmark text fields were populated and every local image was referenced. These checks measure file presence, content identity and source structure. At the time of this source audit, image decoding and semantic annotation accuracy were unverified.

| Publisher JSON task | Train | Dev | Test | Post IDs crossing splits | Image hashes crossing splits |
|---|---:|---:|---:|---:|---:|
| Informativeness | 13,608 | 2,237 | 2,237 | 0 | 83 |
| Humanitarian | 13,608 | 2,237 | 2,237 | 0 | 82 |
| Damage | 2,468 | 529 | 529 | 120 | 17 |

All seven events cross partitions in each task. Pooling task views introduces additional overlap, with 7,671 post IDs and 7,605 media hashes appearing under multiple split names. All 39,690 task rows agree with the event TSV on post ID when joined by image path. Two task rows disagree on image ID. Preserve both source identifiers and flag that discrepancy before deriving records. A task row is a view of a source pair, so summing the three tasks overstates the number of distinct examples.

## Observed labels and compatible targets

| Original label(s) | Candidate public supervision |
|---|---|
| informative, not_informative | Source informativeness for the annotated modality |
| infrastructure_and_utility_damage, vehicle_damage | Reported infrastructure or vehicle damage context |
| affected_individuals, injured_or_dead_people, missing_or_found_people | Separate source categories for affected people, reported casualties, and missing/found context |
| rescue_volunteering_or_donation_effort, other_relevant_information, not_humanitarian | Response activity, other relevant content, or outside the source humanitarian categories |
| severe_damage, mild_damage, little_or_no_damage | Preserve the original ordinal image severity within the public damage task |
| dont_know_or_cant_judge, nan | Abstain or record a missing damage annotation |

Retain task, annotation column, raw label, event, original split, source row reference, post ID and paired image reference together. In the event TSVs, text is labelled informative in 12,855 rows and images in 9,374. A shared task label cannot substitute for both modality-specific annotations. Humanitarian categories provide social-media context only. Distress, verified incident identity, independent corroboration and command urgency need separate evidence.

## Disposition and reproduction

The Phase 10E addendum compared all seven event tables with the three local HumAID shards. It found zero shared normalized whole posts and 220 HumAID rows with at least one 12-word passage in common. These candidates require review before any combined benchmark. Event and post identity cannot be cross-checked from the HumAID Parquet schema. [HumAID overlap methods and results](HUMAID_COMPATIBILITY_REPORT.md)

Public export remains on hold. The local card declares CC BY-NC-SA 4.0 and includes its legal code. A release reviewer must document permitted uses, attribution, redistribution of underlying posts and third-party media, and privacy handling for identifiable people and locations. Public-source approval and adjudication of cross-dataset candidates are outstanding. Preserve publisher partitions for benchmark reporting. Before using this source in a combined experiment, construct disjoint groups spanning shared events, posts and identical media, and report groups that must be held out or excluded. A training split has not been approved. The symbolic pilot contains zero public records.

Run from the repository root to reproduce the aggregate counts, mappings, per-table hashes and split diagnostics. The saved audit is `D:\SWARM-AID-DATA\manifests\model2\crisismmd-10a5626-audit.json`.

```powershell
.tools\phase10a-check\python.exe -m evaluation.data.crisismmd D:\SWARM-AID-DATA\raw\multimodal\CrisisMMD
```
