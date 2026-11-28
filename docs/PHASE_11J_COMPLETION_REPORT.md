# SWARM-AID Phase 11J Completion Report

Date: 2026-11-27. Scope: civilian search-and-rescue **simulation**; validation-only evidence. No training, no
reserved-test access, no physical control.

## Status

| Item | Status |
|---|---|
| A Model registry | Complete |
| B Perception pipeline | Complete; inference batch size is fixed at 1 |
| C Missing modalities, thermal exclusion | Complete |
| D Local memory and reasoning | Complete, using existing agent components |
| E Structured evidence | Complete; ledger is in memory and not persisted |
| F Model 1 to Model 2 | Complete for visual and symbolic findings; ESC-50 and CO forecast stay agent-local |
| G Multi-agent simulation | Complete (symbolic) |
| H End-to-end tests | Complete; dashboard not tested |
| I Profiling, RTX 2060 | Measured on RTX PRO 4500; RTX 2060 unverified |
| J Verification, migration | Verified; copy to the owner's destination is pending |

## What was built

- `evaluation/model1/registry.py`: checksum-verified, `weights_only`, strict, lazy, bounded, frozen models.
  A missing or corrupt checkpoint is `UNAVAILABLE`; random weights are never substituted.
- `evaluation/model1/perception.py`: task-specific preprocessing and output semantics; `MediaPerception`
  implements the existing `PerceptionProvider` port.
- `agents/drone_agent/evidence.py`: structured evidence, per-agent episode ledger, deterministic fusion.
- `Fleet(record_evidence=True)`: opt-in evidence and fusion for symbolic runs.
- `simulation.sensors.mock.fixture_packet`: labelled synthetic media carrier for adapter tests.
- Wire contracts, protocol and Model 2 reasoning are unchanged.

## Selected models (validation only)

| Model | Metric | Value | State |
|---|---|---:|---|
| RescueNet (optimized) | mIoU | 0.631604 | READY |
| FloodNet (optimized) | mIoU | 0.684977 | READY |
| FLAME (baseline) | macro F1 | 0.985144 | READY |
| ESC-50 (optimized) | macro F1 | 0.625182 | READY |
| UCI CO (optimized) | MAE | 0.673876 | READY |
| WiSARD RGB (baseline) | mAP50 | 0.105056 | EXPERIMENTAL |
| Neural environmental fusion | symbolic macro F1 | 1.0 | EXPERIMENTAL (comparison only) |
| WiSARD thermal | - | - | EXCLUDED |
| Smoke Detection IoT, USGS Water | - | - | UNAVAILABLE (deferred) |

All seven checkpoints passed checksum and strict loading. RescueNet: 0.631604 is the saved epoch-2 value and the
highest of the 8 epochs in the training log; no higher value is recorded there.

## Verification

- Phase 11J tests: 18 passed. Full suite: 374 passed, 0 failed, 1 skipped (PostgreSQL not configured).
- Ruff, strict mypy (affected modules), `pip check`, `git diff --check`: passed.
- Fixed during verification: `evaluation/data/validation.py` raised `FileNotFoundError` instead of
  `file unavailable` for a missing asset (from an earlier uncommitted change).
- End to end: fixture image, perception, memory, safety gate, router, Model 2, operator alert with evidence
  lookup. Alert-path assertions use a scripted test double. Real checkpoints ran the same path on a flat
  synthetic image; this verifies plumbing, not accuracy.
- Not tested: frontend (no `node_modules`), backend persistence of model-derived findings, PostgreSQL, accuracy.

## Profile (synthetic inputs, batch 1)

| Measure | Result |
|---|---|
| Checkpoint load | 0.01-1.4 s |
| GPU latency per model | 1-19 ms across FP32, FP16, BF16 |
| CPU latency per model | 0.5-52 ms |
| All seven resident, one pass | 66-75 ms GPU; 147 ms CPU |
| Peak GPU, all resident | 224 MiB allocated, 254 MiB reserved (excludes CUDA context) |
| Process peak RSS | about 3.3 GiB |
| 6 agents sharing one FLAME instance | median 62 ms per tick, one load, no provider errors |

## Deviations and limitations

- **Reserved seed:** seed 42 is the `Engine` default. The first 11J test run and first multi-agent profile used it
  before correction to development seed 3500; existing regression tests also use default seeds. Nothing was
  trained, selected or evaluated from those runs. Review before treating seed 42 as unseen.
- Segmentation flag share (0.05) and minimum confidence (0.5) are unvalidated engineering defaults.
- Low-confidence output is recorded as abstained and sends no finding. This is not evidence of safety.
- The wire contract has no audio modality or quantity field.
- The backend runtime and dashboard do not yet use model adapters or show ledger provenance.
- Media inference needs media the symbolic simulator does not produce.
- WiSARD RGB is unreliable; thermal is excluded; a missing detection never means an area is clear.
- UCI persistence (with CO history the model lacks) remains the stronger reference.
- FLAME video independence and RescueNet/FloodNet site and flight independence are unverified.
- Deterministic fusion is preferred, but wrong observations degrade it badly.
- Reserved-test evaluation is pending. RTX 2060 performance is unverified.

Machine-readable reports: `D:\SWARM-AID-DATA\runs\phase11j`.

## Correction added during Phase 12A

The full-suite runs in Phase 11J also executed reserved seeds 43, 44 and 45 through existing tests
(`test_field_scenarios`, `test_system_integration`). The reserved-seed note above mentions only 42.
