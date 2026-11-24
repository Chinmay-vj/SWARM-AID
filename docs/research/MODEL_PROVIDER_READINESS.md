# Model provider readiness for Phases 11–12 (Model 1, Model 2, artifacts)

Phase 9 audited whether future trained components can replace today's deterministic providers
without changing safety, validation, authorization or human oversight. No model was chosen,
downloaded or trained. Earlier design notes: `docs/agents/FUTURE_MODEL_INTEGRATION.md`,
`docs/command_agent/FUTURE_AI_INTEGRATION.md`.

## Model 1 (per-drone agent)

Ports (`interfaces/providers.py`), all injectable through `DroneAgent(...)`:

| Port | Input contract | Output contract | Current provider |
|---|---|---|---|
| `PerceptionProvider.perceive` | `SensorFrame` (`agent_id`, `tick_ms`, `samples: tuple[Evidence]`, `cell`, `battery_fraction`) | `tuple[Finding, ...]` | `MockPerception` (reads symbolic readings) |
| `SensorFusionProvider.fuse` | frame + findings | `LocalView` | `Fusion` |
| `ReasoningProvider.select_intent` | `LocalView` | `Intent` (survey, revisit, hold, end) | `Rules` |
| `PlanningProvider.plan` | view, intent, lease | `Action` | `Planner` (bounded) |
| `MemoryProvider` | findings | recent findings | `Memory` (bounded, private) |
| `SafetyPolicy.constrain` | proposed `Action`, `SafetyContext` | allowed `Action` | `safety.py` (**must stay independent of learned providers**) |

Modalities in the contract: `image`, `video`, `thermal`, `text`, `gps`, `imu`, `environment`,
`peer` (`Evidence.modality`). The simulator produces `image`, `thermal`, `gps`, `imu`,
`environment`, `text` symbolically.

Data types and shapes: there are **no tensor shapes** today. Evidence is referenced by an opaque
`artifact_key`; readings are symbolic strings with a confidence. Input dimensions for trained
perception must come from the Phase 10 datasets; Phase 9 deliberately defines none.

Validation already in place before any provider sees data: foreign or stale frames are refused,
evidence origin must equal the agent, confidences are 0–1, evidence IDs cannot be reused with
different content, observations cannot precede their evidence, and fusion output is checked for
scope and provenance ("fusion scope or provenance mismatch").

Missing modalities: a dropped modality simply contributes no evidence; findings never invent a
missing modality (verified with `command_missing_modalities`). A trained provider must accept an
arbitrary subset of modalities and report which were absent.

Failure behaviour (`DroneAgent.cycle`): any exception from an injected provider increments
`health.provider_errors`, marks the agent `failed`, moves it to HOLD, publishes a retryable
`error_report` to Model 2 and returns HOLD (or INACTIVE after an end override). Evidence
returned by a provider that was not in the agent's own inputs is refused ("unresolved provider
evidence"). Proposed actions always pass the independent safety controller.

### Gaps before Phase 11

1. **Provider selection:** `Settings.perception` etc. are `Literal["mock"]`/`"rules"` and `Fleet`
   always constructs the defaults. Needed: a provider factory keyed by configuration
   (identifier, version, artifact), with the mock as explicit fallback.
2. **Artifact resolution:** a trained perception model needs pixel/audio data. Needed: an
   artifact resolver mapping `artifact_key` to content for the agent's own evidence only, with
   size and type limits (the backend evidence store already enforces content hashing and media
   types).
3. **Uncertainty output:** `Finding` has no calibrated-uncertainty field beyond
   `Observation.confidence`; add one in a versioned contract change if needed.
4. **Provider version in reports:** the agent's decision log records a provider label
   (`"provider": "rules/1"`), but transmitted reports and persisted records do not. Add the
   provider identifier and version to run manifests (and, if needed, findings) before comparing
   models.

## Model 2 (command agent)

Ports, injectable through `CommandAgent(..., assessment=, review=, urgency=)`:

| Port | Input | Output | Current |
|---|---|---|---|
| `IncidentAssessmentProvider.assess` | previous `Incident` or none, `tuple[ReportedFinding]` | `Incident` (category, reports, uncertainties) | `Rules` (source threshold) |
| `UrgencyAssessmentProvider.assess_priority` | finding + context findings | `Priority` (level, reason, evidence IDs) | `ContextPriority` |
| `RescueRecommendationProvider.recommend` | incident + reports | `Recommendation` (request, evidence IDs, unknowns, expiry) | `Review` |

Guards that stay outside any learned provider (verified in code): report validation (scope,
session-bound sender, freshness, duplicates, conflicts, capacity), the check that an assessment
cites exactly the supplied reports with a consistent revision and never claims
`human_confirmed` (`"unsupported incident"` is refused), human-decision validation against the
exact revision and deadline, authorization in the backend, and persistence as copies only.

Evidence representation: `ReportedFinding(message_id, finding)` with full provenance (origin,
capture time, modality, artifact key). Contradictions are flagged as conflicts (and, since Phase
9, persisted as conflicting evidence). Missing information is carried as `uncertainties` and
`unknowns`.

Gaps before learned Model 2 components: the same provider factory and versioning as Model 1;
a record of which provider produced each revision; a calibrated probability field would be a
contract change (today Model 2 produces categories and priority levels, not probabilities).

## Artifact and provider versioning conventions (lightweight, proposed)

No registry service, MLflow or cloud dependency. Proposed for Phase 11:

| Field | Meaning |
|---|---|
| `provider_id` | stable name, e.g. `model1.perception.mock` |
| `provider_version` | semantic version of the provider code |
| `artifact_id` | SHA-256 of the weights file (none for rule-based providers) |
| `input_schema_version` / `output_schema_version` | contract versions the provider accepts and emits |
| `config_version` | version of the provider's configuration file |
| `hardware` | `cpu` required; GPU optional and never mandatory |
| `evaluation` | pointer to the evaluation run (manifest digest) that qualified the artifact |
| `on_load_failure` | `refuse_start` (default for experiments) or `fallback_to_mock` (labelled in results) |

The Phase 9 run manifest (`orchestration/manifest.py`) is where these fields would be recorded
per run.
