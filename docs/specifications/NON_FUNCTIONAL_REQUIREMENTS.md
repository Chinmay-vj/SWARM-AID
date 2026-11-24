# Non-functional requirements

| Property | Design requirement | Verification |
|---|---|---|
| Portability | CPU-only Windows, Python 3.11 or 3.12; network-free operation after setup | Run headless smoke check and contract suite offline |
| Determinism | Canonical event ordering, seeded named random streams, mission clock | Compare normalized event hashes across repeated runs |
| Reliability | Bounded mailboxes, retry budget and explicit gap accounting | Inject loss, delay, duplicate and disconnect; reconcile delivery counts |
| Maintainability | Provider protocols and typed immutable records; no vendor imports in core | Static typing, dependency review and protocol conformance tests |
| Observability | JSONL events carry run, mission, tick, actor, correlation and reason | Trace one rejected recommendation back to its input |
| Performance | Record tick runtime, queue depth and peak memory by swarm size | Publish CPU model and distributions alongside run config |
| Authority | Authenticated actor and mission scope checked at ingestion and commit | Cross-mission commands and stale approvals have zero effects |
| Privacy | Use only synthetic evidence in prototype; redact raw sensor content from logs | Inspect representative exports and access denial paths |
| Resource bounds | Configure queue, replay window, horizon and artifact quota | Exercise saturation and verify controlled drop or hold |

No measured performance or availability target has been established. Before comparative runs, freeze experiment budgets and failure thresholds in the manifest. Record aborted runs in the same accounting as completed runs.
