# Integrated system architecture (Phase 9)

This describes the system as implemented and verified in Phase 9. Planned or unsupported
capabilities are marked as such. SWARM-AID is a civilian disaster search-and-rescue
**simulation** research framework: there is no physical drone control and no real-world rescue
execution anywhere in the code.

## 1. Integrated system

One running mission is one `SimulationContext` (`backend/integrations/simulation_adapter.py`).
The backend and the headless profile build exactly the same context, so a headless run and a
connected mission execute the same integrated stack.

```mermaid
flowchart LR
  subgraph SIM["Simulation context (one per mission)"]
    ENG["Engine<br/>simulation/core/engine.py<br/>world, ground truth, mission clock"]
    SEN["Mock sensors<br/>simulation/sensors/mock.py"]
    M1["Model 1 agents x N<br/>agents/drone_agent<br/>private memory, safety"]
    NET["Simulated transport<br/>communication/network.py<br/>routing, loss, delay, outages"]
    CO["Coordination baseline<br/>simulation/adapters/coordination.py"]
    M2["Model 2 command agent<br/>agents/command_agent<br/>fusion, incidents, recommendations"]
    ENG --> SEN --> M1
    M1 <--> NET
    CO <--> NET
    NET <--> M2
  end
  subgraph BE["Backend (FastAPI, one process)"]
    RT["RuntimeManager<br/>integrations/runtime.py"]
    AD["Model2Sync adapter<br/>integrations/model2_adapter.py"]
    DB[("SQLite / PostgreSQL<br/>Alembic 0001")]
    HUB["WebSocket hub<br/>realtime/hub.py"]
    API["REST /api/v1"]
  end
  RT -->|step per tick| SIM
  AD -->|copy outputs, one transaction per tick| DB
  DB -->|outbox events| HUB
  API --> DB
  API -->|human decisions| RT
  RT -->|operator channel| NET
  DASH["Dashboard (React)<br/>frontend/"] -->|bearer REST| API
  HUB -->|events| DASH
  EVAL["Evaluator<br/>evaluation/results.py"] -.->|ground truth, research export only| ENG
  ORCH["orchestration/<br/>check, run, matrix, serve, status"] --> RT
  ORCH --> SIM
```

Responsibilities (unchanged from Phases 2 to 8):

| Component | Owns | Does not own |
|---|---|---|
| Engine | world state, ground truth, mission clock, movement resolution | any reasoning |
| Model 1 (`DroneAgent`) | local perception, private memory, local world model, intent, planning, independent safety check | other agents' memory, ground truth |
| Transport (`Router`, `SimulationNetwork`) | delivery, loss, delay, duplicates, partitions, endpoint availability, receipts | message meaning |
| Coordination (`AssignmentFixture` + `Baseline`) | survey tasks, task history, availability | agent actions (agents validate leases) |
| Model 2 (`CommandAgent`) | report validation, evidence fusion, incidents, urgency, recommendations, decision validation | persistence, authorization |
| Backend | authentication, authorization, persistence, event outbox, orchestration of mission lifecycle | assessment or recommendation logic |
| Dashboard | display of authorized information, human review input | any reasoning; synthetic data in connected views |
| Evaluator | ground-truth metrics for research export | operational decisions |
| `orchestration/` (Phase 9) | configuration checks, execution profiles, run manifests, owned backend process | a second lifecycle manager: missions still run through `RuntimeManager` |

## 2. Component dependencies

```mermaid
flowchart TD
  interfaces["interfaces/providers.py"] --> agents
  agents["agents/ (Model 1, Model 2, shared domain)"] --> communication["communication/ (messages, router)"]
  simulation["simulation/ (engine, sensors, adapters)"] --> agents
  simulation --> communication
  evaluation["evaluation/"] --> simulation
  backend["backend/"] --> simulation
  backend --> agents
  backend --> evaluation
  orchestration["orchestration/"] --> backend
  orchestration --> evaluation
  frontend["frontend/ (TypeScript)"] -. HTTP/WebSocket .-> backend
```

There are no import cycles: `orchestration.manifest` is imported lazily by
`backend.integrations.runtime.git_commit`, and `orchestration` imports only
`backend.integrations.simulation_adapter` (no web framework) for headless runs.

## 3. Startup sequence (`scripts/start_system.ps1`)

```mermaid
sequenceDiagram
  participant U as Operator (PowerShell)
  participant S as start_system.ps1
  participant C as python -m orchestration check
  participant A as alembic
  participant B as python -m orchestration serve
  participant V as Vite (node)
  U->>S: start
  S->>S: Python 3.11/3.12 in .venv, Node 20+, node_modules
  S->>C: validate configuration (37 checks)
  C-->>S: ok / errors (no secret values printed)
  S->>S: port 8000 owned? foreign? free?
  S->>A: upgrade head
  S->>B: Start-Process (hidden, no inherited handles)
  B->>B: load settings, write runs/system/backend.state.json
  S->>B: poll /health/ready until 200
  S->>S: record PID + start time (backend.process.json)
  S->>V: cmd /c node vite.js --host 127.0.0.1 --port 5173 --strictPort
  S->>V: poll http://127.0.0.1:5173 until 200
  S-->>U: URLs, PIDs, status/stop commands
```

