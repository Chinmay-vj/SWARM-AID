# Model 2 baseline experiments

Use the README command with configs/experiments/phase6_baselines.json. The matrix crosses three conditions, fleet sizes 3, 6 and 10, and five fixtures (basic flood, multiple sightings, server outage, wildfire and earthquake). The included plan uses seed 42 and a scripted operator. All conditions use the Phase 5 shared-information movement policy. Operator feedback changes traffic, so inspect admitted report counts before attributing differences solely to assessment.

Direct forwards admitted findings with source references. Rules creates separate review records for individual hazards and sightings. Fusion uses fresh findings grouped by reported cell and category. An operator decision may already be stale when it reaches command. The script intentionally exercises the revision check. It does not represent the timing or accuracy of a human rescue team.

The runner creates a UUID-named directory containing comparison.csv and one episode JSON per combination. JSON includes effective scenario and Model 2 settings, synthetic truth comparisons, decision counts, router metrics, simulated duration and termination. IDs and wall-clock runtime of the host should be excluded from seeded semantic comparisons.
