# Independent field review

The first batch contains 100 pending forms from 69 episodes. The selection pass used six ambiguous, 21 conflicting, 12 duplicate, 21 potentially urgent, 20 routine and 20 other primary selections. These are sampling strata derived from existing weak labels. An example may satisfy multiple criteria. The queue checksum is `46f4b4e8da20bd563d1d7997039447e308e0694bea69abb97bded903a2e90d25`.

Read the private file `annotations/model2/phase10g-field-v1/review-queue.jsonl` in the external data root. Each entry contains its batch version, operational features and a blank Phase 10E Target form. Work independently from the features. Cite original evidence UUIDs, record uncertainty and missing information, assign the assessment and urgency only if supported, and record whether human review is required. Preserve the sample ID. Set provenance to human_reviewed, an attributable reviewer handle, revision to 1, and status to reviewed or ambiguous. Leave the baseline incident and recommendation empty during first look. No human judgments have been generated.

```powershell
$root='D:/SWARM-AID-DATA'
.tools/phase10a-check/python.exe -m evaluation.data.independent_reviews --root $root --submit D:/private/form.json
.tools/phase10a-check/python.exe -m evaluation.data.independent_reviews --root $root --agreement reviewerA reviewerB
```

The first-look store keeps immutable, reviewer-specific records outside the repository. Agreement uses only independently rated common samples and reports sample count, raw agreement and Cohen's kappa for assessment, including abstentions. With zero paired judgments, agreement is unavailable. After the first look, inspect the original recommendation and record the cited evidence, incident revision, expiry, scope and any reason for rejecting it. Save the adjudicated result with the existing version-specific review command. Further revisions require the preceding adjudication. [Review and adjudication instructions](MODEL2_HUMAN_REVIEW_GUIDE.md)
