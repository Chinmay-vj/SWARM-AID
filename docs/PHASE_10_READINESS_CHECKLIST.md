# Phase 10 readiness checklist (dataset collection)

Prepared at the end of Phase 9 (2026-11-24). Phase 10 has not started. Items marked **Open** are
prerequisites or decisions for Phase 10 itself, not Phase 9 defects.

## Platform

| Item | Status | Evidence |
|---|---|---|
| Integrated stack runs locally on CPU, single command | Ready | `scripts/start_system.ps1`; final cycle returned in 8 s |
| Configuration validated before start | Ready | `python -m orchestration check` (37 checks, 0 errors) |
| Graceful shutdown that touches only owned processes | Ready | five scripted stop/start cycles; held missions recorded "backend shutdown" |
| Headless integrated runs for synthetic data generation | Ready | `python -m orchestration run` / `matrix`; identical fingerprints across processes |
| Reproducibility manifest (code revision, config digest, environment) | Ready | `orchestration/manifest.py` |
| Evaluator isolation from operational components | Ready | object-graph and endpoint leakage tests |
| Provenance of every observation (agent, modality, capture time, artifact key) | Ready | provenance tests; `GET /observations/{id}/trace` |
| Conflicting evidence preserved end to end | Ready (fixed in Phase 9) | backend regression test, connected e2e |
| Backend persistence on SQLite | Ready | 217 passing Python tests, restart verification |
| Backend persistence on PostgreSQL/PostGIS | **Open** | implemented, unverified; needs authorization to install PostgreSQL or Docker |

## Data-collection prerequisites (decisions for Phase 10)

| Item | Status | Reference |
|---|---|---|
| Dataset inventory (which public datasets, per modality) | **Open** | DATASET_COLLECTION_READINESS.md §"Datasets the later phases need" |
| Licence review per dataset | **Open** | same, §"Privacy, ethics and licensing" |
| Label schema (person / possible / none / uncertain; hazard classes mapped to simulator hazards) | **Open** | same, §"Label definitions" |
| Per-sample metadata schema | Specified | same, §"Required metadata per sample" |
| Storage layout and manifests (git-ignored data root) | Specified | `datasets/` (only `.gitkeep` tracked) |
| Split policy by scenario/location/sequence; reserved evaluation seeds 42–46 | Specified | same, §"Splits and leakage prevention" |
| Privacy handling for imagery of people | Specified, needs approval | same |
| Synthetic episode generation for MARL and Model 2 | Ready to use | `orchestration matrix` (no data generated yet) |

## Interfaces needed by Phases 11–12 (not blockers for Phase 10)

| Item | Status | Reference |
|---|---|---|
| Model 1 provider ports and validation | Ready | MODEL_PROVIDER_READINESS.md |
| Provider factory, versioning, artifact resolver | **Open** | same, "Gaps before Phase 11" |
| Model 2 provider ports and independent guards | Ready | same |
| PettingZoo environment API | Ready (minimal) | MARL_READINESS.md |
| MARL environment over the integrated stack (transport, safety, Model 2) | **Open** | same, "Gaps for Phase 12" |

## Known limitations carried into Phase 10

- Disaster profiles differ only in tile labels (wildfire and flood simulate identically).
- No missing-person scenario fixture exists.
- Mock sensors are symbolic; there is no pixel, thermal-image or audio content anywhere.
- Evidence objects are never uploaded by the simulator.
- Simulations cannot resume after a backend restart.

**Readiness for Phase 10: READY WITH LIMITATIONS** (see `docs/PHASE_9_COMPLETION_REPORT.md`).
