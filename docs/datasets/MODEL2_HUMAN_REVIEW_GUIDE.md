# Local human review

The active first batch has **50 pending forms** in `D:\SWARM-AID-DATA\manifests\model2\pilot-2-addendum-1\review-queue.jsonl`. It includes the original 18 forms. The batch covers all 13 episodes and five controlled cases. Select a form by its sample ID and view only the inputs available at the decision time.

```powershell
$env:SWARM_DATASET_ROOT = 'D:\SWARM-AID-DATA'
$queue = Join-Path $env:SWARM_DATASET_ROOT 'manifests\model2\pilot-2-addendum-1\review-queue.jsonl'
$form = Get-Content -LiteralPath $queue -TotalCount 1 | ConvertFrom-Json
.tools\phase10a-check\python.exe -m evaluation.data.model2 show --version pilot-2 --sample-id $form.sample_id
```

Copy only the selected pending JSON object into a private D:-drive JSON file. Set provenance to human_reviewed, reviewer to an attributable reviewer ID, revision to 1 and status to reviewed or ambiguous. Enter assessment and relationship where justified. Put **actual cited UUIDs** in supporting and conflicting; these lists must be disjoint. Use uncertainty and missing_information for reasons to abstain. Keep baseline_incident null on a human form. Only record a recommendation when its evidence and revision can be checked. This workflow is an annotation, never an operational decision.

For recommendation review, first record your independent assessment. Then read the matching sample in `targets.jsonl` and inspect its baseline incident ID, revision, request, cited evidence and expiry. Record a recommendation only if those references support it at the receipt time. Leave the field empty and explain missing information or uncertainty when they do not.

```powershell
.tools\phase10a-check\python.exe -m evaluation.data.model2 review --version pilot-2 --review-file D:\path\to\review.json
.tools\phase10a-check\python.exe -m evaluation.data.model2 export-reviews --version pilot-2
```

The review command verifies the release, validates the form and creates an immutable revision under `D:\SWARM-AID-DATA\annotations\model2\pilot-2`. A revision conflict fails. Read the prior revision and resubmit an explicitly updated judgment at the next revision. The export command writes the latest human judgment per reviewed example to standard output, in JSONL. Empty output means no saved reviews. Keep private reviewer identifiers outside Git.
