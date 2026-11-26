# Phase 10F field simulation and dataset verification

The six field scenarios produced 4,975 symbolic Model 2 examples from 72 development episodes and 9,465 Model 1 reports. All examples await independent review. The release provides development data for studying evidence handling under simulated faults. Rescue effectiveness and assessment accuracy remain unmeasured.

## Release and replay

The frozen `field-v1` matrix used 12 episodes per family, fleets of 1, 2, 3, 5 and 8, and seeds 1100–1171. Flood, wildfire, earthquake and missing-person search contributed 3,321 training examples. Cyclone and landslide contributed 1,654 validation examples. The six batch directories under `D:\SWARM-AID-DATA\processed\model2` occupy 68,739,396 bytes. The matrix summary is in `manifests/model2/field-v1/summary.json` under the same data root. [Matrix configuration](../configs/datasets/field_matrix.json) · [Scenario mechanisms and assumptions](simulation/FIELD_SCENARIOS.md)

The matrix records 4,951 native examples and 24 controlled variants, with six each for conflict, relay, repeat and stale evidence. Across both sets, 63 examples carry a conflicting relationship label. There are 4,969 rule-derived targets, six unresolved targets and 196 queued review forms. Twenty-one simplified presentation patterns occur in both partitions. Family separation alone therefore gives limited evidence of independence.

The saved replay manifest covers all 72 episodes. Of 9,465 report-linked frames, 6,154 lacked at least one configured modality. For 3,342 possible-human report references, the evaluator recorded a visible civilian at the reported cell and time in 2,075 cases. A person can generate several reports. These are report counts and cannot establish person-level recall. Operational availability and evaluator references live in separate files under `simulation/field-v1` in the data root. Verification on 26 November 2026 matched 288 SHA-256 checksums across 12 replay payloads, six release manifests and 270 batch payloads.

## Matched development comparisons

Both plans ran on flood and missing-person search with three and five agents at seeds 1801 and 1802. Each policy or mode ran on the same eight combinations. [Comparison plans and reproduction commands](research/SIMULATION_EVALUATION_PROTOCOL.md)

| Coordination policy | Mean final grid coverage |
|---|---:|
| Independent | 15.2% |
| Fixed sector | 90.8% |
| Shared information | 95.7% |

Coverage counts distinct cells in the accumulated sensor footprint divided by all 99 grid cells. The eight episodes receive equal weight. The independent configuration issued zero coordination tasks. The comparison does not isolate the effect of information sharing from the policies' movement and assignment behavior.

| Command mode | Observations | Incidents | Updates delivered to operator |
|---|---:|---:|---:|
| Direct forwarding | 1,163 | 0 | 1,105 |
| Individual rules | 1,163 | 689 | 656 |
| Multi-agent fusion | 1,163 | 285 | 338 |

Each row sums eight episodes. Scripted review was disabled and zero decisions were sent. Fusion produced fewer operator updates on these fixtures. Independent adjudication would be needed to determine whether grouped reports referred to the same incident or whether an important alert was missed. Local episode files and comparison CSVs are in `runs/field-coordination/426ec59a532c4393a4021565817c3903` and `runs/field-command/7d96489824e34d239db714099f70df5a`.

The fixtures use symbolic observations and uncalibrated sensing parameters. Each comparison covers two layouts and two development seeds. Domain review, physical calibration and a held-out evaluation remain open. [Simulator gap analysis](research/SIMULATION_GAP_ANALYSIS.md)

## Repository verification

Checks ran from the repository root with `.tools/phase10a-check/python.exe`. Pytest reported 261 passed, one skipped and three dependency deprecation warnings in 113.27 seconds. Ruff passed. Strict mypy passed across 140 files.
