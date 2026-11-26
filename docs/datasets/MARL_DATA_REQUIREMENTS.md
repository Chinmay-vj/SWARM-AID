# Future MARL episode requirements

Use a release manifest with scenario/config digest, disaster profile, grid and horizon, named seed streams, fleet size, baseline, code revision, host environment and termination reason. Label the execution path (integrated SimulationContext or RescueEnv). Keep train, validation and reserved evaluation episodes disjoint.

| Record | Required data |
|---|---|
| Episode | Run ID, mission, scenario/seed, policy configuration, initial active agents and reset semantics. Record gaps and failed/truncated episodes. |
| Per-agent step | Agent ID, tick, own observation, proposed action, allowed action and resolved outcome where available, reward definition/version, termination and truncation. Preserve missing values for fields unavailable on a given path. |
| Communication and coordination | Configured delay/loss/dropout/outages, timed delivery and acceptance, lease, task status, agent availability and changes in active set. Record public/own information only in observations. |
| Evaluation | Export coverage, people observed, false positives, misses, availability, battery use and invalid actions with units and denominators. Restrict truth-derived metrics to evaluator outputs. Compare fixed-sector, independent and shared-information baselines on matched seeds. |
| Reproduction | Persist manifest and configuration digests, tick interval, policy/provider versions when known, seed and deterministic fingerprint. A restarted mission is a new episode. |

RescueEnv currently returns an int32 vector of length four per agent (x, y, rounded battery percent, own possible-human reading count). Unknown position is -1. Action space is Discrete(10); the default injected reward is zero. Inactive agents terminate and active agents truncate at horizon. The wrapper steps the bare engine. Integrated transport, leases, Model 1 safety and Model 2 decisions must come from integrated records. No new observation space, reward or coordination policy is defined here.