## 4. Mission lifecycle

Authoritative states live in `missions.status` and are changed only by
`backend.integrations.runtime.transition_mission`, which writes `mission_status_history` and an
outbox event in the same transaction.

```mermaid
stateDiagram-v2
  [*] --> draft: POST /missions (validated MissionConfig)
  draft --> running: start (only from draft; duplicate start -> 409 duplicate_execution)
  running --> paused: pause
  paused --> running: resume
  running --> completed: horizon reached or no active drones
  running --> stopped: stop / backend shutdown
  paused --> stopped: stop / backend shutdown
  running --> failed: simulation error or 20 consecutive persistence failures
  paused --> failed
  completed --> [*]
  stopped --> [*]
  failed --> [*]
```

A mission left `running` or `paused` by a process that died without graceful shutdown is marked
`stopped` ("backend restarted; in-memory simulation state was not durable") at the next
startup. Simulations cannot resume: simulator state is not durable (see FAILURE_RECOVERY.md).

## 5. Model 1 information flow

```mermaid
flowchart LR
  E["Engine.capture()"] -->|"Packet (frame + readings)<br/>own position, battery, own sensors"| IN["Inputs.ingest<br/>rejects foreign or stale frames"]
  IN --> P["PerceptionProvider<br/>(mock)"] --> F["SensorFusionProvider<br/>(mock)"]
  F --> MEM["Private Memory + World<br/>(bounded)"]
  MEM --> R["ReasoningProvider<br/>(rules)"] --> PL["PlanningProvider<br/>(bounded)"]
  PL --> SAFE["Safety controller<br/>independent check"] -->|allowed Move| E
  F -->|"validated report<br/>(observation id, evidence refs)"| MAIL["Mailbox"] --> NET["Router"]
```

## 6. Model 1 and Model 2 interaction

```mermaid
sequenceDiagram
  participant D as Model 1 (d0..dN)
  participant N as Router
  participant C as Model 2
  participant B as Backend adapter
  participant H as Human (dashboard)
  D->>N: environmental / hazard / possible-human report
  N->>C: delivered (sender bound to session)
  C->>C: validate scope, freshness, duplicates, conflicts
  C->>C: fuse by (kind, label, cell), assess, urgency
  C-->>N: incident_update + recommendation (to operator)
  N-->>B: persisted each tick (observations, incidents, recommendations)
  B-->>H: REST + WebSocket events
  H->>B: approve / reject (exact version, idempotency key)
  B->>N: human_approval via operator channel (202 submitted)
  N->>C: decision
  C->>C: validate revision and deadline
  C-->>B: accepted / rejected / expired
  B-->>H: HUMAN_DECISION_RESOLVED
  C-->>N: mission_instruction (coordination) to Model 1
  D->>D: lease accepted only after independent safety check
```

## 7. Communication flow

Peer-to-peer traffic between drones goes through the same simulated router as drone-to-command
traffic; it never passes through the dashboard or database. Under `shared_information`, drones
exchange reports and health; under `fixed_sector` and `independent`, peer sharing is off.

```mermaid
flowchart LR
  d0((d0)) <-->|peer reports, health| d1((d1))
  d0 -->|reports, heartbeat, task status| cmd[command endpoint / Model 2]
  d1 --> cmd
  cmd -->|instructions, acknowledgements| d0
  cmd -->|incident updates, alerts| op[operator endpoint]
  op -->|human approval / override| cmd
  cfg["Scenario network conditions:<br/>loss, delay, jitter, duplicate,<br/>reorder, partition, server_down,<br/>endpoint_down, outage_steps"] -.-> cmd
```

## 8. Evidence provenance

```mermaid
flowchart LR
  S["Sensor sample<br/>Evidence(origin=agent, captured_ms, modality, artifact_key)"] --> O["Observation<br/>(observation_id, cell, observed_ms, confidence)"]
  O --> M["Envelope<br/>(message_id, source, session, sent_ms)"]
  M --> F["Model 2 finding<br/>(message_id -> finding)"]
  F --> I["Incident revision<br/>(report_message_ids)"]
  I --> R["Recommendation version<br/>(evidence_ids)"]
  R --> D["Human decision<br/>(recommendation_id, expected_revision)"]
  O -.persisted.-> OBS[(observations + evidence)]
  I -.persisted.-> INC[(incidents, incident_evidence role)]
  D -.persisted.-> HD[(human_decisions)]
  OBS --> T["GET /observations/{id}/trace"]
  INC --> T
  HD --> T
```

Evidence `origin` is checked in tests to equal the reporting agent at every stage
(`tests/integration/test_system_integration.py`). The trace endpoint returns persisted records
only: no private agent memory, no Model 2 internals, no ground truth.

## 9. Human review workflow

