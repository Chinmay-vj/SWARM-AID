# Final matched-alert audit

**Operational important-alert preservation remains blocked.** Across eight matched development configurations, both command modes processed 1,163 observations. Individual rules delivered 656 operator updates and fusion delivered 338, a 48.5% reduction. Neither delivery nor a same-cell reference supplies an independent importance judgment.

| End-of-episode report citation | All reports | Possible-human reports with a visible civilian at the reported cell and capture time |
|---|---:|---:|
| Both methods | 453 | 142 |
| Individual only | 203 | 44 |
| Fusion only | 7 | 2 |
| Neither | 500 | 5 |

The audit rebuilt evidence membership within each scenario, fleet size and seed from operator citations and explicit recommendation/alert evidence. **None of the 203 individual-only reports had any of its evidence IDs attributed elsewhere under fusion**. This includes all 44 same-cell cases. The command journal marked 201 of the 203 as corroboration. Internal merging can coexist with an omitted operator attribution. The records do not establish duplicate removal, distress, or subsequent rescue. Of reports cited in both modes, 119 first appeared later under fusion.

Of 193 reference-positive reports, individual mode cited 186 (96.4%) and fusion cited 144 (74.6%). Fusion retained an explicit report citation for 142 of the 186 cited by individual mode (76.3%). Denominators count repeatable reports, not people. Important-alert recall cannot be estimated without independent importance labels. Rule urgency alone is insufficient.

Private `runs/phase10h-alert-v1/alert-review.jsonl` has 203 pending records indexed by report, observation, development configuration, evidence present/absent and journal events. Filter `reference_colocated == true` for the 44 priority reviews. Review original matched receipts and fused incident revisions, distinguish omitted attribution from content preserved in narrative, and record evidence and reviewer provenance. Do not expose evaluator references to the initial blinded reviewer. [Earlier matched audit](ALERT_PRESERVATION_AUDIT.md) · [Blinded review procedure](HUMAN_ANNOTATION_STATUS.md)
