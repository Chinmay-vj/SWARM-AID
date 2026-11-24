# Model 2 evaluation metrics

| Field | Measurement boundary |
|---|---|
| observations | Unique finding IDs admitted to command by episode end. |
| incidents | Distinct incident identities in command memory. Direct forwarding creates none. |
| operator_updates | Delivered forwarded reports and incident alerts, including revisions and human dispositions. A mission status update is a separate message type. |
| decisions_sent | Number of scripted operator responses submitted. Accepted, stale and expired decisions have separate command counters. |
| first_operator_sighting_ms | Earliest simulated receipt time for a possible-human finding at the operator endpoint, null if absent. |
| false_sighting_fraction | Delivered distinct possible-human reports with no visible synthetic person at the reported cell and observation time, divided by all delivered distinct possible-human reports. Null for an empty denominator. |
| missed_people_fraction | Configured people without a truth-matched report at the operator divided by configured people. Null for an empty population. |
| repeat_reports_of_people | Truth-matched reports beyond the first for each observed identity. Independent corroboration can legitimately contribute here. |
| mixed_identity_incidents | Delivered incident groups associated with more than one visible truth identity at the reported observation times. |
| network | Wire bytes, intended pairs, delivery, duplicate/loss/overflow, latency and recovery metrics from the Phase 4 router. |
| counts | Application events, including admitted, stale, duplicate, conflict, opened, revised, expired, rejected decisions and recovery. Missing keys represent zero events. |

Truth is sampled within evaluation at mission ticks. The command API receives neither entity identities nor simulator coordinates beyond reported observations. Rates measure symbolic fixture behavior. No clinical priority, rescue success or real-world false-alarm rate was measured.
