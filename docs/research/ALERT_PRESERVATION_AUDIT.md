# Operator citation audit on matched field observations

Eight matched configurations used flood and missing-person search, three or five agents, and development seeds 1801 and 1802. The audit replayed individual rules and command fusion separately with the standard fleet, verified identical report identities, observations, evidence and capture times, and traced each operator-delivered incident revision back to its reported sources. No human decisions entered the replay.

| Report citation by end of episode | All matched reports | Possible-human reports with visible civilian at reported cell and time |
|---|---:|---:|
| Both modes | 453 | 142 |
| Individual rules only | 203 | 44 |
| Fusion only | 7 | 2 |
| Neither mode | 500 | 5 |

There were 1,163 matched reports. Individual rules sent 656 delivered updates and cited 902 distinct evidence IDs. Fusion sent 338 and cited 601. Of the 453 reports represented in both modes, 119 first appeared later under fusion. Of 28 distinct evidence IDs explicitly marked potentially urgent by delivered individual-mode alerts, 15 had no end-of-episode report citation under fusion. This urgency designation is a rule-derived signal. The evaluator's 193 same-cell references concern reports, potentially including repeated sightings of one person.

The private `runs/phase10g-alert-v2/matched.jsonl` records capture time, first operator citation time, citation multiplicity, evidence lineage, both rule-derived urgency signals, and a flag for review. Use `review == true` to examine asymmetric, absent or delayed citations. Inspect updates and original reports together when adjudicating content. Several reports can merge into an incident. A missing citation alone cannot distinguish aggregation, publication suppression, packet loss, or the episode ending before delivery. Human importance, semantic preservation and rescue outcomes remain unresolved. [Reproduction commands](../datasets/DATASET_PREPROCESSING_SPECIFICATION.md)

Of the 203 individual-only report citations, the command journal recorded 201 as corroboration held to preserve an outstanding human-review revision. Counting direct alert and recommendation evidence as well as incident-report lineage, 325 unique evidence IDs represented by individual mode were absent from fusion outputs. The 15 individually urgent IDs were still absent under this broader attribution rule. The replay establishes a loss of explicit evidence attribution on these development cases.
