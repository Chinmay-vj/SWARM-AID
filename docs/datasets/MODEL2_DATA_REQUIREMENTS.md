# Model 2 symbolic episode and review data

Use integrated symbolic episodes containing authenticated report events. Retain mission, scenario, seed, simulator/config revision, tick, message ID, bound principal, destination, session, capture/send/delivery/decision times and application outcome. A transport receipt means inbox delivery. Use the command acceptance journal to establish which inputs reached assessment.

| Unit | Required content and handling |
|---|---|
| Report | ReportedFinding pairs the accepted envelope UUID with Finding. Preserve stable observation ID, kind, optional label, cell, score and each original Evidence. A direct sighting and a forwarded copy share observation lineage. Record forwarding chain separately from originating agent. |
| Group | Keep source IDs, report IDs, incident ID and revision, association reason, time window, supporting and conflicting links. Treat independent originating sensors/agents separately from relays. Include retries, contradictory labels, missing streams, stale reports, environmental negatives and unresolved associations. |
| Assessment | IncidentAssessmentProvider consumes previous Incident or null and the selected tuple of ReportedFinding. Targets can use routine, hazard, possible_human, uncertain_need, suspected_emergency or human_confirmed with uncertainties. Current rules cover a subset. Preserve rejection reasons, age, evidence access and confidence separately. |
| Urgency | The command-local urgency port takes a Finding and context findings, emits level, reason and evidence IDs. Levels are review_required, elevated and potentially_urgent. Record what information was available at that tick. |
| Recommendation | RescueRecommendationProvider takes incident and reports. Output has proposal ID, incident ID and revision, cited evidence IDs, unknowns, exclusive expiry and one of inspect_evidence, request_observation, review_rescue_need. |
| Review | Record actual authorized review event, expected revision, timestamp and outcome. A review request, scripted operator and rule-generated assessment cannot supply an expert label. Leave expert labels absent until independently obtained and attributable. |

Operational features stop at the assessment tick. Store human-reviewed targets separately from inputs. Simulator truth, later decisions and subsequent incident revisions belong outside that feature window. A confirmed category requires an explicit human decision reference. Group related reports, forwarded copies, incident revisions and the entire episode in one split. Evaluate citation validity, unsupported assertions, duplicate handling, conflict retention, stale rejection and agreement with independently reviewed cases. Report unavailable human ground truth as unknown.
