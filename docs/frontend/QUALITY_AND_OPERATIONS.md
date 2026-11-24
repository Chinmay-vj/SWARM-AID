# Phase 8 dashboard: testing, accessibility, security, performance and startup

## Testing

| Layer | Location | Tooling | What it covers |
|---|---|---|---|
| Unit | `frontend/tests/unit/` | Vitest | formatting, freshness, status mapping, permission matrix, statistics, CSV safety, event buffer (dedup/out-of-order/gap/bounded), grid transforms, idempotency keys, sorting, contract validation against captured backend shapes, event vocabulary, recommendation diffs, API client (bearer, request ID, schema errors, structured errors, single-flight refresh, session expiry, safe retries, timeout, cancellation), WebSocket stream (auth frame, URL without token, dedup, reconnect cursor, resync, 4403 stop, polling fallback, cleanup, backoff), synthetic engine (determinism, contracts, hidden truth, degradation, Model 2 outage, decisions, stale version, permissions, failure/empty presets, no network, export labels) |
| Component / integration | `frontend/tests/integration/` | Vitest + Testing Library (jsdom) | protected routes, sign-in errors and password non-persistence, synthetic labelling, navigation, confirmed lifecycle control, decision flow ("submitted" before validation), stale-version UI, observer restrictions, backend-failure/empty/not-found states, map accessibility alternative and no movement controls, connected failure without synthetic substitution, cross-mission 404, coordinator create action, admin-only health, cache/timeline clearing on mode switch |
| E2E (mock) | `frontend/tests/e2e/mock/` | Playwright + system Chrome + axe-core | synthetic demo only; asserts that no `/api` or `/ws` requests are made |
| E2E (connected) | `frontend/tests/e2e/connected/` | Playwright against the real backend | real auth, mission creation/start, positions, observations, Model 2 output, pause + review + decision + validation + persistence, stale 409, reload session recovery, observer 403/read-only UI, cross-mission 404, WebSocket drop/reconnect/resume, researcher analytics and exports, experiments, communication degradation, mission switching, stop and persisted retrieval |
| Performance | `frontend/tests/e2e/connected/performance.spec.ts` | Playwright (`E2E_PERF=1`) | 3/6/10/20-agent observations → `runs/frontend/phase8-performance.json` |

Commands (from `frontend/`):

```powershell
npm run typecheck; npm run lint; npm run test; npm run build
npm run test:e2e                                   # mock project
$env:E2E_PASSWORD = "<dev account password>"; npm run test:e2e:connected
$env:E2E_PERF = "1"; npx playwright test --project=connected -g "agents"
```

The connected tests need the backend running and the five development accounts (`admin`,
`coordinator`, `operator`, `researcher`, `observer`) sharing one password. Without
`E2E_PASSWORD` they are reported as skipped, not passed. Running the suite twice within a
minute can hit the backend's login rate limit (10 per minute); wait a minute.

## Accessibility (target: WCAG 2.2 AA practices)

Implemented:

- Semantic landmarks, a skip link and named regions (every panel is labelled by its heading).
- Visible 3 px focus ring, logical tab order, keyboard row selection and arrow-key tabs.
- Native `<dialog>` modals with focus trap, Escape and focus return.
- `aria-live` timelines (paused live updates switch it off), polite toasts, status and alert
  roles, and form fields with labels, help text and error descriptions.
- Map: keyboard pan, zoom and fit; focusable entities with descriptive labels; an entity table
  as the non-visual alternative.
- Charts: `<figcaption>` text summaries; exact values in tables.
- Status uses colour, glyph and text together.
- Reduced motion: a preference plus `prefers-reduced-motion` disables pulses, transitions and
  interpolation. A larger-text option and density setting are available.
- Responsive layout for 1366×768, 1440×900, 1920×1080, tablet and mobile (off-canvas nav).

Verified automatically: axe-core (tags wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa) reports no
serious or critical violations on overview, review, fleet and settings (light theme) or on
overview, review, incidents and communication (dark theme). The first run found 5 light-theme
contrast failures (accent and status colours on tinted backgrounds, 3.85–4.38:1); the light
tokens were darkened. No horizontal page scroll at 1366, 1920, 820 and 390 px widths.

