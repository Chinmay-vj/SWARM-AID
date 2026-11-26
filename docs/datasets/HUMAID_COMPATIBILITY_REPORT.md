# HumAID supplementary disaster-context collection

All three Parquet shards were present at `D:\SWARM-AID\datasets\raw\model2\HumAID`. The expected external raw path was absent. The audit read the local shards in place. Train and test SHA-256 values matched QCRI's LFS pointers. Validation matched the publisher's Git blob ID `2a028f0c2826f8e4d0065893e525bd6e4ebfe80b`. The external `humaid-context.json` records each filename, SHA-256, byte size, schema, split and per-label counts. [QCRI file metadata](https://huggingface.co/api/datasets/QCRI/HumAID-all/tree/main/data)

| File split | Rows | Distinct normalized texts | Missing text or label | Payload bytes |
|---|---:|---:|---:|---:|
| Train | 53,531 | 53,531 | 0 | 5,045,706 |
| Validation | 7,793 | 7,792 | 0 | 739,357 |
| Test | 15,160 | 15,159 | 0 | 1,438,693 |
| Combined | 76,484 | 76,478 | 0 | 7,223,756 |

Every shard contains two string fields, `tweet_text` and `class_label`. The ten observed classes are `caution_and_advice`, `displaced_people_and_evacuations`, `infrastructure_and_utility_damage`, `injured_or_dead_people`, `missing_or_found_people`, `not_humanitarian`, `other_relevant_information`, `requests_or_urgent_needs`, `rescue_volunteering_or_donation_effort` and `sympathy_and_support`. The card also describes an undecidable category that was absent from these shards. The publisher attributes collection to 19 disaster events and labels to crowd annotators. Individual rows have no event, post ID, timestamp or verified outcome. [QCRI dataset card](https://huggingface.co/datasets/QCRI/HumAID-all/blob/main/README.md)

Use the original label and split only for supplementary text classification. A request for help in a post cannot establish a current rescue need, independent drone evidence or Model 2 priority. The source collection remains separate and reference-only. Zero public posts entered the native features, targets or review queue.

**Governance remains pending.** The card metadata declares CC BY-NC-SA 4.0 while its licensing section names CC BY-NC 4.0. Obtain a documented rights decision covering the applicable terms and underlying posts before export. Handles, locations and accounts of injury can identify individuals. The audit exports only aggregate statistics and file hashes. [QCRI licensing statements](https://huggingface.co/datasets/QCRI/HumAID-all/blob/main/README.md)

## Leakage inspection

HTML entity decoding, Unicode NFKC normalization, case folding and whitespace normalization yielded four distinct texts in more than one HumAID split. Against all seven audited CrisisMMD event TSVs the same method found zero matching whole texts. A second screen removed URLs and handles and searched for any common contiguous sequence of 12 word tokens. It flagged 154 train, 28 validation and 38 test HumAID rows. Each row counts once. Shared passages can arise from quotation, headlines or reposting. Short texts, paraphrases and shared events can evade this screen.

Preserve the publisher splits for source analysis. Before a combined benchmark, adjudicate or exclude candidate matches and group related texts across sources. Event-disjoint and post-ID-disjoint evaluation cannot be certified from these shards. [Reproduction commands and native leakage results](MODEL2_ADDENDUM.md)
