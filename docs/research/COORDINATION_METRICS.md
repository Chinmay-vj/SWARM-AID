# Coordination metrics

| Export field | Measurement |
|---|---|
| coverage_cells_by_tick | Evaluator count of unique grid cells ever sampled by spatial sensors, including reset. Divide by width times height for fractional coverage. |
| cross_agent_duplicate_cells | Sum of each drone's distinct captured cells minus fleet union. Counts one extra for each additional agent covering a cell. A revisit by the same agent adds zero. |
| first_person_capture_ms | First synthetic capture in mission milliseconds by truth identity. Undetected identities are absent. |
| task_final_states / tasks_issued | Command-side task counts at episode end. Completed requires reported arrival. Expired includes unresolved assignments at the horizon. |
| task_workload | Issued survey tasks per member, including undelivered instructions. |
| availability_history | Command-side changes in freshness of reported health. Stale is an uncertainty marker. |
| repeated_reports | Additional reports with an observation ID already seen by command. |
| coordination_conflicts | Recorded inconsistent labels, identity conflicts or task-status errors with time and reference. |
| safety_interventions | Fleet sum of Model 1 non-approved action decisions. Engine invalid counts are reported separately. |
| network | Episode totals and denominators from the Phase 4 router. Pending deliveries count against intended recipient-message pairs at the final barrier. |
| summary | Mean, median, sample standard deviation and episode count for fractional final coverage within each scenario, policy and fleet size. Standard deviation is null for one seed. |

The engine counts people observed at synthetic capture. The command-side reported cell set contains only cells from admitted reports and can be smaller than actual sensor coverage.

The release export includes task_completion_rate, the final completed count divided by issued assignments, or null when none were issued. first_reported_sighting_ms is the earliest observation time among possible-human reports admitted by command, or null if none arrived. Report creation time, command arrival time and evaluator truth capture answer different questions.