Not verified: manual screen-reader testing (NVDA/JAWS/VoiceOver), full keyboard-only
walkthrough of every view, zoom to 400%, and moderate/minor axe findings. Compliance is **not
claimed**.

## Security

- No HTML injection (lint rule against `dangerouslySetInnerHTML`; all text is React text).
- Every response is validated at runtime; malformed WebSocket frames are dropped.
- The token is sent in the first WebSocket frame, never in the URL.
- Credentials: the password lives only in component state during sign-in. The access token is
  memory-only; the refresh token is tab-scoped (see API_INTEGRATION.md). No credentials,
  tokens or mission records are kept in localStorage; preferences only.
- No hard-coded credentials. Development passwords are generated locally into the git-ignored
  `runs/backend/dev-credentials.env`. `VITE_*` variables hold no secrets.
- Evidence media loads only by backend object ID through the authorized content endpoint, as a
  blob, and only for PNG/JPEG. Artifact keys are opaque text. No remote URLs are fetched.
- Error messages show the backend's structured code and message and the request ID, never raw
  bodies or stacks.
- Same-origin proxy (backend CORS stays empty). The preview server sends CSP
  (`default-src 'self'`, no inline scripts), `nosniff` and `no-referrer`. The dev server omits
  CSP because React Fast Refresh needs an inline preamble.
- CSV downloads are formula-neutralised client-side (backend CSV is not neutralised; noted for
  Phase 9).
- The backend's CSRF exposure is low because authentication uses bearer headers, not cookies.
- This is not a production security certification.

## Performance

Implemented: route-level lazy loading (one chunk per page), bounded event, notification and
sample histories, batched stream invalidation (400 ms), scope-limited cache invalidation,
pagination, memoized derived data, Recharts animations off, and cleanup of timers,
subscriptions, object URLs and observers.

Observed on an Intel i7-10750H (12 threads), 17 GB RAM, Windows 11, Chrome, with the SQLite
backend on the same machine (tick delay 100 ms). Each row is 15 s wall-clock with the overview
open, then a map navigation:

| Agents | Sim time reached | Events | Observations | API requests | API p50 / p95 (ms) | JS heap (MB) | Long tasks | Map navigation (ms) |
|---|---|---|---|---|---|---|---|---|
| 3 | 5.7 s | 504 | 168 | 141 | 81 / 413 | 44.2 | 0 | 191 |
| 6 | 4.3 s | 718 | 258 | 137 | 78 / 486 | 38.5 | 0 | 292 |
| 10 | 3.1 s | 814 | 281 | 129 | 86 / 972 | 77.4 | 0 | 87 |
| 20 | 2.1 s | 1092 | 388 | 113 | 136 / 644 | 32.4 | 0 | 107 |

Observations, not scalability claims:

- The backend's simulation throughput falls as agent count rises (fewer ticks per wall-clock
  second).
- The overview issues roughly 8–9 API requests per second while open, because many panels
  poll and stream events invalidate. Consolidating overview reads is a Phase 9 optimisation.
- JS heap stayed under 80 MB; the variation is garbage-collection timing.
- No list virtualization was added; all lists are paginated or bounded.

## Startup (Windows PowerShell)

```powershell
cd D:\SWARM-AID
Copy-Item .env.example .env        # set SWARM_JWT_SECRET (>= 32 chars); never commit .env
.\.venv\Scripts\python.exe -m alembic upgrade head
$env:SWARM_NEW_USER_PASSWORD = "<choose>"; .\.venv\Scripts\python.exe -m backend.cli create-user --username coordinator --role coordinator
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

cd D:\SWARM-AID\frontend
npm ci
npm run dev                        # http://127.0.0.1:5173
```

Or run `powershell -ExecutionPolicy Bypass -File scripts\start_dashboard.ps1`. It checks the
venv, `.env` and secret length (without printing it), runs migrations, skips services already
listening, binds to 127.0.0.1 and prints the URLs.
