# Cluster FIX 2 handoff (not started)

Needs an explicit owner request. Read `PHASE_12_CLOSURE_FIX_REPORT.md` and
`PHASE_12_OWNER_DECISION_PACKET.md`; the issue register is
`D:\SWARM-AID-DATA\runs\phase12\closure-fix\outstanding_issue_register.json`.

## Candidates, by dependency

| Needs | Work |
|---|---|
| Decision D4 | Seed entry in the mission form; demo scripts and CLI |
| Node.js approval | Frontend type check, lint, tests, build; mock and connected e2e; verify the re-seeded specs in a browser |
| PostgreSQL test database | Run the PostGIS migration test and backend checks |
| Decision D7 | Commit and off-machine copy (regenerate the migration manifest first) |
| Nothing | Bounded test of an in-flight tick around execution pause, without changing behaviour |

## Carried restrictions

Learned operator-facing integration disabled. No training. No movement, coordination or policy
work. Preserve the Phase 13 optimizations. Seeds 900000–900099 locked, 42–46 retired.
`PHASE_13_CLUSTER3_HANDOFF.md` (13G, 13H) remains separately pending.
