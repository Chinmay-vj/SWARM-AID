# Phase 13 cluster 2 completion report (13D, 13F)

2026-11-27, about 12 minutes. **Cluster status: partial.** No training, no protected or retired
seeds, no operator, movement or coordination changes. Phase 12 remains conditionally closed.

| Part | Status |
|---|---|
| 13D communication and backend | Complete except PostgreSQL (blocked) |
| 13F dashboard | Blocked: no Node.js |

Detail: `PHASE_13D_COMPLETION_REPORT.md` and `PHASE_13F_COMPLETION_REPORT.md`.

## Checks

- Full suite: 452 passed, 0 failed, 3 skipped (PostgreSQL; two retired-seed tests).
- Project mypy (226 files), Ruff, `git diff --check`: passed.
- Not run: all frontend checks, PostgreSQL, pip check (no dependency change).

## Compatibility

`backend/integrations/model2_adapter.py` and `backend/api/v1/missions.py` changed; learned-policy
behaviour does not use them. MARL checkpoint and `marl.py` hashes are unchanged. Corrected-runtime
compatibility is still unestablished and learned operator-facing integration stays disabled.

## Reproduce

```powershell
.\.venv\Scripts\python.exe -u -m evaluation.phase13_cluster2 compare
```

About two minutes, alternating old and new adapters. It overwrites `13d\runs.json` and the query
and equivalence records. The snapshot-list change is measured separately
(`13d\snapshot_listing.py`).

## Pending owner decisions

Compressed snapshot format; installing Node.js; providing a PostgreSQL test database; and the
earlier ones (Phase 12 closure, checkpoint compatibility, movement permission, default seed,
RTX 2060 residency and precision).
