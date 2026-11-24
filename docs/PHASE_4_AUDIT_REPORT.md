# Independent audit of Phases 1 through 4

**Phase 5 assessment: READY WITH LIMITATIONS.** The offline, finite-horizon simulator is suitable for implementing and testing a cooperative policy against existing baselines. Large comparative studies, untrusted provider execution and persistent command operation have additional prerequisites below. No critical defect was identified within the trusted simulation scope.

## Findings and disposition

| Severity | Confirmed defect | Correction and regression evidence |
|---|---|---|
| High | A command processed first at a tick could suppress a valid operator pause at that tick. | Separate revision-checked operator authority from command ordering. A pause clears the lease. Commands cannot install a lease while paused. Tested with colliding timestamps. |
| High | A pre-recovery instruction queued during a server outage could recreate discarded movement authority on restoration. | Require a fresh instruction issued at or after the observed recovery barrier. Test checks clearance, rejection and subsequent valid assignment. |
| High | The safety controller checked initial battery while a move costs two points. A configured reserve above the engine minimum could be crossed. | Check projected battery before approving movement. Test exercises both sides of a 50% reserve boundary. |
| High | An unread, previously admitted control could be consumed after expiry. A repeated submission could also address a new session under an old recipient name. | Both inbox APIs check exclusive expiry at consumption. Pin recipient sessions on first authorized submission for direct and group destinations. Covered synchronous/async reads and both routing modes. |
| Medium | Disabling GPS retained the frame cell in the provider view. Text and IMU readings also exposed absolute position despite their measurement meaning. | Remove filtered localization and omit coordinates on those symbolic readings. A replacement provider inspects the actual admitted frame. Spatial image/environment readings retain their declared grid references. |
| Medium | A replacement fusion provider could insert a future observation into memory before wire validation. | Reject future event times and mismatched view ticks before memory mutation. Tested fail-closed behavior with an injected provider. |
| Medium | Delayed heartbeat receipt refreshed health using arrival time, and negative or repeated acknowledgements could count as successful receipts. | Use monotonically increasing heartbeat creation time. Count the first positive acknowledgement per original pair. Tested delayed, rejected, accepted and duplicate acknowledgements. |
| Low | Diagnostic snapshot consumers could mutate live log dictionaries. Closing an endpoint silently retained unread inbox entries through existing references. A viewer exception skipped Pygame cleanup. | Copy diagnostic history, release and account for unread deliveries, and close the renderer in a finally block. Covered all three paths. |

## Verification coverage

| Requested checks | Evidence and scope |
|---|---|
| 1–4. Architecture, simulator, injection, model replacement | Reviewed provider protocols, Fleet composition, agent constructor and mock implementations. Provider replacements and failure doubles run in tests. Phase 2 policies and the opt-in Phase 4 path both remain covered. Safety uses a concrete independent gate. The baseline provider configuration selects built-ins; new provider names require composition-root wiring. |
| 5–7. Memory, lifecycle, hidden state | Fleet allocates independent agent objects; scoped restore rejects another owner or mission. Public bounds, base and restricted cells are explicit inputs. Hidden-person counterfactual tests compare decision logs. Only the trusted adapter/router samples global positions for routing. Python process isolation is outside this design. |
| 8–11. Inputs, missing modalities, provenance, reasoning/planning | Input admission checks scope, age, evidence and synthetic score. Dropout and conflicting labels have tests. Fusion retains evidence identities and uses a conservative score. Reasoning selects an intent from local history; planning proposes an action under the current lease. Raw imagery and asynchronous sensor alignment remain future work. |
| 12. Independent safety | Safety checks measured position and time, constraints, reserve, lifecycle and human override before engine collision checks. Failure returns hold. Verified restricted, unleased, expired and paused actions plus the corrected cases above. |
| 13–17. Serialization, schemas, endpoints, permissions, deduplication | JSON discriminator round trips, schema versions, size limits, unknown identities, session binding, role pairs, revision-bound overrides and group membership are covered. Receipt lookup is scoped to the mission router. Inbox admission, application acceptance and human confirmation have distinct meanings. |
| 18–21. Failures, recovery, replay, metrics | Tested controlled outage, expiry, delayed packets, heartbeat staleness, deduplication and queue saturation. Independently replayed the healthy run. Verified event counts, pending-at-horizon accounting and recovery times against exported logs. |
| 22–23. Bounds and cleanup | Inbound/outbound queues, local findings and agent histories have configured bounds. Router events, original digests, receipts, delay samples and mock endpoint histories grow with episode traffic. This limits experiment duration and fleet size; these are episode-scoped data structures. GUI and endpoint cleanup have regression tests. |
| 24–26. Platform, dependencies, training | Executed locally on Windows CPython 3.12.10. Runtime and packaging inspection found no mandatory GPU, model weights, paid API or training dependency. Training and datasets contain only .gitkeep files. The combined stack was not rerun on Python 3.11 or installed on a clean host for this audit. |
| 27–28. Model 2 and cooperative experiments | Mock command receives typed reports and preserves source evidence. The PettingZoo parallel compatibility test passes. Model 2 can consume the report stream. The existing PettingZoo observation is a small local vector with a zero test reward; experiments needing peer messages require an explicit, agent-visible observation extension. |

