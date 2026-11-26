# Annotation procedure

1. Read the focal receipt and prior context without opening targets.jsonl or evaluator.json. Anchor the decision to receipt time. List evidence IDs supporting or challenging each claim, and check their original agents.
2. Decide whether the content supports a routine description, hazard, possible sighting, uncertain need, or abstention. Relationship and assessment are independent fields. Record contradictions, missing modalities, stale inputs and uncertainty as needed.
3. Assign urgency separately. A source confidence score remains attached to its observation and has no calibration guarantee. Insufficient information permits an ambiguous review without selecting an assessment.
4. If proposing a recommendation, choose an existing request and use a supported incident/revision, cited evidence, unknowns and exclusive expiry. A new review request is not a rescue authorization. Record review_required and explain what an operator would need to verify.
5. Store a reviewer ID, integer revision, provenance and status. Preserve previous judgments. For independent agreement studies collect each reviewer’s first judgment privately before adjudicating; the current revision ledger supports a sequential pilot, not a blinded multi-rater assignment service.

Examples: a delayed copy with the same evidence IDs adds no independent witness. A single possible-person report at a flooded cell supports review while leaving distress unresolved. Two reports disagreeing about the same observed cell/time justify explicit contrary evidence. The controlled false-sighting example is evaluator-labelled for the test design only. [Taxonomy](MODEL2_LABEL_TAXONOMY.md) · [Local review commands](MODEL2_HUMAN_REVIEW_GUIDE.md)