Recommendation versions (`recommendations.status`):

```mermaid
stateDiagram-v2
  [*] --> pending: RECOMMENDATION_CREATED
  pending --> approved: human approval accepted by Model 2
  pending --> confirmed: human confirmation accepted
  pending --> rejected: human rejection accepted
  pending --> revision_requested: operator correction accepted by Model 2
  pending --> superseded: new evidence -> new version
  pending --> expired: review deadline passed
```

Human decisions (`human_decisions.status`), which are separate records:

```mermaid
stateDiagram-v2
  [*] --> submitted: approve/reject with exact version (HTTP 202)
  submitted --> accepted: Model 2 validates revision and deadline
  submitted --> rejected: Model 2 refuses (outdated revision, expired)
  submitted --> undeliverable: mission ended before processing
  [*] --> recorded: alert acknowledgement (no Model 2 validation needed)
```

Approval is decision support. It is never treated as a successful rescue outcome.

Stale versions are refused before submission (409 `stale_version`); repeated submissions with
the same idempotency key return the same decision.

## 10. Backend persistence

Each tick: `RuntimeManager._tick` steps the context and `Model2Sync.sync` copies new outputs in
one transaction (observations, evidence, incidents, revisions, evidence links, recommendations,
transitions, alerts, tasks, agent reports, runtime state, outbox events). If the transaction
fails, adapter cursors are restored and the next tick persists the same data again; after 20
consecutive failures the mission is marked `failed`. Every `snapshot_every_ticks` ticks a
Model 2 checkpoint, its read model and the coordination snapshot are stored with SHA-256
digests.

## 11. WebSocket synchronization

```mermaid
sequenceDiagram
  participant C as Client
  participant H as Hub
  participant DB as Outbox
  C->>H: connect /ws/v1/missions/{id}
  C->>H: {"type":"auth","token":...} (never in the URL)
  H-->>C: welcome(last_sequence)
  C->>H: subscribe(after_sequence = last seen)
  H->>DB: replay events > after_sequence (up to 1000)
  H-->>C: event frames, strictly increasing sequence
  Note over H,C: heartbeat every N s; bounded queue per client
  H-->>C: resync_required + close 4008 if the client falls behind
  C->>DB: REST /events?after_sequence=n to resynchronise
```

Delivery is at-least-once with client-side de-duplication by `sequence`; exactly-once is not
claimed. Phase 9 verified disconnect and replay against the running system: 219 events seen,
reconnect with `after_sequence=220`, replay started at 221 with no gaps
(`runs/phase9/demo/demo-20261124T154241Z.json`).

## 12. Failure recovery

See FAILURE_RECOVERY.md for categories. Recovery levels actually supported:

| Level | Supported |
|---|---|
| Historical record recovery after backend restart | Yes (verified) |
| Mission metadata recovery | Yes (verified) |
| Model 2 memory restore from checkpoint (read model integrity) | Yes, on request (`POST /missions/{id}/model2/recovery`), verified |
| Agent (Model 1) state recovery | No: not persisted |
| Exact simulation continuation after interruption | No: missions are marked stopped |

## 13. Research evaluator isolation

```mermaid
flowchart LR
  subgraph OPS["Operational (agents, Model 2, operators)"]
    M1[Model 1] --> M2[Model 2] --> OPV[Operational API views]
  end
  subgraph TRUTH["Evaluator only"]
    ENG[Engine ground truth: people, hazards, coverage]
    EV[evaluation.results.metrics]
    RX[Research export<br/>researcher role, labelled]
  end
  ENG --> EV --> RX
  ENG -->|"own sensor packet only<br/>(noisy, dropout, misses)"| M1
  ENG -. never .-> M2
  ENG -. never .-> OPV
```

Verified by an object-graph test (no `Engine`, `Person`, `Hazard`, `Drone` or another agent's
memory is reachable from any Model 1 agent, and none is reachable from Model 2) and by a
key-level scan of every operational endpoint (SECURITY_AND_ISOLATION.md).

## 14. Future trained-provider integration (planned, not implemented)

```mermaid
flowchart LR
  cfg["Provider config<br/>(id, version, artifact id)<br/>PLANNED"] --> fac["Provider factory<br/>PLANNED"]
  fac -->|PerceptionProvider| M1[DroneAgent]
  fac -->|SensorFusionProvider| M1
  fac -->|IncidentAssessmentProvider<br/>UrgencyAssessmentProvider<br/>RescueRecommendationProvider| M2[CommandAgent]
  res["Artifact resolver<br/>artifact_key -> tensor<br/>PLANNED"] --> fac
  mock["Deterministic mock providers<br/>(current, kept as fallback)"] --> M1
  mock --> M2
  SAFE["Safety controller, Model 2 validation,<br/>authorization, human review<br/>stay independent of learned providers"]
```

The provider ports exist (`interfaces/providers.py`) and both agents accept injected providers;
the factory, configuration and artifact resolver do not exist yet. See
`docs/research/MODEL_PROVIDER_READINESS.md`.
