# Baseline experiments

Run the two JSON plans described in the README. The main plan crosses seeds 42 and 43, fleet sizes 3, 6 and 10, and three policies on flood_basic. The fault plan runs the shared-information policy with six agents and seed 42. For new experiments, use scenario filenames or packaged names. A scenario can specify assignment_ticks and a sectors mapping from agent IDs to ordered arrays of grid cells.

Each invocation creates a new experiment directory. Compare episode scenario snapshots before attributing a difference to policy. The independent arm is stationary, so differences from it combine movement and coordination. Fixed and shared arms both use finite movement leases. The shared arm also enables peer traffic. The two-seed comparisons exercise software behavior and do not estimate general disaster-search performance.

See the [Phase 5 report](../PHASE_5_COMPLETION_REPORT.md) for the measured summaries.

The release run reproduced the three six-agent communication traces across independent process invocations and verified all 28 CSV coverage values against their episode JSON. See the [release audit](../PHASE_5_AUDIT_REPORT.md).
