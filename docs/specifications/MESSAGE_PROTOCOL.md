# Message protocol v1.0

Wire JSON is produced by Envelope.model_dump_json(). Decode with Envelope.model_validate_json(). All envelopes require schema_version, message_id, source, destination, mission_id, session_id, timestamp, sent_ms, sequence, priority, correlation_id and payload. The timestamp is timezone-aware for audit. sent_ms is mission-relative; expiry is exclusive. Sequence starts at zero per mission, sender session and destination. Priority is routine, urgent or control. Correlation groups related envelopes. Identity and correlation UUIDs serve different purposes.

| payload.message_type | Required payload content | Authorized path in runtime |
|---|---|---|
| registration | role, session_id | Participant to broker, verified against registry |
| heartbeat | state | Drone to command |
| environmental_observation | observation, feature | Drone to nearby peers and command |
| possible_human_detection | observation | Drone to nearby peers and command |
| hazard_detection | observation, hazard | Drone to nearby peers and command |
| incident_update | incident, optional recommendation | Command to reviewer |
| evidence_reference | evidence | Evidence owner to authorized recipient |
| mission_instruction | task_id, action | Command to assigned drone |
| task_status | task_id, status | Assigned drone to command |
| agent_health | battery_fraction, degraded_sensors, optional cell | Drone to command |
| acknowledgement | acknowledged_id, outcome | Receiver to originating sender |
| connection_loss | peer, last_seen_ms | Link monitor to local supervisor |
| reconnection | peer, session_id, last_contiguous_sequence or null | Rejoining principal to broker |
| human_approval | recommendation_id, incident_id, revision, decision, reason | Authorized reviewer to command |
| human_override | action, reason | Authorized mission operator to command |
| error_report | code, retryable, optional related_id | Receiver to sender or local supervisor |

Observation payloads carry confidence and evidence. Expiry is mandatory for instructions, decisions and overrides. Reject unknown versions or keys. Introduce a new schema version with a dedicated decoder and migration tests before changing required fields. Generate the machine-readable schema using Envelope.model_json_schema().

Receiver processing order is principal binding, schema and scope validation, lookup of the authenticated recipient's committed receipt and original byte digest, then expiry and revision or lease checks for unseen messages, transactional application and acknowledgement. Persist receipt and state mutation together. Repeated accepted IDs return the earlier outcome without reapplying. A reused ID with different bytes is a protocol error. Track gaps independently of highest seen sequence. Retry reliable unacknowledged messages with identical bytes, bounded backoff and the original expiry; drop superseded telemetry. Expired observations can be archived as historical with a stale flag outside the live decision path.

On reconnect exchange stream cursors and fetch current mission restrictions before accepting work. A lost session starts a new sequence namespace. If retained history cannot cover a gap, request a snapshot and record the unrecoverable interval. A priority flag never conveys permission.

Save the original encoded bytes for retries. For an exact retry by the same authorized sender, return the stored disposition even after expiry. A first delivery at or after expiry cannot execute. An acknowledgement records ingestion only; a lost acknowledgement cannot trigger a second task. Bind receipt lookup to mission, authenticated origin, message ID and receiving member. A sender's replay horizon must fit inside receipt retention; outside that window require reconciliation.

In v1.0 a reconnect cursor is meaningful only when the authenticated handshake identifies exactly one previous incoming stream (mission, original sender, original session and original destination). The reconnect payload session identifies the rejoining sender. If that mapping is unavailable, changed, or ambiguous across group streams, ignore the cursor and recover from a current snapshot. A new session cannot inherit an unverified lease. For lossy telemetry, report a terminal gap once replay is exhausted and advance the stream via a snapshot. Keep a bounded retry path for reliable control independent of telemetry gaps.

Bind HTTP overrides to the expected mission revision in the If-Match precondition. Persist that precondition with the envelope and verify it atomically on application. Reject a bare v1.0 override received without an authenticated revision binding. A drone applies restrictions through the synchronized command state; delayed resume never revives a revoked lease.

A drone detects command silence using acknowledgements to its periodic heartbeat on the command channel. Only authenticated current-session responses count as contact. Receipt of a peer report or replayed old acknowledgement cannot reset the offline timer. Command detects drone silence using the counterpart heartbeat deadline. Explicit command-state reconciliation still precedes lease renewal.

## Phase 4 extension

MissionUpdate requires schema version 1.1. Existing v1.0 payloads remain accepted. See the [communication protocol guide](../communication/MESSAGE_PROTOCOL_GUIDE.md) for channel mappings and simulated delivery semantics.
