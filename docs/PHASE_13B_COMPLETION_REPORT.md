# Phase 13B completion report: perception inference

2026-11-27. **Complete.** Shared method, memory and checks: `PHASE_13_CLUSTER1_COMPLETION_REPORT.md`.
Data: `D:\SWARM-AID-DATA\runs\phase13\cluster1\13b`.

## Retained changes

1. `registry.py`: `torch.load(..., mmap=True)`. Checkpoints are about six times the model size
   because they also hold optimizer and loop state, which is now not read into memory.
2. `perception.py`: when several image models consume one artifact, it is decoded once and
   resized once per size. The reuse object lives only inside one `perceive` call.
3. `perception.py`: segmentation class counts are synchronized with the device once, not per class.

## Latency, median ms of three rounds (batch 1, FP32)

| Measurement | Before | After | Change |
|---|---:|---:|---:|
| Frame, four image models, CUDA | 50.35 | 36.91 | −26.7% (1.36×) |
| Frame, four image models, CPU | 150.06 | 131.81 | −12.2% (1.14×) |
| Segmentation post-processing, CUDA | 1.16 | 0.72 | −38% |
| Segmentation post-processing, CPU | 1.82 | 1.82 | none |

| Single model | CPU before → after | CUDA before → after |
|---|---:|---:|
| RescueNet | 49.7 → 48.7 | 11.6 → 10.9 |
| FloodNet | 49.8 → 48.2 | 11.5 → 11.1 |
| FLAME | 9.6 → **10.4** | 9.7 → 9.0 |
| WiSARD RGB | 36.0 → 35.8 | 15.8 → 15.2 |
| ESC-50 | 3.68 → 3.68 | 4.20 → 4.25 |

Single-model differences are small and mostly within round-to-round variation. CPU FLAME measured
slower (rounds 9.4–9.8 before, 9.5–10.5 after); its path was not materially changed.

## Loading

| Model, device | First load ms | Reload ms | Peak RSS MiB |
|---|---:|---:|---:|
| RescueNet, CPU | 1,284 → 1,200 | 251 → 195 | 886 → 670 |
| WiSARD RGB, CPU | 1,543 → 1,405 | 303 → 219 | 1,092 → 724 |
| FLAME, CPU | 920 → 896 | 99 → 90 | 622 → 590 |
| RescueNet, CUDA | 1,396 → 1,306 | 266 → 200 | 1,009 → 751 |
| WiSARD RGB, CUDA | 1,655 → 1,496 | 319 → 226 | 1,213 → 775 |

First load still includes the lazy torchvision import. Checksum verification remains the largest
part of reload and was kept.

## Device placement (one pass of all seven models, ms)

| Placement | Before | After |
|---|---:|---:|
| All CPU | 162.1 | 148.9 |
| All CUDA (existing default) | 56.6 | 56.6 |
| Mixed | 56.0 | 54.1 |
| RTX 2060 config file (FP16, two resident) | 1,212 | 946 |

Mixed placement shows no meaningful benefit. The RTX 2060 configuration reloads all seven models
on every pass because only two stay resident. **No default was changed.**

## Consistency

Tolerance was fixed beforehand (CPU exact; CUDA absolute 1e-5). All 33 tensor cases and 44 record
cases per device were bit-identical, including invalid, missing and excluded inputs. A further 44
synthetic segmentation cases, including values around the flag threshold, matched the old code.
Synthetic inputs show consistency, not accuracy. Thermal stays excluded.

## Not done

Meta-device construction, startup import or warm-up code (relocates cost), skipping checksums,
stripping checkpoints, precision or placement changes. An added `infer` argument was reverted
because it broke an existing test double.
