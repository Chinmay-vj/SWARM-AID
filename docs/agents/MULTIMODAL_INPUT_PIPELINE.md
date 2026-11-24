# MULTIMODAL INPUT PIPELINE

Inputs.ingest validates ownership, capture age, score and evidence identity. Each accepted reading carries mission, owner, schema version, representation and grid reference; its Evidence supplies modality, capture time, source and identifier. The mock packet uses symbolic terrain labels and synthetic scores. Absent modalities produce no placeholder detections. New physical measurement types require an adapter that supplies their units and reference frame. Peer observations and mission instructions enter through DroneAgent.receive with a trusted fixture principal.

```mermaid
flowchart LR
Packet --> Scope --> Freshness --> EvidenceIndex --> FilteredFrame
```
