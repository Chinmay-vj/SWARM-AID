# Cluster FIX 2: owner decisions and integration closure

2026-11-27 local time (decision date as supplied: 2026-11-28). Symbolic civilian research
simulation. No training, no learned-policy experiments, no protected or retired seeds, nothing
pushed. Artifacts: `D:\SWARM-AID-DATA\runs\phase13\cluster-fix2`.

| Part | Status |
|---|---|
| 2A decisions | Complete |
| 2B development seeds | Complete, with limits below |
| 2C Node.js and frontend | Complete |
| 2D PostgreSQL/PostGIS | Complete |
| 2E dashboard | Complete; render-level performance not measured |
| 2F backend persistence | Complete |
| 2G checks | Complete |
| 2H reports and commit | Complete |

## Owner decisions and Phase 12

D1–D5, D7 and D8 approved, D6 unverified (`PHASE_12_OWNER_DECISION_PACKET.md`). Phase 12 offline
research is **closed with documented limitations**. Corrected symbolic runtime: partial. Checkpoint
compatibility: unestablished. Learned operator-facing integration: blocked. Publication:
exploratory only.

## Development seeds

The mission form requires 12000–12999 and no longer copies the scenario default. The development
API refuses a missing or final-evaluation seed. The simulator CLI refuses an implicit default;
`orchestration run` and headless start require a seed; demo scripts use 12988 and 12989. The
scenario default stays 42 and non-development API behaviour is unchanged. Explicit 42–46 is still
accepted for historical reproduction. `system_demo.py` was not run. `AGENTS.md` still shows
`--seed 42`.

## Environment

Node 24.22.3 LTS and npm 11.19.1 (portable, checksum matched). PostgreSQL 16.16 with PostGIS 3.7.0,
unpacked on D:, localhost only, password authentication, non-superuser test role; no service or
admin rights. The PostgreSQL archive had no checked publisher checksum. The server is stopped.

`npm ci` left the lockfile unchanged. `npm audit` reports 20 advisories (2 low, 12 moderate,
4 high, 2 critical); shipped dependencies: `zod` high, `react-router` and `react-router-dom`
moderate. Nothing was upgraded.

## Database

- The PostGIS test, skipped until now, passes. The backend API suite passes on PostgreSQL
  (65 tests); one audit test needed the PostgreSQL exception class.
- Migration downgrade and re-upgrade work. Stored snapshots verify.
- One 60-tick mission produced identical domain rows on SQLite and PostgreSQL; all 347 located
  observations have matching geometry. No latency comparison is made.

## Dashboard

Type check, lint, 78 tests and build pass. Mock browser tests 12/12 (the very first run had one
Chrome launch failure). Connected browser tests 11/11 twice on emptied databases, after fixing
three test problems: an ambiguous heading locator, environment setup (login rate limit, no stored
experiments) and a stop test that waited for a button the dashboard correctly hides once a mission
ends. A separate script confirmed rejection, "submitted" before validation, and the unreachable
banner without synthetic substitution (screenshots saved).

Load: no long tasks, no overlapping duplicate requests in a 6 s sample, map navigation 77–175 ms in
the earlier runs. No dashboard optimization was justified.

## Checks

Python: 459 passed, 0 failed, 2 skipped (retired seeds). Mypy (228 files), Ruff, pip check and
`git diff --check` passed.

## For the owner's attention

The commit includes earlier work that adds one exception to the data-release gate: an unverified
licence is accepted for `wisard` only, with an owner attestation, for local use.

## Remaining limitations

Checkpoint compatibility; independent safety review; frontend advisories; timeout handling and
render-level performance untested; RTX 2060 untested; off-machine copy not verified.
