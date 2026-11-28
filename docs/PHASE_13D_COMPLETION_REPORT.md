# Phase 13D completion report: communication and backend

2026-11-27. **Complete except PostgreSQL (blocked).** SQLite, disposable databases, development
seed 12990. Data: `D:\SWARM-AID-DATA\runs\phase13\cluster2\13d`.

## Cause

Per tick, persistence issued about 125 SQL statements. It re-queried every task ever issued (cost
grows with mission length, by code) and re-read agent rows about 11 times. SQLAlchemy accounts for
about half of own time; commit about a fifth; snapshot digesting about 1%. Python 3.12 profiles
include all threads, so this harness drives persistence from one thread.

## Retained

1. A stored task with no new history or report is not queried.
2. Agent rows are held for the duration of one unit of work.
3. The snapshot list endpoint no longer loads payloads that its response does not contain.

Transactions, durability, schema, identifiers, events and API responses are unchanged.

## Persistence, 6 agents, 60 ticks, median of three alternating rounds

| Metric | Snapshot every 10 (default) | Snapshot every 5 |
|---|---|---|
| Median ms | 22.8 → 18.5 (−19%) | 24.7 → 20.0 (−19%) |
| Mean ms | 37.9 → 31.8 (−16%) | 44.9 → 40.2 (−11%) |
| p95 ms | 142.7 → 116.2 (−19%) | 142.4 → 141.3 (none) |
| Checkpoint tick median ms | 42.3 → 38.3 | 69.8 → 54.3 |
| Peak RSS MiB | 164 → 164 | 188 → 189 |
| Database bytes | 8.0 MB, unchanged | 13.1 MB, unchanged |

p95 rounds are noisy (every 10: 121–155 before, 114–122 after). Statements per tick: 124.7 → 85.2;
task selects 1,980 → 226; agent selects 674 → 60. These numbers are lower than Phase 13A's 27 ms,
which was measured inside the running application loop.

Snapshot list query (39 rows): 112 → 7.2 ms (15.5×), identical responses.

## Integrity

- All rows of all domain tables matched between old and new code after canonicalizing run-specific
  ids and times, at both snapshot settings.
- Injected failures every third tick: after retry, task rows and event history stay exact.
- All stored snapshot digests verified. Backend tests: 63 passed, 1 skipped.

## Snapshot storage (study only; format unchanged)

Default setting: snapshots are 5.87 MB of 6.74 MB logical data (plus a WAL of up to 4.7 MB before
checkpointing). Each checkpoint repeats the whole replay journal (210 → 1,402 entries).

| Codec | Snapshot bytes | Largest checkpoint: compress / decompress ms |
|---|---:|---|
| Stored JSON | 5,862,787 | — |
| zlib 1 | 1,107,642 (−81%) | 4.6 / 1.7 |
| zlib 6 | 949,305 (−84%) | 10.1 / 1.6 |

All round trips were exact. **Proposal, not adopted:** zlib 1 for new rows behind a new
`schema_version`, with the old format still readable, an Alembic migration and restore tests. It
adds roughly 9 ms to a default checkpoint tick and needs an owner decision.

## Messages

721-byte envelope: serialize 4.3 µs, validate 7.7 µs, exact round trip. Not changed.

## PostgreSQL

BLOCKED: no server, client or Docker; `SWARM_TEST_POSTGRES_URL` unset. Nothing was installed.
SQLite results say nothing about PostgreSQL.

## Update (Cluster FIX 2): PostgreSQL verified; 13D COMPLETE

PostgreSQL 16.16 with PostGIS 3.7.0: the PostGIS test and 65 backend tests pass, migration
round trip works, and one mission stored identical domain rows on SQLite and PostgreSQL. The
BLOCKED statement above records the state at the time of cluster 2.
