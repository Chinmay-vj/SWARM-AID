# Phase 2 simulation contract

Build a headless fixed-step, two-dimensional grid on a CPU. A scenario declares dimensions, navigable cells, private victim locations, hazards, sensor radii, noise parameters, drone starts, battery budgets, communication radius, queue limits and a finite horizon. Validate bounds, distinct start occupancy and feasible initial budgets. Treat flood, forest fire, earthquake, landslide and cyclone as named scenario profiles with independently configurable blocked cells, visibility and communications. Begin with one static flood fixture; additional profiles can reuse the same engine.

1. Reset named pseudorandom streams for layout, sensor noise and network faults. Derive them from a recorded root seed and stable component identifiers.
2. At tick t deliver due messages in deterministic order (delivery tick, recipient, sender, sequence). Generate each drone's view from the same pre-step world. Limit sensing by footprint, visibility, modality and seeded error.
3. Collect one discrete intent per active drone. Survey/revisit moves at most one adjacent cell toward a target. Hold consumes one idle tick. End terminates the agent. Apply policy, bounds and reserve checks before commitment.
4. Resolve same-cell conflicts and position swaps by holding conflicting movers. Reject moves into cells occupied by an agent that will stay; propagate holds until stable. Apply all remaining moves simultaneously.
5. Debit configured idle, movement, sensor and transmission costs. Advance hazards through the scenario adapter. Record accepted actions, energy and coverage. Enqueue transmissions with a minimum one-tick delay.
6. End on authorized termination, horizon or all drones ended. Record termination reason separately from meeting the mission coverage/search objective.

A PettingZoo ParallelEnv adapter will expose per-agent Gymnasium observation/action spaces with fixed-size local patches, missingness masks, battery, local time and bounded message summaries. Use a target-cell index plus an intent code and action mask. Keep evaluator truth outside observations and agent-facing infos. Optional Pygame reads snapshots without advancing time. Phase 2 must freeze sensor error distributions, map dimensions, goal thresholds, budgets and stream derivation in a versioned scenario schema before baseline comparison.

Acceptance fixture: two drones, one hidden synthetic person, partial overlap and a scheduled link outage. Verify hidden cells stay hidden, same-seed trace repeats, collisions resolve symmetrically, stale tasks hold and the offline evaluator can score a missed detection.

Keep the root seed, hidden scenario file, world object, evaluator labels and unrestricted artifact resolver out of all policy constructors and messages. Identifiers, filenames, action masks, rewards, termination signals and diagnostics can reveal hidden state. Expose only authorized public constraints and locally observable outcomes. Run a paired visibility test with identical visible state and random streams but different hidden victims. Before a sensor can distinguish them, normalized agent inputs and policy-visible metadata must agree. In-process isolation is an architectural boundary for trusted adapters; it cannot sandbox arbitrary third-party Python.

For equal delivery ticks, break ties using recipient, source, session, original destination and sequence. Freeze or derive IDs from stable run-local event keys for replay comparisons, and exclude wall timestamps from normalized traces.
