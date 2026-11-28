# Phase 13 cluster 2 handoff (not started)

Needs an explicit owner request. Read `PHASE_13_CLUSTER1_COMPLETION_REPORT.md` and the 13A report;
do not repeat cluster 1.

## Candidate work

- **13D persistence** (largest backend cost): 27 ms median, 154 ms p95 per tick against 13 ms to
  simulate. Snapshots are about 12.6 of 13.3 MB after 60 ticks (measured with a snapshot every 5
  ticks; default 10). Measure query counts single-threaded: Python 3.12 profiling also records
  other threads. Keep one atomic transaction and restore equality; a snapshot format change needs
  a versioned schema and Alembic migration.
- **13F dashboard:** measure first; needs frontend dependencies. Connected runs default to seed
  42, so pass a development seed.
- **13G scalability:** 20 agents take 51–61 ms per tick. Do not change random streams. Engine,
  sensor, messaging and fleet changes can alter learned-policy behaviour **without** failing the
  checkpoint identity check: require trace equality on development seeds.
- **13H final verification:** after the above.

## Carried restrictions

No training. Learned policies disabled on operator-facing missions. Safety, authorization and
operator behaviour unchanged; operator-authority tests must keep passing. PostgreSQL and dashboard
unverified. Seeds 900000–900099 locked, 42–46 retired. Artifacts on D:. No commit or push without
approval; source is uncommitted and no off-machine copy is verified.
