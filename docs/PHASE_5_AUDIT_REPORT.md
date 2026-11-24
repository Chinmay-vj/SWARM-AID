# Phase 5 release audit

**READY WITH LIMITATIONS** for finite, trusted simulator experiments and Phase 6 interface development.

## Environment and validation

Reused the existing Windows CPython 3.12.10 virtual environment. Its base interpreter was inaccessible to the sandbox account and accessible under the owning Windows account. Ran pip upgrade (26.3 already installed), editable installation of the dev and simulation extras, pip check, imports, CLI help, full pytest, Ruff and configured strict mypy. Pydantic 2.14.4, NumPy 2.5.5, PettingZoo 1.27.0, Gymnasium 1.4.0 and Pygame 2.6.1 imported. pytest 8.4.2 passed 103 tests with zero failures or skips and two PettingZoo deprecation warnings. Ruff 0.17.6 passed. Mypy 1.20.2 passed across 46 files.

## Findings

| Severity | Finding and disposition |
|---|---|
| Critical / High | No outstanding release blocker identified for trusted offline simulation. |
| Medium | Command ignored locationless observations and could incorporate the location from a conflicting reuse of an observation ID into search progress. Preserve the first observation, count repeats by ID and record conflicts before updating coverage. Regression exercises all three cases. |
| Medium | Duplicate experiment levels could inflate the sample count. Configuration now rejects repeated seeds, fleet sizes, policies and scenario entries. Added regression coverage. |
| Medium | Shared-information changes both peer traffic and assignment selection. Independent is stationary. Their coverage differences cannot isolate the effect of peer collaboration. |
| Low | Added explicit command-reported sighting time and task completion fraction. An empty assignment denominator yields null. README now identifies the correct simulator extra and virtual environment commands. |
| Low | Two upstream deprecation warnings remain. Python 3.11 and a fresh host were outside this verification. |

## Architecture and scope reviewed

- **Contracts, evidence and agent ownership.** Each fleet member owns its local memory and lifecycle. Policies receive public mission geometry and command-reported cells. Observation IDs survive forwarding. The router binds sender identity to a registered session. Raw simulator person identities and complete footprints stay in engine/evaluation paths.
- **Mission, tasks and safety.** The assignment fixture timestamps transitions, preserves task history and checks owner, time and completion evidence. Human overrides and lease validity are checked at Model 1 before engine motion. An arrival report establishes survey-task completion only. Unknown or stale remote health remains uncertain. Conflict records stay available for review.
- **Transport and recovery.** Bounded queues, expiry, duplicate suppression, peer partitioning, loss and recovery use the existing in-process router. Direct outage fixtures exercise endpoint restoration. Physical unavailability and communication disconnection have separate semantics. Router history and receipts remain episode-local.
- **Extensibility and compatibility.** The existing Phase 1 through 4 suites and PettingZoo parallel API test passed. The reward hook defaults to zero. The command snapshot is suitable for an in-process consumer. Durable decision history, production authentication and learned peer observations remain future work.
- **Platform and research scope.** The release executed on CPU without backend or ML extras, training, dataset downloads or model weights. The comparison used the same scenarios and seeds across arms. Release commands and scenario identifiers match the working CLI.

## Execution evidence

The baseline plan produced 18 episodes across three policies, two seeds and three fleet sizes. The additional plan produced ten six-agent shared-information episodes. Checked every CSV coverage against episode JSON, covered plus unobserved cells against grid size, task histories against issued count, and detected identities against per-person capture records. Recomputed delivery event totals and serialized bytes from each six-agent baseline JSONL. Each policy's complete event trace matched the SHA-256 of a separate seed-42 invocation.

| Seed 42 scenario | Final coverage | Delivery ratio | Mean delay, ms |
|---|---:|---:|---:|
| Multiple sightings | 75.8% | 96.1% | 101.2 |
| Agent link interrupted | 79.2% | 95.9% | 105.0 |
| Delay | 68.3% | 84.1% | 403.4 |
| Loss | 74.2% | 61.0% | 105.6 |
| Partition | 100.0% | 96.4% | 100.0 |
| Reordering | 63.3% | 86.2% | 343.8 |
| Duplication | 79.2% | 96.0% | 101.3 |
| Server outage | 70.8% | 96.0% | 110.6 |
| Wildfire | 79.2% | 96.0% | 101.3 |
| Earthquake | 72.5% | 96.1% | 103.6 |

Both interruption fixtures recorded one restoration. The loss fixture recorded 659 dropped attempts. Delivery ratio uses intended recipient-message pairs. Fault scenarios can differ in geometry and eligible recipients. Compare policies within the same scenario.

Local artifacts are under runs/phase5-release. The matched comparison ID is 082eb73bfb104836ab327b4bf1af7783 and the fault sweep ID is 092c4a27dde947bf8702cd4b4758d132. Recreate them with the README commands. The repository already tracked a PowerShell ModuleAnalysisCache at the Phase 4 revision. It was outside the release diff.
