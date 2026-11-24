# Phase 8 completion report: human rescue command dashboard

**Date:** 2026-11-24 · **Branch:** `main` (uncommitted; awaiting the independent Phase 8 audit)
**Readiness:** **READY WITH LIMITATIONS** (see section 29)

Simulation research only. The dashboard visualizes reported simulation state and relays human
decisions; it performs no reasoning, has no physical drone control and makes no claim about
real-world rescue reliability. No datasets were collected, no models were trained or
downloaded, and Phase 9 was not started.

## 1. Existing MVP assessment

| Item | Classification |
|---|---|
| `frontend/{index.html,app.js,styles.css}` (308 lines, vanilla JS) | Complete and verified as a **synthetic-only** presentation demo |
| MVP "Connected Simulation" option | Not implemented: it showed a toast and reverted to synthetic; backend incompatible |
| MVP backend check | Unauthenticated `fetch` of `/health/ready` only |
| MVP map, fleet, incidents, recommendations, network, charts | Synthetic only; useful mechanics and visual design |

The MVP was kept unchanged in `frontend/legacy-mvp/`. Its palette became the dark-theme design
tokens, and its deterministic playback was ported into the new synthetic engine.

Repository at start: single worktree `D:\SWARM-AID` on `main`, HEAD `d0d471b` (tag `v0.6.0`),
Phase 7 backend present but **uncommitted** (left as the user's work). Remote `origin` is a
placeholder URL (`YOUR_USERNAME`); it was not used. No other agent modified the workspace
during the session.

Phase 7 readiness, verified before any change: `pip check` clean; pytest 173 passed, 1 skipped
(PostgreSQL only); Ruff clean; strict mypy clean (110 files). The live server on SQLite was
checked end to end: health, readiness, OpenAPI (76 paths), auth, mission lifecycle, simulation,
Model 1/2 persistence, review queue, decisions (202 → accepted), stale 409, idempotent replay,
cross-mission 404, refresh rotation and reuse rejection, and WebSocket (17 event types).

## 2. Implementation summary

- A React 18 + TypeScript strict + Vite dashboard: 21 lazy routes and about 13,800 lines of
  source. It has one `DataProvider` interface with two isolated implementations, Connected
  (Phase 7 REST + WebSocket) and Synthetic (deterministic in-browser engine with 10 presets).
- Runtime Zod contracts for every backend response, a central API client and a resilient
  WebSocket stream.
- Permission-aware UI mirroring the backend matrix, human-oversight workflows with version
  binding and idempotency, and measured research analytics and exports.
- Unit, integration, mock e2e, connected e2e, axe accessibility and performance tests.
- Three minimal backend additions with regression tests (section 7).

## 3. Repository structure (added/changed)

```text
frontend/            new app (package.json, lock file, vite/ts/eslint/prettier/playwright configs)
  legacy-mvp/        presentation MVP (moved, unchanged)
  src/ app contracts services stores hooks lib components features styles
  tests/ unit integration e2e/{mock,connected}
backend/api/v1/catalog.py, backend/services/catalog.py      new read-only catalog endpoints
backend/core/config.py, backend/application.py, migrations/env.py   narrow changes
tests/backend_api/test_catalog.py, tests/backend_api/test_database.py (1 test added)
scripts/start_dashboard.ps1
docs/frontend/*.md (4), docs/PHASE_8_COMPLETION_REPORT.md
docs/backend/API_REFERENCE.md, README.md, AGENTS.md          updated sections
```

## 4. Files created and modified

**Created:**
- `frontend/` app files (sources in section 3) and `frontend/README.md`
- `backend/api/v1/catalog.py`, `backend/services/catalog.py`, `tests/backend_api/test_catalog.py`
- `scripts/start_dashboard.ps1`
- `docs/frontend/FRONTEND_ARCHITECTURE.md`, `API_INTEGRATION.md`, `OVERSIGHT_ANALYTICS_DEMO.md`,
  `QUALITY_AND_OPERATIONS.md`, and this report

**Modified:**
- `backend/core/config.py` (adds `configured_database_url`, `experiments_dir`)
- `backend/application.py` (registers the catalog router)
- `migrations/env.py` (URL precedence)
- `tests/backend_api/test_database.py` (+1 test)
- `docs/backend/API_REFERENCE.md` (catalog row)
- `README.md` (Phase 8 section)
- `AGENTS.md` (Phase 8 row; corrected the outdated "backend and dashboard remain design work"
  sentence)

**Moved:** `frontend/{index.html,app.js,styles.css}` → `frontend/legacy-mvp/`

**Local only (git-ignored):**
- `.env` (generated development secret)
- `runs/backend/phase8_dev.db` and `runs/backend/dev-credentials.env` (five development
  accounts, generated password)
- `runs/frontend/phase8-performance.json`
- `runs/backend/phase8-regression.txt`

## 5. Architecture decisions

1. **Provider interface, not mode flags in components.** It keeps the sources isolated: query
   keys are prefixed by mode, and a mode switch logs out and clears all caches. Lint forbids
   UI imports of synthetic code.
2. **Synthetic engine emits backend-shaped records.** Both sources render through identical
   pages and are validated by the same schemas.
3. **Same-origin Vite proxy.** Backend CORS stays empty, and production preview sends a strict
   CSP.
4. **Plain CSS tokens and native `<dialog>`.** These replace Tailwind and shadcn: they preserve
   the MVP look, reduce dependencies, and give accessible modals.
5. **Injected providers.** Tests stub `DataProvider` directly, so MSW isn't needed.
6. **Bearer token design kept.** The backend has no cookie mode; trade-offs are documented.
7. **Hand-written SVG map in grid coordinates.** No external map services, no GPS assumption.
8. **Analytics time series built from `METRICS_UPDATED` events.** These are measured; nothing
   is interpolated.
9. **The review deadline issue is a UX problem, not a backend change.** The dashboard steers
   users to pause before reviewing.

## 6. Completed dashboard pages

All are implemented and render in both modes; "verified" means exercised by automated tests:

- Sign-in (mode choice, demo role) — verified
- Missions (list, filter, paginate, create) — verified, connected create in e2e
- Overview (metrics, map, review queue, events, fleet, incidents, hazards, lifecycle controls)
  — verified
- Live map (layers, legend, pan/zoom/fit/reset, selection, entity list) — verified
- Fleet (grid/table, search, condition filter) and agent detail (overview, status, positions,
  observations, events) — verified
- Observations (filters, pagination, detail, provenance) — verified
- Evidence (group source, modality filter, gallery, detail, comparison, provenance, media) —
  verified for reference-only evidence; stored-media rendering not exercised (see section 26)
- Incidents (filters, grouping) and incident workspace (actions, evidence, assessments,
  recommendations, transitions, decisions) — verified
- Model 2 monitoring — verified (connected output present)
- Recommendations and recommendation detail (versions, diff, history, evidence, decisions) —
  verified
- Human review (queue, alerts, decision history, simulated override) — verified; override
  submission not exercised e2e
- Tasks and coordination; environment and hazards; communication network; event timeline —
  verified
- Research analytics and exports; experiment results — verified (connected)
- System health (probe, client API metrics, admin details); settings; not found — verified;
  admin health details not e2e-tested (covered by type contracts and a manual API check)

## 7. Backend endpoint inventory and backend changes

The full table is in [docs/frontend/API_INTEGRATION.md](frontend/API_INTEGRATION.md). It covers
the 76 Phase 7 paths plus 3 added. Backend changes, each with regression tests:

| Change | Reason | Test |
|---|---|---|
| `GET /api/v1/scenarios` | Create-mission form needs the real scenario registry; returns configuration only (no terrain, hazards or people) | `test_scenarios_list_configuration_without_ground_truth` |
| `GET /api/v1/experiments`, `/experiments/{id}` (global researcher/admin) | Phase 5/6 results existed only as files | `test_experiments_require_research_role_and_return_measured_rows` (role gate, families, metadata, no paths, traversal → 404) |
| `migrations/env.py` uses `configured_database_url()` (env → `.env`) | **Defect:** Alembic ignored `.env`, so following the README migrated a different database from the one the server opened | `test_migration_url_follows_backend_settings_precedence` |

No schema migration, no change to existing response shapes, no security relaxation.

## 8. Authentication and authorization results

- **Verified connected:**
  - Login, `/auth/me`, and logout with refresh revocation.
  - Single-flight refresh on 401 (unit) and refresh reuse rejection (API).
  - Session restore after a browser reload (e2e).
  - Login rate limiting surfaced as a clear message (observed during repeated runs).
- **Roles:** backend identifiers (`administrator|coordinator|operator|researcher|observer`;
  mission roles without administrator) are mirrored and unit-tested. An observer's UI is
  read-only, and the backend returns 403 to the observer's pause request. Cross-mission direct
  URLs return 404. Administrators cannot decide without membership (unit).
- **Defect found and fixed:** after creating a mission the creator's new coordinator
  membership wasn't reflected, so Start stayed disabled. Fixed by refreshing `/auth/me` on
  mission entry and after creation, found by the connected e2e suite.
- **Limitation:** there's no in-dashboard user or membership administration. Memberships are
  managed through the API (`POST /missions/{id}/members`) or CLI.

## 9. WebSocket integration results

- **Verified connected:** the auth frame (token never in the URL), welcome/subscribe with
  cursor, live events, and a real socket drop (Playwright `routeWebSocket`) followed by
  automatic reconnection that resumed from the last applied sequence.
- **Verified in unit tests:** dedup, out-of-order hold, gap → resync, `resync_required`,
  4401 refresh, 4403 stop, polling fallback after three failures, cleanup, backoff bounds.
- Chromium offline emulation doesn't drop an open localhost WebSocket. The first test design
  relied on it and was replaced.

## 10. Simulation integration results

Connected e2e ran a six-agent `flood_basic` mission (seed 42, horizon 400, fusion) created and
started from the UI: real reported positions on the map (cell coordinates with ±0.5
uncertainty), observations, the event timeline, pause, resume, stop, and persisted retrieval
after reload. A second mission (`flood_outage`) showed recorded communication degradation and
recovery. Mission switching changes the scope of the header, timeline and stream.

## 11. Model 1 monitoring results

- Fleet and agent views show the agents' own reports: availability, reported state, link,
  last report, position and uncertainty, battery when reported, degraded sensors, tasks, and
  status and position history.
- Condition is classified as nominal, degraded, stale, unavailable or unknown. A missing
  heartbeat is never shown as "failed" (unit-tested).
- Private agent memory isn't exposed by the backend and isn't requested.

## 12. Model 2 monitoring results

- The Model 2 page shows availability, counters, evidence groups with per-agent report counts,
  assessments and activity. Connected e2e confirms "N Model 1 report(s) from K independent
  agent(s)".
- **Limitation:** Model 2 unavailability can't be demonstrated with the real backend. The
  runtime's `model2_state` only goes from active to ended in the current integration, so
  `MODEL_2_UNAVAILABLE` is never emitted. Dashboard handling is verified with the synthetic
  preset and in component/e2e mock tests only.

## 13. Human oversight results

- **Verified connected:** pause → review queue → approve with reason and confirmation → UI
  shows "submitted", not approved → resume → the persisted decision becomes accepted or
  rejected by Model 2's validator → still visible after a reload.
- **Verified connected via API:** a stale version returns 409 `stale_version`.
- **Verified synthetic (UI):** the stale-version dialog blocks submission and offers to load
  the updated version, and an idempotent resubmission returns the same decision.
- **Finding:** Model 2's review window is about 1 s of simulated time. The UI tells reviewers
  to pause; this is now documented.

## 14. Persistent data verification

Decisions, recommendations, incidents and observations were retrieved again after a browser
reload, and after the mission was stopped and the page reloaded (connected e2e). The database is
SQLite at `runs/backend/phase8_dev.db`, migrated to head `0001`. PostgreSQL/PostGIS: **not
verified** (no server available; the PostGIS test remains skipped).

## 15. Research analytics results

- **Connected (researcher):**
  - Measured time series from `METRICS_UPDATED` events.
  - Run metrics and human review latency statistics.
  - Research JSON export with evaluator ground truth, and operational CSV (formula-neutralised).
  - Experiment comparison over stored Phase 5/6 results: n, mean, median, SD, 95% CI and
    missing counts per group.
- Synthetic metrics are labelled as not research results.
- No measurements were fabricated; missing values show as missing.

## 16. Synthetic demonstration results

- All 10 presets run deterministically. Unit tests cover determinism, contract conformance,
  hidden-truth isolation, degradation and recovery, the Model 2 outage, decision validation,
  stale version, permission enforcement, failure and empty presets, export labelling, and the
  absence of any network calls.
- The mock e2e suite asserts that no `/api` or `/ws` request is made during the demo.

## 17. Unit and component test totals

`npm run test`: **77 passed** (5 files): 60 unit (lib, contracts, transport, synthetic)
and 17 component/integration.

## 18. End-to-end test totals

`npx playwright test` (system Chrome): **20 passed, 1 skipped**:
- **mock:** 12 passed (synthetic flows, map/agent/observation/incident/evidence navigation,
  review with stale version, observer restriction, degradation and Model 2 outage
  scenarios, analytics/export labelling, backend-failure state, 4 responsive sizes, axe in
  light and dark themes).
- **connected:** 8 passed against the real backend (sections 8–15).
- **Skipped:** the performance spec, which is gated by `E2E_PERF=1`; it was run separately
  and passed.

Mock tests are not counted as integration verification.

## 19. Backend regression results

After all backend changes:
- pytest **176 passed, 1 skipped** (PostgreSQL-only test; 3 new tests)
- `ruff check .`: all checks passed; `ruff format --check`: clean
- `mypy` (strict): no issues in 113 source files
- `pip check`: no broken requirements
- `alembic current`: `0001 (head)`

## 20. Lint and TypeScript results

- `npm run lint` (ESLint, zero warnings allowed): pass
- `npm run typecheck` (strict, plus `noUncheckedIndexedAccess`, for app, tests and configs):
  pass
- `npm run format:check`: pass

## 21. Production build results

`npm run build`: pass (`tsc -b` + Vite). There's one lazy chunk per route. The two largest
shared chunks are about 396 kB (React, Router, Query, Zod; 119 kB gzip) and about 400 kB
(Recharts; 110 kB gzip).

## 22. Accessibility findings

- **Implemented:** see [QUALITY_AND_OPERATIONS.md](frontend/QUALITY_AND_OPERATIONS.md).
- **Automated:** axe reported no serious or critical violations on the scanned pages in both
  themes.
- **Defects found and fixed:**
  - 5 light-theme contrast failures (3.85–4.38:1); the light tokens were darkened.
  - Panels were unnamed regions; every panel is now labelled by its heading.
  - Long mission names overflowed the top bar; they're now truncated with an ellipsis.
- **Not verified:** manual screen-reader testing, a full keyboard-only walkthrough, 400% zoom.
  WCAG compliance is **not claimed**.

## 23. Security findings

- **Implemented:**
  - No HTML injection (lint-enforced) and runtime response validation.
  - Token only in the first WebSocket frame.
  - Access token in memory only; no credentials or records in localStorage.
  - Evidence content only via authorized object IDs.
  - Same-origin proxy and CSP on preview; CSV formula neutralisation on download.
  - A safe post-sign-in redirect that rejects `//host`, backslash, scheme and control
    characters (unit-tested). It mitigates the React Router v6 open-redirect advisories for
    the one URL-derived navigation target.
- **Dependency audit (runtime):**
  - `react-router-dom` upgraded 6.28.0 → **6.30.6**.
  - Remaining `react-router` advisories are fixed only in v7. The SSR and loader ones don't
    apply to this client-only app; the open-redirect class is mitigated as above.
  - `zod` 3.23.8 has GHSA-mrhx-c7xc-m3w5 (memory exhaustion on oversized collections), fixed
    only in Zod 4. Accepted residual risk, because only paginated backend responses are
    validated.
  - Both are Phase 9 upgrade items. The other audit findings are in development tooling.
- **Other residual items:**
  - The refresh token in tab `sessionStorage` is readable by injected script.
  - Backend CSV exports aren't neutralised server-side (the dashboard re-encodes them).
  - The dev server runs without CSP.
- This is not a production certification.

## 24. Performance observations

Local measurements for 3/6/10/20 agents are in
[QUALITY_AND_OPERATIONS.md](frontend/QUALITY_AND_OPERATIONS.md#performance):
- 0 long tasks recorded.
- JS heap 32–77 MB.
- API p50 78–136 ms.
- Map navigation 87–292 ms.
- The live stream stayed open in all runs.

Two observations: backend simulation throughput falls as agent count rises, and the overview
generates about 8–9 requests per second. These are not scalability claims.

## 25. Bugs corrected

1. Alembic migrated a different database from the server when the URL was only in `.env`
   (backend, with test).
2. `EventBuffer` reversed the released events in place, delivering out-of-order events in the
   wrong order (unit test).
3. A new mission's creator saw lifecycle controls disabled until signing in again (connected
   e2e).
4. Light-theme contrast failures (axe).
5. Unnamed panel regions (accessibility).
6. Top-bar mission-name overflow (visual).
7. The open-redirect exposure in the post-sign-in redirect (security).
8. A communication-pulse cleanup bug (timers cancelled by effect reruns).
9. An unstable random React key in the conflicts table.
10. Zustand selectors returning new arrays (render loop risk).

## 26. Remaining limitations

- **Model 2 unavailability** can't be produced by the real backend; it's demonstrated
  synthetically only.
- **PostgreSQL/PostGIS** is not verified.
- **Evidence media:** the simulator doesn't upload evidence objects, so connected evidence is
  reference-only. The authorized image path (blob, PNG/JPEG only, zoom) is implemented but not
  exercised end to end with a stored object.
- **Review window** of about 1 s simulated time; reviewers must pause.
- **No user or membership admin UI.**
- **The simulated override** is implemented but not exercised end to end.
- **Admin system-health details** are not covered by e2e.
- **Overview request volume** is high.
- **Dependency advisories:** zod (v4 needed) and react-router (v7 needed).
- **Synthetic demo** state is lost on reload, by design.
- **Hazard severity** isn't reported by the backend and is shown as "not reported".
- **Peer link state** is unknown.
- **Manual accessibility audits** are pending.

## 27. Verified startup commands

Verified in this session:

```powershell
cd D:\SWARM-AID
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
cd D:\SWARM-AID\frontend
npm ci        # this session used npm install to create the lock file
npm run dev
```

`scripts\start_dashboard.ps1` was syntax-checked with the PowerShell parser but not executed:
starting new windows was outside what could be verified non-interactively.

## 28. Dashboard URL

- Development: http://127.0.0.1:5173
- Preview build: http://127.0.0.1:4173
- Backend: http://127.0.0.1:8000
- API docs: http://127.0.0.1:8000/docs

## 29. Phase 9 readiness checklist

| Area | Status | Phase 9 action |
|---|---|---|
| Simulator | Ready | Expose a scenario that exercises Model 2 unavailability; throughput drops with agent count |
| Model 1 | Ready | Report evidence objects so evidence media can be shown; optional battery/peer-link reporting |
| Model 2 | Ready with limitation | Add a real unavailable/degraded state transition to the runtime; consider a longer, configurable review window or pause-on-review |
| Communication | Ready | Expose per-link peer state if link health is needed in the UI |
| Coordination | Ready | — |
| Backend | Ready with limitations | Neutralise formulas in CSV exports; consolidated overview read model; membership admin endpoints exist (UI pending) |
| Database | SQLite verified; PostgreSQL/PostGIS unverified | Run the skipped PostGIS test against a real server |
| Dashboard | Ready with limitations | Upgrade Zod 4 and React Router 7; membership admin UI; manual accessibility audit; reduce overview polling |
| Research evaluation | Ready | Experiment catalog accepts new families when runners write `comparison.csv` |
| Failure recovery | Verified for stream drop, session expiry, backend unreachable, stale versions | Exercise database outage and Model 2 recovery against the real system |
| System orchestration | Not started (Phase 9 scope) | Single command to run backend, simulation and dashboard; service supervision |

**Classification: READY WITH LIMITATIONS.** Mandatory connected functionality is verified end
to end against the real backend except for two items: Model 2 unavailability, which the
backend can't produce, and stored-evidence media rendering, which the simulator doesn't
provide. Both are documented above and are not substituted with synthetic results.

## Git status

Nothing has been staged or committed, and no tag was created, pending the independent Phase 8
audit. `git diff --check` is clean. `node_modules/`, `dist/`, `.env`, `runs/` (databases,
credentials, reports) and Playwright outputs are git-ignored. `frontend/package-lock.json` must
be committed. The Phase 7 backend files were already uncommitted at the start of the session
and should be reviewed and committed together with Phase 8, or before it.
