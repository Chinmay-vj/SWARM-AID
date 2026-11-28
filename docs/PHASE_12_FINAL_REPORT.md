# Phase 12 final report: multi-agent learning for symbolic civilian search

2026-11-27. **Recommended status: conditionally complete** (owner acceptance pending). The offline
exploratory research scope is complete. Operator-facing use of learned policies is **blocked**.
Nothing here concerns physical drones or deployment.

## What was built

- A PettingZoo `SearchEnv` over the existing engine, network and safety gate; 240-value local
  observations; five movement actions with masks; reward-1 (preserved) and reward-2.
- Conventional comparators: independent (stationary, weak), fixed sector, shared information,
  masked random.
- IPPO and MAPPO with a shared local actor; MAPPO's critic pools local observations in training.

## Training

One run per algorithm (learner seed 1), 300,000 environment steps each, CPU, about 80–85 minutes.
Both first reached 99% validation coverage at 14,400 steps. `best.pt` stayed at update 30 because
later ties never replaced it; `latest.pt` is the provisional offline candidate.

## Findings

- Coverage saturates: the task is too easy. Training used 900 of an intended 2,700 seed–scenario
  combinations; flood and wildfire share starts and blocked cells.
- The corroboration reward largely duplicates coverage. The uncertainty reward never fired in
  training.
- 900 robustness episodes were run on development validation seeds.

Coverage AUC (sensed cells over time, not rescue outcomes):

| Condition | IPPO | MAPPO | Shared information |
|---|---:|---:|---:|
| Nominal | 86.1% | 86.1% | 63.4% |
| Missing observations | 74.9% | 63.2% | 58.7% |
| Radio outage and partition | 67.1% | 51.5% | 56.4% |
| Message delay | 86.1% | 85.4% | 41.4% |

These compare two individual trained policies. No claim of algorithm superiority or equivalence is
supported. The metric and checkpoint were chosen after seeing results, and the heuristics are a
low bar.

## Operator-pause defect

A mission-wide pause did not stop learned policies (47–65 IPPO and 53–62 MAPPO moves while
paused), and heuristic leases also continued (7–10). `Fleet.advance` now blocks travel unless the
mission is active; all counts became 0. The backend route is verified on SQLite.

## Restrictions that remain

- Learned policies are disabled on operator-facing fleets.
- Checkpoint compatibility with the corrected runtime is not established.
- Standalone SearchEnv has no mission authority.
- PostgreSQL, perception models and dashboard were not tested in these phases.
- Phase 12I-7 remains partial.

## Test results

436 passed, 0 failed, 3 skipped. Ruff and diff check pass. Project mypy reports 6 errors in one
Phase 11 test file. Frontend checks were not run.

## Reproducibility gaps

Source is uncommitted; no commit or launch record exists for training; no authorization record
exists; earlier test runs executed retired seeds; no off-machine copy is verified. Protected seeds
900000–900099 were never executed.

## Deferred

A nearest-unsearched comparator; a harder task; the pairing and checkpoint-selection corrections;
reward revision; multiple learner seeds (about 1.4 h pilot, 8.3 h for 3 seeds, 13.8 h for 5, at
current throughput); protected final evaluation. More training on the current task is not
justified. Owner decisions: `owner_decisions_pending.json` under
`D:\SWARM-AID-DATA\runs\phase12\phase12j`.

Detail: `PHASE_12A_D`, `12E_F`, `12G`, `12H`, `12I`, `12I_FIX` and `12J` reports.

## Addendum: Cluster FIX 1 (the findings above are unchanged)

- Later full suite: 453 passed, 3 skipped. The project mypy errors were fixed in Phase 13A.
- Connected dashboard specs no longer use retired seed 42; no browser run has verified them.
- Checkpoint compatibility is still not established, and Phase 13 added runtime changes the
  identity check cannot see.
- Closure scopes and decisions: `PHASE_12_CLOSURE_FIX_REPORT.md` and
  `PHASE_12_OWNER_DECISION_PACKET.md`. Acceptance is still pending.

## Addendum: owner decisions (2026-11-28)

Under decisions D1 and D5 the **historical offline research scope is CLOSED WITH DOCUMENTED
LIMITATIONS**. Corrected symbolic runtime: PARTIAL. Checkpoint compatibility: UNESTABLISHED.
Learned operator-facing integration: BLOCKED. Publication: EXPLORATORY ONLY. The earlier
conditional-closure text is kept above as the record of its time.
