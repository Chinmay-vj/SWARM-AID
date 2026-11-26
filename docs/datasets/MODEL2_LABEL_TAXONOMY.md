# Model 2 annotation taxonomy 1.0

The source vocabulary is described below. The fourth column gives an ambiguity or common annotation error. Record the cited observations and leave a target unresolved when its inclusion criterion fails.

| Category and inclusion evidence | Positive example | Exclude / negative example | Ambiguity or common error |
|---|---|---|---|
| routine: admitted description of an environmental feature | A source reports road surface | A possible-human finding | An environmental reading may still supply context to a separate hazard |
| hazard: hazard finding tied to evidence | Agent reports an indexed hazard | Presence of ordinary terrain alone | A reported hazard is not a verified physical event |
| possible_human: original sighting with evidence | Symbolic possible-person report | Routine environmental tile | Visibility says nothing about injury |
| uncertain_need: qualified baseline incident with unresolved need | Multiple fresh origins support a person sighting | Forwarding one report twice | Source agreement does not confirm rescue need |
| suspected_emergency / human_confirmed | A supported suspected assessment would need documented grounds; confirmation needs an authorized revision-bound decision | High priority, confidence or scripted delivery | No confirmed or suspected examples in this pilot; confirmation cannot be created via annotation |
| single / insufficient evidence | One original observation, no context; reviewer cannot decide | Multiple independent consistent findings for the same claim | A single report may still justify review |
| corroborating | Fresh, compatible same-cell reports from distinct evidence origins | Same sensor forwarded by another agent | Different people can occupy one grid cell |
| duplicate | Same observation or evidence identity repeated | Fresh observation from the same agent with a new identity | Repeated location alone is insufficient |
| conflicting | Same observation ID with different contents, or simultaneous incompatible same-kind labels in one cell | Two different modalities support the same claim | Different acquisition times can reflect change |
| related | Context shares space/time without meeting a stronger relation | An unrelated cell | A shared cell does not establish incident identity |
| stale / delayed | Age reaches freshness limit; positive send-to-receipt interval records delay | A delayed but still fresh report | Keep transport delay and observation age separate |
| missing modality | A stream is disabled in the fixture, or provenance establishes its absence | A modality simply absent from one report’s evidence list | Missing information is not a negative detection |
| potentially_urgent / elevated / review_required | Actual command priority with rationale from human-plus-hazard context, human-only context, or hazard review respectively | Numeric confidence alone | Priority expresses attention, not probability or distress |
| request human review | Valid recommendation cites source IDs and current incident revision | A categorical claim without evidence | Pending review does not imply acceptance |
| resolution reported / closed | Authorized human lifecycle event for the checked incident revision | Stale update, operator receipt, simulation horizon | Lifecycle events are outside the pilot target set |

The reserved source categories are original public annotation, deterministic scenario reference, rule-derived weak label, independent human review and unresolved. Baseline outputs cannot become independent labels by changing a status string. A reviewer supplies their own assessment and records their identity and revision.
