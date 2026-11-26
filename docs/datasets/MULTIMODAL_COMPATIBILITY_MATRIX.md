# Modality compatibility

| Relationship | Measured evidence | Supported use and boundary |
|---|---|---|
| RGB + semantic mask | 2,343 FloodNet and 4,494 RescueNet paired source images, indexed masks and matching dimensions | Private segmentation review. Use nearest-neighbor mask resizing and explicit ignore padding. |
| Visible + thermal | WiSARD has 26,252 visible and 29,878 infrared-labeled files. All indexed images report RGB mode with three display channels. Camera/platform tokens occur in sequence names. | Separate image/thermal previews. Zero verified synchronized pair IDs; unmatched count relative to a true pairing schedule is unknown. Intrinsics, clock offsets, calibration and registration remain unverified. Display intensity cannot supply temperature. |
| Source image + post | 18,082 CrisisMMD event pairs; multiple task views share content | Source-local disaster-context preview. Labels may differ by modality. |
| Environmental audio + scene | 2,000 independent ESC-50 clips, no join to field observations | Environmental sound categories only. Rescue calls, victim distress and synchronized acoustic evidence lack verified targets. |
| Stationary sensors + imagery | Three sensor sources with different sites, time bases and units | Independent scalar/interval tasks. No verified image, weather or audio pairing. |
| Source text + native reports | Public posts have no common mission clock, origin agent or evidence IDs with the simulator | Separate context tasks. No valid row-level join. |
| Symbolic modalities + delivered report | Replay links readings to a native report and receipt. 3,311 complete and 6,154 incomplete report frames | As-of structured development previews. Preserve missing channels, timing, uncertainty and shared origins. No real pixels or waveforms are present. |

Models may need separate modality encoders, masks for absent inputs and variable-length context. A future fusion evaluation requires authoritative pair references and measured timing/alignment appropriate to the task. [Label mapping](DATASET_LABEL_MAPPING.md)
