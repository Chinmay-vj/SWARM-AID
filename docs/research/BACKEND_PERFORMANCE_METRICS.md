# Backend performance metrics (Phase 7)

These are measured local results, not design targets and not evidence of production scalability. Reproduce them with `.\.venv\Scripts\python.exe -m evaluation.backend_benchmark`, which writes `runs/backend/benchmark-<timestamp>/benchmark_results.json`. The values below come from run `benchmark-20261124T102605Z`.

## Method

- One uvicorn worker (no reload) as a separate process; SQLite file database in WAL mode; client and server on the same host.
- Host: Windows 11 (10.0.26200), Intel64 Family 6 Model 165, 12 logical CPUs, CPython 3.12.10.
- For each fleet size N in {3, 6, 10, 20}: one running `flood_basic` mission (stationary `independent` coordination, ticks every 250 ms), one agent credential per drone, and N x 40 synthetic reports submitted through `POST /missions/{id}/observations` by min(N, 16) concurrent client threads, each using a persistent HTTP client. Each report is consumed by the mission's Model 2 instance and persisted. Then 10% of reports were resubmitted, followed by 40 rounds of five REST reads. One WebSocket client recorded delivery latency (server `occurred_at` to client receipt).
- Separately: 20 logins, 50 concurrent authenticated WebSocket connections, 300 single-row database commits and primary-key reads, server peak memory (reported by the server process itself), and cold start and restart-to-ready time.

An earlier run created a new HTTP client per request. On Windows that adds about 200 ms of client-side setup, which inflated every latency, so it was discarded. Another earlier run used moving drones that exhausted their batteries mid-run (the engine ends the mission as `inactive`). That produced 409 errors, so it was also discarded.

## Results

All requests succeeded (error rate 0) in the reported run.

| Fleet | Reports | Ingest mean / median / p95 / p99 (ms) | Throughput (reports/s) | Duplicate median / p95 (ms) | WebSocket delivery median / p95 / p99 (ms) |
|---:|---:|---|---:|---|---|
| 3 | 120 | 211 / 186 / 665 / 849 | 13.7 | 2.7 / 4.1 | 53 / 124 / 492 |
| 6 | 240 | 424 / 412 / 854 / 1362 | 13.7 | 3.2 / 3.8 | 59 / 156 / 434 |
| 10 | 400 | 808 / 726 / 1641 / 2118 | 12.0 | 3.1 / 7.6 | 70 / 303 / 1893 |
| 20 | 800 | 1270 / 1100 / 2567 / 2893 | 12.3 | 3.1 / 7.8 | 61 / 967 / 2058 |

All duplicate resubmissions (12, 24, 40 and 80) were recognized as duplicates.

REST read latency during the 20-agent run, median / p95 / p99 (ms): summary 5.7 / 14.2 / 66.1; incidents 29.2 / 90.0 / 94.0; observations 6.0 / 44.7 / 53.5; review queue 63.5 / 508.7 / 600.3; map 30.6 / 301.4 / 340.6. The 3-agent run had medians of 5.2, 27.4, 5.8, 27.9 and 14.5 ms respectively.

| Other measurement | Result |
|---|---|
| Login (Argon2id verify plus token issue), n = 20 | mean 63.3, median 61.0, p95 80.7 ms |
| 50 concurrent authenticated WebSocket connections | 50 of 50 succeeded; median 16.7, p95 32.5, p99 41.3 ms |
| Single-row commit, n = 300 | median 0.38, p95 1.09, p99 40.3 ms (mean 3.7: occasional WAL checkpoint stalls) |
| Primary-key read, n = 300 | median 0.27, p95 0.35, p99 0.44 ms |
| Server cold start to ready | 2.11 s |
| Restart (after kill) to ready | 2.01 s |
| Server peak working set | 316.3 MB |

## Interpretation

- **Ingestion throughput is capped at about 12-14 reports per second regardless of fleet size.** Each report is handed to the mission's single Model 2 instance under the mission lock and persisted in its own SQLite transaction; ticks take the same lock. Latency therefore grows with concurrency (queueing), not with per-request work. This is a consequence of the design (one authoritative Model 2 per mission, single writer), not a defect, but it bounds an API-driven fleet. Batching reports or a per-mission ingestion queue are possible Phase 8+ improvements.
- Review-queue and map latency rise with mission size: the queue builds incident read models per item, and the map recomputes sector geometry on each request. Both would benefit from caching.
- WebSocket p95 and p99 delivery grow with event volume because dispatch runs after each commit on the shared event loop.
- Simulated in-process traffic (Model 1 to Model 2 over the router) does not use the HTTP path and is not limited by these figures.
- Not measured: PostgreSQL (not available), multi-process deployment, long-duration load, network latency between hosts.
