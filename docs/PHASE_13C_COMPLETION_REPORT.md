# Phase 13C completion report: Model 2 evidence processing

2026-11-27. **Complete.** Data: `D:\SWARM-AID-DATA\runs\phase13\cluster1\13c`.

## Cause and change

Each hazard or possible-human report rebuilt a message-id lookup over every finding and scanned
every finding for the same cell. `CommandAgent` now maintains those two indexes as findings are
added. Findings are never removed. If a memory mapping is injected, the old scan is used. No rule,
limit, ordering or output changed.

## Median of three rounds, hazard report

| Reports | Median µs before → after | p95 µs before → after | Whole stream ms before → after |
|---:|---:|---:|---:|
| 100 | 71 → 30 | 105 → 38 | 4.1 → 2.1 |
| 500 | 227 → 33 | 407 → 45 | 60 → 11 |
| 1,000 | 432 → 38 | 879 → 55 | 235 → 28 |
| 2,000 | 934 → 49 | 1,813 → 75 | 958 → 62 |

Environment reports are unchanged (about 8–15 µs). Peak RSS is essentially unchanged
(58.1 → 59.5 MiB at 2,000).

## Equivalence

- 120 random synthetic streams, 31,200 messages, three modes, two capacities: every return value,
  snapshot, checkpoint and restore matched the pre-change module. Exercised stale, duplicate,
  conflict, capacity, expiry, corroboration, operator approval, rejection and review actions.
- Six symbolic fleets (seeds 12900–12905) ended in identical command state.
- Final state hashes match at all four benchmark sizes.
- `tests/integration/test_command_agent.py` passed unchanged.

Not covered: injected assessment, review or urgency providers.

Remaining growth comes from incidents that accumulate many reports and from `expire`, which walks
all incidents; neither was changed.
