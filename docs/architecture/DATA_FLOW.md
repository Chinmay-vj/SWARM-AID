# Data flow and lineage

```mermaid
flowchart TD
    Truth[Private world state] --> Filter[Visibility and seeded noise]
    Filter --> Sample[Per-drone samples]
    Sample --> Report[Observation and evidence keys]
    Report --> Local[Private local memory]
    Report --> Inbox[Peer and command inboxes]
    Inbox --> Link[Deduplicated report associations]
    Link --> Revision[Incident revision] --> Proposal[Validated recommendation]
    Proposal --> Human[Human decision]
    Human --> Ledger[Decision and audit ledger]
    Truth --> Score[Offline scoring]
    Ledger --> Score
    Link --> Score
```

At capture the sensor assigns evidence IDs, origin and capture tick. The observation adds a reportable location if available. Retries preserve IDs. Independent observations get new evidence IDs even when associated with the same incident. A recommendation refers to a specific immutable revision; a reviewer must refresh after a conflicting update.

The evaluator joins truth to observations after the run. Agent-facing APIs expose only observed coverage and permitted evidence. Operational logs carry correlation IDs, message metadata and rejection codes. Raw artifacts remain in a separate access-controlled store. Experiment exports use synthetic identifiers and omit artifact contents by default.
