# SENSOR SIMULATION

RGB and thermal emit symbolic candidates within a Manhattan footprint. Smoke, buildings, damaged structures and debris obscure possible people. Environment readings label terrain. GPS supplies local position, IMU supplies heading and text supplies a survey instruction. Dropout applies per modality per capture. Miss and spurious detection probabilities apply per eligible cell; noise displaces a candidate to the observer cell. Frames arrive after the configured latency. Evidence is synthetic and has no measured computer-vision accuracy.

```mermaid
flowchart LR
World --> Footprint --> Occlusion --> Noise --> Evidence --> Delay --> Packet
```
