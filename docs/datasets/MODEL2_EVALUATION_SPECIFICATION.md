# Prospective Model 2 evaluation

Use frozen episode and parent groups, unseen-event or scenario-family sensitivity analyses, and independently annotated held-out cases. Keep public relevance evaluation separate from native command decisions. Compare direct forwarding, per-finding rules, existing rule fusion, a future learned individual-report assessor and a future learned grouped assessor on matched source reports and cutoffs. Direct forwarding has no assessment head; report delivery and time-to-operator rather than assigning it a category score.

| Endpoint | Numerator / denominator or computation | Interpretation |
|---|---|---|
| Assessment and urgency | Per-class precision TP/(TP+FP), recall TP/(TP+FN), macro F1; publish counts and undefined cells | Separate category and urgency. Compare against independent reviewed labels only. |
| Escalation and misses | Unsupported escalations / reviewed non-escalation cases; missed review-worthy incidents / reviewed incident cases | Deduplicate incident revisions, stratify by delayed or missing evidence. |
| Evidence handling | Duplicate, independent-corroboration and conflict precision/recall; correct citation set overlap against reviewer-selected IDs | Use episode-scoped IDs. Score controlled perturbations separately. |
| Recommendations | Fraction satisfying schema, valid citation subset, current revision and expiry; independently reviewed appropriateness | A syntactically valid proposal can still be unsupported. |
| Uncertainty | Coverage versus error among decided cases, abstention agreement on ambiguous cases | Baseline confidence is uncalibrated. Define costs before comparing thresholds. |
| Human labels | Double-annotated count, raw agreement and chance-adjusted agreement where class support permits | Record independent pre-adjudication labels. Pending forms do not supply a denominator. |

Report confidence intervals by resampling independent episodes rather than rows, alongside absolute class and episode support. With only one controlled contradiction and no independent reviewers, several endpoints cannot yet be estimated. No learned model was trained or evaluated.
