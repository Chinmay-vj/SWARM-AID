# Domain data contracts

The Python definitions in agents/shared/domain.py and communication/messages.py are the wire authority. Domain values inherit Record, reject extra fields and non-finite numbers, and use immutable nested records and tuples. JSON arrays decode to tuples. The envelope carries mission context for nested values; storage keys must retain that context.

| Record | Fields and interpretation | Runtime responsibility |
|---|---|---|
| Cell | Nonnegative integer x,y in scenario grid | Validate width, height and restrictions |
| Evidence | UUID, original agent, capture ms, modality, opaque artifact key | Check ownership, availability and access |
| Observation | UUID, optional cell, observed ms, confidence in [0,1], nonempty evidence | Preserve origin and mark age; confidence is a provider score |
| SensorFrame | Agent, tick ms, modality samples | Expose only artifacts visible to this agent |
| LocalView | Agent, tick ms, observations, battery fraction | Derived from local data and authorized messages |
| Action | Intent and cell for survey/revisit | Validate lease and occupancy against simulation constraints |
| Incident | ID, positive revision, category, report IDs, uncertainty strings, conditional confirmation ID | Verify same-mission references and committed explicit confirmation |
| Recommendation | ID, incident ID/revision, review request, evidence IDs, unknowns, expiry | Check freshness, evidence resolution and human authority |

Unknown locations use null. No synthetic grid coordinates may be interpreted as GPS. GPS and IMU adapters must record their reference frame and units in referenced samples before projecting to the grid. Images and video are represented by keys, never by inline pixels. Derived evidence must retain links to input IDs in the future evidence store. Versioned config selects the scenario, tick, seed, reserve and maximum offline duration; unknown settings fail validation.

## Audited boundary rules

Nonblank identifiers, strictly numeric counters/scores and strictly boolean retry flags prevent coercion of malformed JSON. The issuer must use opaque tokens independent of labels. Resolve tokens in a scoped lookup table. Duplicate evidence IDs within an observation are invalid. Capture time is at most observation time, which is at most report send time. Direct evidence and last-contact timestamps also cannot exceed send time. An attached recommendation must be current at publication; receivers still check expiry at use.

SensorFrame and LocalView carry nullable measured position and measured battery. A Finding couples observation with environment, hazard or possible-human classification. ReportedFinding pairs it with the accepted envelope ID for command provenance. TaskLease retains task ID, authorized action and exclusive deadline from the instruction envelope. SafetyContext supplies an independent measured frame, authoritative state, lease, reserve, offline deadline and prohibited cells; every input comes from the scoped controller. These are in-process provider contracts. The 16 v1.0 message shapes are preserved. The audit tightens acceptance of malformed values; historical invalid records require quarantine with a reason, without coercion or replay.
