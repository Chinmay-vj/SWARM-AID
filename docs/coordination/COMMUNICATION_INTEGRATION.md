# Communication integration

Survey assignments use existing MissionInstruction, TaskStatus and AgentHealth envelopes. Peer broadcasts resolve through the configured range and partition. Fixed-sector and independent comparisons disable peer links while retaining the command channel. Session binding, queue bounds, expiry, retransmission and receipt accounting remain router responsibilities.

```mermaid
sequenceDiagram
  participant C as Fixture
  participant R as Router
  participant A as Model 1
  C->>R: Finite survey instruction
  R->>A: Validated envelope
  A->>R: Health and task status
  R->>C: Admitted report
```
