# Measured pilot-2 statistics

| Unit | Count |
|---|---:|
| Completed episodes / distinct fixtures | 13 / 13 |
| Unique source report envelopes at command | 1,138 |
| Native focal examples selected | 505 |
| Traceable controlled variants | 5 |
| Total examples / distinct context report sets | 510 / 509 |
| Distinct baseline incidents in exported updates | 70 |
| Public-source / independently reviewed examples | 0 / 0 |
| Weak / unresolved target records | 508 / 2 |
| Pending status / pending reviewer queue | 510 / 18 |
| Train / validation / test | 234 / 80 / 196 |

**Assessments:** routine 157, hazard 61, possible_human 42, uncertain_need 26, no category 224. A weak relationship label can exist without an assessment. **Relations:** single 146, related 191, corroborating 170, duplicate 2, conflicting 1. **Urgencies:** review_required 56, elevated 64, potentially_urgent 9, absent 381. Of 129 actual generated recommendations, 103 requested evidence inspection and 26 requested review of rescue need.

Fleet sizes of one, three and four account for 29, 321 and 160 rows respectively. Focal evidence references include 453 image, 473 thermal and 312 environmental modality tags; these are symbolic references, and multiple tags can occur per row. Distinct context-plus-focal evidence counts range from 1 to 66; 132 examples have three. Forty rows have four scenario-disabled modalities. Thirty-seven presentations reach the 1,500 ms stale boundary. All 510 presentations have positive receipt-minus-send time, including the counterfactuals. The outage fixture recorded one command-offline transition.

Per-fixture counts: flood_basic 44, command_routine 41, command_single 29, command_stale 36, and 40 each for command_conflict, command_missing_modalities, cyclone_basic, earthquake_basic, flood_network_duplicate, flood_noise, flood_server_unavailable, landslide_basic and wildfire_basic. Only 5 controlled presentations exist: repetition, relay, conflicting identity, stale presentation and spurious sighting. Repeated weighting of near-identical controlled cases was avoided.

The external pilot directory contains 36 files totaling **6,385,696 bytes**. Its 35 indexed payload checksums matched the earlier full generation. The earlier development export pilot-1 occupies 4,794,811 bytes separately. Its records are excluded from all pilot-2 counts. The CrisisMMD inventory and snapshot storage measurements are separate from the symbolic release. [Public-source measurements](CRISISMMD_COMPATIBILITY_REPORT.md)
