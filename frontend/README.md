# SWARM-AID rescue command dashboard (Phase 8)

React 18 + TypeScript (strict) + Vite single-page application for monitoring SWARM-AID
simulation missions and making human-oversight decisions. **Simulation research only: there is
no physical drone control.** Recommendations are decision support; human decisions are validated
by Model 2 and remain authoritative.

The dashboard has two isolated data sources:

| Mode | Source | Use |
|---|---|---|
| Connected simulation | Phase 7 FastAPI backend (REST + WebSocket) via the Vite proxy | Real missions, persisted records, live events |
| Synthetic demo | Deterministic in-browser playback (`src/services/providers/synthetic`) | Demonstrations without a backend; labelled SYNTHETIC everywhere, never sent to the backend |

The original presentation MVP (vanilla JS) is preserved unchanged in [`legacy-mvp/`](legacy-mvp/);
open `legacy-mvp/index.html` directly in a browser.

## Quick start (Windows PowerShell)

Prerequisites: Node.js 20+ (verified with 23.11) and, for connected mode, the backend from the
repository root (see the root README "Phase 7 backend" and [`scripts/start_dashboard.ps1`](../scripts/start_dashboard.ps1)).

```powershell
# Terminal 1 — backend (repository root)
cd D:\SWARM-AID
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

# Terminal 2 — dashboard
cd D:\SWARM-AID\frontend
npm ci
npm run dev
```

Open http://127.0.0.1:5173. API docs: http://127.0.0.1:8000/docs. Choose **Connected simulation**
and sign in with a backend account, or **Synthetic demo** (no backend needed).

Production build: `npm run build` then `npm run preview` (http://127.0.0.1:4173, same proxy, strict
CSP headers).

## Commands

| Command | Purpose |
|---|---|
| `npm run dev` | Dev server on 127.0.0.1:5173 with `/api`, `/health`, `/ws` proxied to the backend |
| `npm run typecheck` | Strict TypeScript for app, tests and configs |
| `npm run lint` | ESLint (no warnings allowed; forbids `dangerouslySetInnerHTML`, UI → synthetic imports) |
| `npm run test` | Vitest unit + component/integration tests (non-watch) |
| `npm run test:e2e` | Playwright **mock** project (synthetic mode, no backend) |
| `npm run test:e2e:connected` | Playwright **connected** project (needs backend + `E2E_PASSWORD`) |
| `npm run build` | Typecheck + production bundle in `dist/` |

Playwright uses the installed Google Chrome (`channel: "chrome"`); set `PW_CHANNEL=""` and run
`npx playwright install chromium` to use the bundled browser instead.

## Configuration

See [`.env.example`](.env.example). `VITE_*` values are compiled into the bundle and must never
contain secrets. `SWARM_BACKEND_URL` is read only by `vite.config.ts` for the proxy target.

## Structure

```text
src/
  app/            App, routes, providers, error boundary
  contracts/      zod schemas for every backend response; event vocabulary
  services/api/   HTTP client, errors, token storage, connected provider
  services/websocket/  mission event stream (auth frame, backoff, dedup, resync, polling)
  services/providers/  DataProvider interface, registry, synthetic engine/provider
  stores/         zustand: session, preferences (persisted, non-sensitive), activity, connection
  hooks/          query bindings (mode/mission scoped keys), stream, auth actions
  lib/            pure logic: formatting, freshness, status, permissions, stats, CSV, grid, buffer
  components/     ui primitives, layout shell, map, charts
  features/       one folder per dashboard area
  styles/         design tokens (dark/light) and component styles
tests/unit, tests/integration, tests/e2e/{mock,connected}
```

Documentation: [`docs/frontend/`](../docs/frontend/) and the
[Phase 8 completion report](../docs/PHASE_8_COMPLETION_REPORT.md).
