# Phase 13E completion report: memory and resources

2026-11-27. **Complete.** Data: `D:\SWARM-AID-DATA\runs\phase13\cluster1\13e`.

## All seven models in one process (MiB)

Includes experimental WiSARD RGB and comparison-only neural fusion; the five READY models were not
measured as a separate set.

| Measure | CPU before → after | CUDA run before → after |
|---|---:|---:|
| RSS before loading | 502 → 502 | 519 → 520 |
| RSS after loading | 1,140 → 759 | 1,126 → 778 |
| RSS after warm-up | 1,212 → 869 | 2,061 → 1,700 |
| Peak RSS | 1,265 → 874 (−31%) | 2,066 → 1,713 (−17%) |
| GPU allocated / reserved peak | — | 224 / 256 → 224 / 256 |

Model parameters and buffers total 169 MiB. After release, 9 MiB allocated and 20 MiB reserved
remain; process RSS is not returned to the system. Total device memory rose about 550 MiB above
idle (855–858 MiB), which includes the CUDA context.

## Change

The only demonstrated inefficiency addressed is checkpoint loading (see 13B): unused optimizer and
loop state is no longer read. No cache clearing per inference, no limits and no state removed.

## Stability and isolation

Five windows of 40 passes were flat before and after (CPU RSS 1,213 → 871; CUDA 181.5 MiB
allocated both times), with each model loaded once. No leak existed or is claimed fixed. A test
shows a mapped checkpoint can be deleted after loading, so no mapping is retained. Image reuse is
scoped to one call and Model 2 indexes to one instance.

## Provisional RTX 2060 budget (not verified)

Assumption 6 GiB VRAM. Measured here: 256 MiB peak reserved, about 550 MiB total device increase,
1.7 GiB process RSS. All seven models appear to fit comfortably, so keeping only two resident
(current RTX 2060 file) trades about a second per seven-model pass for little memory. Changing
that, or FP16 (slower here), is an owner decision and needs measurement on the target.
