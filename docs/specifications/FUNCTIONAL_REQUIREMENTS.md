# Functional requirements

| ID | Required behavior | Acceptance observation | Stage |
|---|---|---|---|
| F01 | Parse versioned config for all five disaster families | Unknown keys, unsupported version or invalid budget reject startup | 1 |
| F02 | Represent each protocol message as a typed variant | Round-trip each variant and reject invalid controls | 1 |
| F03 | Replace perception or planning through a port | Alternate implementation needs no change in message types | 1 interface, 2 execution |
| F04 | Maintain per-drone sensor and memory scope | Hidden victim and peer-private state absent from agent input | 2 |
| F05 | Report possible presence, hazards and surroundings | Same observation reaches command and eligible peers independently | 2 |
| F06 | Enforce bounded disconnected operation and independent safety | Expired task yields hold even with an active planner | 2 |
| F07 | Associate independent reports and retain provenance | Relay of one capture adds no independent corroboration | Command integration |
| F08 | Classify incidents and expose uncertainty | All six categories represented; confirmation requires audited human decision | Command integration |
| F09 | Validate recommendations against available evidence | Missing evidence prevents publication; absent resource stays unknown | Command integration |
| F10 | Provide human mission control | Revision conflict prevents stale approval and preserves audit trail | Dashboard |
| F11 | Inspect location, health, coverage, evidence, hazards and messages | Operator sees observation age and can approve, reject or override | Dashboard |
| F12 | Reproduce and compare experiments | Replayed seed and manifest yield equal normalized trace; analytics show denominators | Evaluation |
