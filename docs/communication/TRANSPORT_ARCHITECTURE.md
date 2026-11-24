# TRANSPORT ARCHITECTURE

Router owns a mission and a single simulation clock. Its scoped SimulatedPort implements async send and nonblocking receive (QueueEmpty when empty). The synchronous simulator uses the same submit path through a bound callback. Route eligibility is injected into the transport. Only the trusted adapter uses simulated positions. Each delivered object is reconstructed from immutable JSON bytes. Consumers cannot obtain another agent's memory through a packet.

```mermaid
sequenceDiagram
participant A as Drone A
participant R as Router
participant B as Drone B
A->>R: Observation to peers
R->>R: Snapshot eligible members
R->>B: Decode at delivery barrier
B->>B: Remember original evidence
```

```mermaid
sequenceDiagram
participant D as Drone
participant R as Router
participant C as Mock command
D->>R: Report envelope
R->>C: Deliver report
C->>R: ACK referencing report ID
R->>D: Track ACK
```
