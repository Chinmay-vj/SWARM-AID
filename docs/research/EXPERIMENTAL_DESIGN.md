# Experimental design

Use scenario-seed blocks; each treatment sees the same world, horizon, fleet, search area, sensing budget and exogenous failure schedule. Use independent random streams for layout, measurement errors, network faults and policy decisions. Key noise draws by tick, cell and sensor where possible so changes in message count do not perturb the world.

| Treatment | Task allocation and permitted information |
|---|---|
| Independent | Each drone follows a local search order; command collects reports only |
| Conventional cooperative | Fixed disjoint search sectors with deterministic sweep |
| Centralized | Command assigns cells from received reports; local safety always applies |
| Decentralized | Drones share observations and choose local tasks with neighbor coordination |
| Hybrid | Command leases survey/revisit targets; local planner chooses permitted steps toward each target |
| Future MAPPO / QMIX | Swap policy adapter under the same execution-time visibility and communication budget; document any privileged training inputs separately |

Cross coordination with intact, lossy and partitioned links. For perception ablations, retain the same trajectories or replay recorded sensor opportunities. For fusion ablations, replay the same report stream twice and restrict evidence to the first reporting drone in one arm. Keep decision thresholds and adjudication rubric fixed. Use blinded human review or explicitly label deterministic synthetic review as a separate treatment.

Before execution freeze scenario versions, seed lists, horizons, primary comparisons, matching tolerances, sample-size rationale and stopping rules. Separate development seeds from held-out evaluation seeds. Log config and source digests, dependency versions, CPU/OS, provider identities, clock policy, event ordering and all exclusions. Retain JSONL trace and truth in separate stores linked by run ID. Repeat a seed to verify normalized trace identity before unblinding results.

Analyze per-mission paired differences, stratified by disaster family and link condition. Use intervals resampled by seed block, retaining nested drones and victims together. Report censored discovery curves, failed runs, raw denominators and comparison multiplicity. Phase 1 contains no experiment runs.

Fix the decision-time information available to each arm. For independent and decentralized arms, a mission-scoped local task allocator issues bounded leases from the preauthorized mission search scope. It cannot extend offline budgets or override human restrictions. Use the same scope, lease lifetime and safety limits in paired arms. Keep the allocator outside learned policies and record its decisions. Record assignment and renewal traffic in cost comparisons. Compute first-drone membership from capture origin rather than relay identity. Freeze a common incident adjudication rubric and blinded reference labels before paired replay.
