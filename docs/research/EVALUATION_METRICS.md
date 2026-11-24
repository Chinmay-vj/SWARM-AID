# Evaluation metrics

Use mission-relative simulated time. Freeze spatial/time matching tolerances and use deterministic one-to-one matching of deduplicated detection events to truth events within each scoring window. Report counts as well as rates. A zero denominator yields unavailable with its reason.

| Metric | Definition |
|---|---|
| Search coverage | Distinct eligible cells observed through a valid sensor footprint divided by scenario-defined eligible cells |
| Victim discovery time | First matched observation capture time minus victim availability time; censor undetected persons at horizon and report discovery fraction |
| Detection precision / recall | Matched detections divided by all detections / matched truth events divided by all eligible truth events respectively |
| False alarm rate | Unmatched alerts per simulated search hour; separately report false positives per evaluated negative window if defined |
| Duplicate observation rate | Repeat deliveries of an originating observation to a given recipient divided by total delivered observations to that recipient |
| Communication latency | First accepted arrival minus send time for each delivered logical message-recipient pair; report median and p95 |
| Message delivery rate | Unique delivered intended message-recipient pairs divided by intended pairs by horizon, by type and channel |
| Bandwidth consumption | Sum serialized UTF-8 byte lengths of all delivery attempts including retries, divided by simulated seconds; fan-out counted per recipient |
| Simulated energy | Sum configured movement, idle, sensing and communication debits across agents; report units and exhausted agents |
| Mission completion | Fraction of runs meeting the preregistered search objective before horizon and within safety constraints |
| Incident assessment accuracy | Correct category predictions divided by labeled incidents at a frozen assessment checkpoint; publish confusion matrix and category counts |
| Recommendation feasibility | Proposals satisfying all scenario-defined prerequisites divided by reviewed proposals; report indeterminate cases separately in the denominator |
| Unsupported recommendation rate | Generated proposals with at least one unresolved or unsupported claim divided by all generated proposals; also score published subset |
| Reliability under faults | Completion fraction per fault condition and paired difference from healthy runs; also report recovery duration and safety violations |

Separate case labels from actual human decisions. Score explicit confirmation against the recorded decision history. Report pre-review assessment separately to avoid rewarding access to a reviewer label. Keep event-time discovery distinct from delayed receipt at command.

Count transport retries by envelope and semantic duplicates by original observation ID. Separately report incident fragmentation (ground-truth cases linked to multiple predicted incidents / matched truth cases). Independent corroboration from distinct captures is eligible evidence. Detection matching must handle multiple eligible candidates deterministically, e.g. maximum cardinality then minimum aggregate time/distance with stable ID tie-breaks. Use the same matching rule across arms.

Also publish missed incidents, unmatched predicted incidents, assessment coverage and proposal yield per eligible incident. Report feasible, infeasible and indeterminate counts among all reviewed proposals and the fraction reviewed among published proposals. Log rejected proposals before filtering and report abstentions so a policy producing no proposals cannot earn a perfect feasibility or support score.
