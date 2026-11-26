# Phase 10I-B1/C1 Model 1 preparation report

**Status: candidate-only audits completed; human review and governance remain open.**
**Training decision: NO-GO.** This work does not authorize data use, training,
Phase 10I-D1/E1 execution, Model 2 work, or Phase 11.

## Scope and reproducibility

The pass covered ten public Model 1 sources: HERIDAL, SARD, FLAME, FloodNet,
RescueNet, WiSARD, ESC-50, Smoke Detection IoT, UCI Air Quality, and USGS.
It used the local Phase 10G indexes and Phase 10I-A hash ledger, did not
re-download or modify raw data, did not access private Model 2 or alert data,
and ran on CPU with two workers. Processing took 196.599 seconds. Mask class
counts were recomputed for 2,343 FloodNet and 4,494 RescueNet masks.

The frozen Phase 10H release remains SHA-256
`81b0ed436ce8e2bc3ec260f85a87dc89c28f95dc585e3309d8ae3e88c57e11b8`.
All 41 repository entries and 19 evidence entries recorded in the historical
release were independently checked against their recorded digests. The
historical release was not changed. The built-in `final_release --verify`
command currently raises `KeyError: evaluation/data/model1_prep.py` because
its dynamic source glob includes this new file, which is not part of the
historical manifest; this is not a mismatch in any recorded release file.

Candidate artifacts are stored outside the repository at
`D:\SWARM-AID-DATA\manifests\phase10i-b1-c1-v1`. Their checksum manifest
covers 18 artifact files. Input bindings record the preparation-code digest,
Phase 10H release digest, Phase 10I-A summary and ledger digests, registry,
source indexes, and the Phase 10G visual files used by the audit. Candidate
files are not training manifests and are not consumed by an approved-training
loader.

## Main findings

| Source(s) | Verified result | Disposition |
|---|---|---|
| HERIDAL | 1,600 indexed images, 3,194 boxes, 560 empty-annotation images, no invalid boxes | Human review and parent flight/site metadata required |
| SARD | 5,755 indexed images, 7,424 boxes, 832 empty-annotation images, no invalid boxes | Human review and parent flight/site metadata required |
| FLAME classification | 4,419 near train/test frame pairs; 491 distinct training frames excluded; zero exact cross-split image-hash groups | Candidate only; parent video/capture independence unresolved |
| FLAME segmentation | 2,003 unpaired masks; zero verified mask/image pairs | Blocked; no filename-based pairing inferred |
| FloodNet / RescueNet | 2,343 / 4,494 indexed image-mask paths; decoded class-pixel totals match the frozen Phase 10G visual summaries | Site/flight independence and governance remain unresolved |
| WiSARD | 1,275 annotation flags, 11,542 missing sidecars, zero verified RGB/thermal pairs | Blocked; RGB/8-bit display-coded imagery is not calibrated temperature |
| ESC-50 | Four publisher recording IDs cross official folds; nine clips excluded; 1,991 retained | Candidate preserves official folds; clip terms still need review |
| Smoke | Five runs reduce to three repeated sensor-signature groups | No split emitted |
| UCI | 7,603 candidate windows (5,052 train / 1,198 validation / 1,353 test); 0 raw-row reuse across partitions | Temporal-only candidate; one-site generalization and governance block training |
| USGS | 36 interval summaries, one station, 152 overlapping interval pairs | Not eligible as a continuous-series task |

The complete machine-readable task disposition is
[phase10i_b1_c1_model1.json](../configs/datasets/phase10i_b1_c1_model1.json).
Detailed candidate and quality records are in the D-drive release directory.

## Candidate and human-review outputs

Three candidate manifests were produced: FLAME (47,501 candidate records),
ESC-50 (1,991), and UCI (7,603). All state
`training_approved=false`, `approved_training_records=0`, and
`human_review_required=true`. The human-review queue contains 152 pending
items with a nominal 426 reviewer-minutes estimate. It is a review queue, not
completed annotation; no human labels or decisions were created.

All 14 listed Model 1/native task dispositions are **BLOCKED**. The readiness
matrix is in [the candidate readiness report](datasets/PHASE_10I_B1_C1_MODEL1_CANDIDATE_READINESS.md).
The grouping evidence is in [the leakage audit](datasets/PHASE_10I_B1_C1_GROUPING_LEAKAGE_AUDIT.md);
label review and governance evidence are in their linked reports below.

## Safety and authorization

- Training and governance approvals granted: **0**.
- Approved training records: **0**.
- Model training, protected evaluation access, private Model 2 access, and raw
  data modification: **none**.
- D1/E1 work and Phase 11: **not started**.
- No source permission, privacy clearance, label correction, site identity,
  flight identity, or missing pairing was inferred.

## Verification

| Check | Result |
|---|---|
| Candidate audit run | Completed; 10 source indexes verified, mask decoding completed |
| Candidate artifact checksums | 18 files verified; no mismatch |
| Frozen Phase 10H recorded files | 41 repository and 19 evidence entries verified |
| Built-in Phase 10H verifier | Fails on newly added module being absent from historical manifest; recorded historical files independently verified |
| Full pytest suite | **285 passed, 1 skipped, 3 warnings** in 251.91 seconds |
| `pip check` | Passed; no broken requirements |
| `ruff check .` | Passed |
| Strict MyPy | Passed; no issues in 161 source files |
| Focused candidate tests | 7 passed; one existing Starlette/httpx deprecation warning |
| Focused Ruff and strict MyPy | Passed |

## Handoff

This report proposes, but does not execute, the separate human-review and
governance handoffs in [D1](PHASE_10I_D1_HANDOFF_PROPOSAL.md) and
[E1](PHASE_10I_E1_HANDOFF_PROPOSAL.md). Obtain explicit authorization before
starting either. Do not train or advance to Phase 11.