## Actual Windows execution

Baseline before audit edits: 76 passing tests. After corrections: **89 passed**, with two existing PettingZoo deprecation warnings. Ruff lint passed and format verification reported 96 formatted files. Strict mypy with incremental caching disabled found no issues in 40 source files.

The following command was executed with each scenario, using the workspace Python runtime and separate output directories. Both runs reached the 30-step, 3000 ms horizon with six active agents, 5371 captured readings, 17.5% coverage and zero engine-invalid actions.

```powershell
.tools\python\python -m simulation --scenario flood_basic --policy model1 --agents 6 --seed 42 --headless --communication --output runs/audit0
.tools\python\python -m simulation --scenario flood_server_unavailable --policy model1 --agents 6 --seed 42 --headless --communication --output runs/audit1
```

| Metric | Healthy flood | Server outage |
|---|---:|---:|
| Logical submissions | 1343 | 1343 |
| Delivered / intended pairs | 1994 / 2063 | 1994 / 2063 |
| Pending copies at last barrier | 69 | 69 |
| Unique positive acknowledgements | 510 | 510 |
| Serialized attempted bytes | 1530418 | 1530418 |
| Mean / median / p95 delivery delay, ms | 100 / 100 / 100 | 108.12 / 100 / 100 |
| Available endpoint sample fraction | 1.0000 | 0.9875 |
| Connection loss / restoration | 0 / 0 | 1 / 1 |

The outage trace records command loss at 400 ms and restoration at 700 ms. The server caught up on retained messages. The healthy run repeated in a third process produced a byte-identical JSONL trace, SHA-256 A91B64E98B90BB5B1928A768BDABFBB47126C162FFADC7A6898BF1912AC8EF1F. Run metadata has separate experiment IDs and wall timestamps. The health and outage traces had no recorded overflow, rejection or packet loss. Forced-fault tests exercise those branches.

Local evidence: [healthy metrics](../runs/audit0/3c03d35ae3cc479f9aac1057904b4f52.communication.json), [outage metrics](../runs/audit1/ab6b60d20ed94fc880cf0c9b21da0985.communication.json), [outage events](../runs/audit1/ab6b60d20ed94fc880cf0c9b21da0985.communication.jsonl). Run files reside in the ignored runs directory.

## Remaining limitations

Medium: full-event retention and linear scheduling/dedup bookkeeping have no fleet-scale memory or throughput benchmark. Profile or bound these before long sweeps. Priorities are wire metadata; the router services attempts by due time and has no reserved control capacity. Saturated queues can reject controls, which matters when designing safety-sensitive experiments. Delivery and receipts are in memory, with no crash recovery or exactly-once claim.

Low: symbolic confidence scores are uncalibrated. Replay evidence covers the tested configurations and environment. The experiment manifest requires external recording of the policy selection, provider/build versions and invocation for publication-grade reproduction. Protocol role checks assume trusted participants and cannot secure a hostile Python plugin.

There is no outstanding blocker for finite, trusted Phase 5 development. No Phase 5 policy, training, service or deployment was implemented.
