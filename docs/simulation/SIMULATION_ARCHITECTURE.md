# SIMULATION ARCHITECTURE

The CLI owns the engine, invokes a baseline on each private packet and submits a simultaneous action dictionary. Terrain and person identity belong to the environment. Evaluation consumes privileged capture counters. Reset reconstructs state and independent random streams.

```mermaid
flowchart LR
Config --> Engine
Engine --> Sensors --> Packet --> Policy
Policy --> Engine
Engine --> Evaluator
Engine --> Renderer
```

```mermaid
flowchart LR
Actions --> Validate --> Conflicts --> Commit --> Clock --> Events --> Capture --> Delivery
```
