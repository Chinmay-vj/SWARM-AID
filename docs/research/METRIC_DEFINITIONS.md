# Metric definitions (Phase 9 verification)

"Operational" metrics use only what agents, Model 2 and operators could know. "Evaluator-only"
metrics use simulator ground truth and appear only in research exports, the `evaluator_only`
section of headless results and the research matrix columns prefixed `evaluator_`.

Missing data: a metric whose denominator is zero is `null`, never 0; runs that did not complete
are excluded from aggregates and counted as failed or unsupported.

## Evaluator-only (`evaluation/results.py`)

| Metric | Definition | Unit | Calculation | Aggregation |
|---|---|---|---|---|
| `coverage` | fraction of all map cells sampled by spatial modalities | 0–1 | `len(engine.covered) / cells` | mean, median, sample SD across seeds |
| `people_observed` | unique visible ground-truth people detected at capture | count | `len(engine.seen)` | mean |
| `missed` | visible person-modality opportunities missed | count | engine counter | sum/mean |
| `false_positive` | spurious modality-cell detections | count | engine counter | sum/mean |
| `observations` | captured symbolic readings, including at reset | count | engine counter | mean |
| `steps`, `duration_ms` | completed transitions; simulated elapsed time | ticks; ms | `t`, `t × tick_ms` | — |
| `battery_used` | fleet battery percentage points spent | points | `Σ(100 − battery)` | mean |
| `invalid` | rejected action proposals at the engine | count | engine counter | sum |
| `unavailable` | inactive drones at the final tick | count | `drones − active` | — |
| `availability` | connected active-agent samples / active samples | 0–1 or null | radio samples | mean |
| `first_person_capture_ms` (Phase 5 episodes) | first capture per person | ms | engine record | — |
| `cross_agent_duplicate_cells` (Phase 5) | search overlap: cells covered by more than one agent | count | `Σ per-agent cells − union` | mean |
| `false_sighting_fraction`, `missed_people_fraction` (Phase 6) | delivered sightings without a matching person; people never matched | 0–1 or null | truth matching per delivered report | mean |

## Operational

| Metric | Definition | Unit | Source |
|---|---|---|---|
| `agent_reported_cells` (`reported_cells`) | cells that agents reported as surveyed: **agent-estimated coverage** | count | coordination fixture |
| `tasks_issued`, `task_final_states`, `task_completion_rate` | survey tasks and their last state | count, 0–1 | task registry |
| `coordination_conflicts` | conflicting coordinator vs reported task information | count | coordination fixture |
| `repeated_reports` | duplicate reports of an already reported cell | count | coordination fixture |
| `observations_reported` / `model2_admitted_findings` | reports admitted by Model 2 | count | Model 2 |
| `model2_counts` | Model 2 processing outcomes (`admitted`, `duplicate`, `conflict`, `stale`, `capacity`, `offline`, `recovered`, ...) | counts | Model 2 event counter |
| `model2_incidents` | incidents Model 2 opened | count | Model 2 |
| `first_reported_sighting_ms` (Phase 5) / `first_operator_sighting_ms` (Phase 6) | discovery time as reported, not truth | ms | transport history |
| communication `generated`, `delivered`, `dropped`, `duplicate`, `expired`, `rejected`, `overflow` | router events | count | router |
| `delivery_ratio` | receipts / intended (recipient, message) pairs | 0–1 or null | router |
| `mean_ms`, `median_ms`, `p95_ms` | delivery latency (simulation time) | ms | router; p95 nearest rank `ceil(0.95n)` |
| `recovery_ms` | durations from connection loss to restoration | ms list | router |
| `safety_interventions` | actions or leases changed by the independent safety check | count | Model 1 health |
| human review latency | decision `submitted_at` → `resolved_at` | wall-clock | `human_decisions` (export) |
| incident assessment latency | report `received_ms` → incident revision `sim_time_ms` | ms | exports (not aggregated automatically) |

Agent-estimated coverage (`agent_reported_cells`) and evaluator-measured coverage (`coverage`)
are deliberately separate and must not be compared as if they measured the same thing.

## Performance (Phase 9 runner)

`step_ms` and `router_pending` report `n`, mean, median, p95, p99 (nearest rank), min and max.
Wall-clock values are host-dependent and nondeterministic.

## Not computed

No accuracy, precision, recall or trained-model performance metric is computed: there are no
trained models and no labelled datasets. Phase 6's false-sighting fraction compares rule-based
outputs with simulator truth; it is not a perception-accuracy metric.
