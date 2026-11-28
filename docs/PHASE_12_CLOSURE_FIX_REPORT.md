# Cluster FIX 1: Phase 12 correctness and closure

2026-11-27. Symbolic civilian research simulation, CPU. No training, no learned-policy
experiments, no checkpoint or production source changes. Artifacts:
`D:\SWARM-AID-DATA\runs\phase12\closure-fix`.

| Part | Status |
|---|---|
| 1A issue register | COMPLETE (23 issues) |
| 1B checkpoint compatibility | COMPLETE assessment; compatibility not established |
| 1C operator authority | COMPLETE within SQLite and simulator scope |
| 1D development seeds | PARTIAL: specs fixed; browser run and form default open |
| 1E research methodology | COMPLETE: `PHASE_12_RESEARCH_LIMITATIONS.md` |
| 1F closure assessment | COMPLETE; every acceptance PENDING_OWNER_APPROVAL |
| 1G verification | COMPLETE; frontend and PostgreSQL NOT TESTED |

## Resolved here

Three connected dashboard specs named retired seed 42 five times (Cluster 2 listed four lines and
the form, missing the form-filling step). They now use development seeds 12982–12986, with only
those values changed. A test now rejects non-development seeds in these specs. Through the real
backend API, the new seeds produce what the specs wait for: a pending review, more than ten
observations and incidents (12982), communication degradation (12983), and Model 2 unavailability
then recovery (12984). Conflict (12985) is injected by its spec; 12986 only times pages. This is
**not** a browser test.

## Checkpoint compatibility

| Category | Status |
|---|---|
| File integrity (four files match 12G hashes) | VERIFIED |
| Deserialization and structure | VERIFIED (`best.pt` last loaded in 12G) |
| Historical offline reproducibility | PARTIAL |
| Corrected symbolic runtime | UNESTABLISHED |
| Operator-facing authorization | BLOCKED |

Since the 12J record, one file in the SearchEnv import closure changed:
`agents/command_agent/agent.py` (Phase 13 indexing). SearchEnv builds no command agent. Since
training started, `model1.py` (pause fix) and that file were modified, by file times, which are
only indicative. Other Phase 13 changes are outside the closure. The identity check hashes three
sources and cannot detect any of this.

## Operator authority

57 focused tests passed: operator and observer permissions, mission pause, operator-only resume,
fail-closed missing status, human review, approval and rejection, persistence failure and
recovery. No new defect was found in that scope. Open limits are in
`movement_permission_limitations.json`: no mission authority in the standalone simulator, a
self-issued learned lease, no per-drone backend route, and a possible in-flight tick after
execution pause (read from code, not tested). Learned operator-facing integration stays disabled.

## Closure by scope

| Scope | Status |
|---|---|
| A. Historical offline research | Evidence supports closure with recorded gaps; awaiting approval |
| B. Corrected symbolic runtime | PARTIAL |
| C. Operator-facing integration | BLOCKED |
| D. Publication | PARTIAL: exploratory reporting only |

Phase 14 is not defined in the repository, so which items block it cannot be determined.

## Phase 13 preservation

All seven retained optimizations are present in source and their tests pass. Benchmarks were not
rerun.

## Checks

Full suite 453 passed, 0 failed, 3 skipped (PostgreSQL; two retired-seed tests), none deselected.
Project mypy (226 files), Ruff and `git diff --check` passed. Frontend checks not run.
