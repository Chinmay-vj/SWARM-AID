# Phase 10A completion report

**Completed 2026-11-25 on Windows CPU. Phase 10B is ready for manual release verification.** All 11 external datasets remain candidates pending release-specific licence and privacy review. The deliverable consists of offline infrastructure, documentation and deterministic test fixtures. Dataset acquisition, model selection/training and simulator changes were outside this phase.

## Handover and baseline

The initial working tree was clean on main at c41a406 (Phase 9 system integration), matching the local origin/main ref. One local branch and one worktree were present. Local tags ran through v0.6.0 and v0.8.0; Phases 7 and 8 share a commit. The v0.9.0 tag was absent. The handover's read-only GitHub milestone query returned an empty list. The Phase 9 completion report predates its commit and includes prior-phase audit findings. Standalone tracked audit reports exist for Phases 4, 5 and 6. Independent Phase 9 audit sign-off could not be established. The Phase 9 report recorded 217 Python passes and one PostGIS skip. Phase 10A verified the Python suite again below.

## Deliverables

| Deliverable | Implementation and interpretation |
|---|---|
| Model 1 | [Task-by-task requirements](datasets/MODEL1_DATA_REQUIREMENTS.md) cover aerial RGB, thermal, environment, smoke/fire, flood, structural damage, audio, environmental sensors, fusion and uncertainty. The live interface supplies scoped Evidence and symbolic readings. External physical samples are required for perception. Audio has no operational wire variant. |
| Model 2 | [Episode and target requirements](datasets/MODEL2_DATA_REQUIREMENTS.md) specify accepted reports and source lineage, conflicts, independent sources, missing/stale evidence, assessment and priority outputs, recommendation expiry and revision-bound human review. Expert labels remain unavailable. |
| MARL | [Trajectory requirements](datasets/MARL_DATA_REQUIREMENTS.md) define scenario/run/agent metadata, action and availability history, termination, evaluation and reproducibility. The four-integer PettingZoo observation and integrated mission traces have separate semantics. |
| Registry and schemas | [Candidate registry](../configs/datasets/registry.json), [registry schema](../configs/datasets/schemas/registry.v1.json), [manifest schema](../configs/datasets/schemas/manifest.v1.json) and [storage schema](../configs/datasets/schemas/storage.v1.json). The registry records unknowns and review states. Manifest roles separate operational inputs, supervised targets and evaluator labels. |
| Inventory and acceptance | [Primary-source inventory](datasets/DATASET_CANDIDATE_INVENTORY.md), [annotation standards](datasets/ANNOTATION_STANDARDS.md), [quality gates](datasets/DATA_QUALITY_REQUIREMENTS.md) and [licence/privacy policy](datasets/DATASET_LICENSE_POLICY.md). Source-specific class mappings, ignore semantics, expert review and acceptance thresholds remain open. |
| Validation and leakage | [Offline validator](../evaluation/data/validation.py), [contract/CLI guide](datasets/DATASET_REQUIREMENTS.md) and [split policy](datasets/DATA_LEAKAGE_PREVENTION.md). Validate the full proposed collection together. Enforce reserved synthetic test seeds 42–46; shared incident, mission, episode, sequence, location, event, pair and content groups stay in one partition. |
| Storage | [Storage plan](datasets/DATASET_STORAGE_PLAN.md) and configurable external root. D: had 365.2 GiB free at measurement. A hypothetical 61 GiB staging budget illustrates capacity calculation; actual release sizes remain unknown. Layout helper separates immutable sources, references, derived data, labels, simulation records and future artifacts. |
| Simulation and future work | [Limitations and Phase 10F specification](datasets/SIMULATION_LIMITATIONS_AND_PHASE_10F.md) classify effects on Phases 10, 11, 12 and research evaluation. [Artifact conventions](datasets/DATASET_REQUIREMENTS.md) bind future models to provider/schema versions, dataset and manifest digests, configuration, evaluation evidence and CPU compatibility. |
| Phase 10B | [Readiness and collection order](datasets/PHASE_10B_READINESS.md). Verify aerial human detection releases first, then thermal and paired sources, disaster mapping, optional audio and symbolic episode preparation. No release has acquisition approval. |

## Actual verification

Run from the repository root using Python 3.12.10 and existing Windows CPU dependencies. The local .venv launcher points to an unavailable base executable. An ignored verification interpreter at `.tools/phase10a-check/python.exe` uses the bundled Python binary and .venv site-packages. Python 3.11 and the frontend suite were not exercised during 10A.

| Command | Result |
|---|---|
| python -m pip check | Exit 0, no broken requirements. Windows known-folder lookup required running this read-only check outside the sandbox. |
| python -m pytest -q | Exit 0, **249 passed, 1 skipped, 3 warnings** in 99.36 s. PostgreSQL/PostGIS integration requires SWARM_TEST_POSTGRES_URL. Warnings came from Starlette/FastAPI test-client and PettingZoo deprecations. |
| python -m pytest -q tests/unit/test_dataset_infrastructure.py | Exit 0, 32 passed. |
| python -m ruff check . | Exit 0, all checks passed. |
| python -m mypy | Exit 0, strict check passed for 130 source files. |
| python -m evaluation.data | Exit 0, 11 candidates, zero sample rows. |
| python -m evaluation.data --registry tests/fixtures/data/registry.json tests/fixtures/data/symbolic.json | Exit 0, one deterministic symbolic fixture row in test. |

## File inventory and limitations

Added `evaluation/data/{__init__,__main__,contracts,pipeline,validation}.py`, `configs/datasets/{registry,storage}.json`, and registry, manifest and storage v1 JSON Schemas under configs/datasets/schemas/. Added tests/unit/test_dataset_infrastructure.py and tests/fixtures/data/{registry,symbolic}.json. Added the twelve documents under docs/datasets/ linked above and this report. Modified README.md, .gitignore and pyproject.toml for discoverability, artifact exclusions and packaged configuration. Empty local layout directories live under the ignored datasets/ root.

Validation depends on truthful source metadata, canonical group IDs, verified hashes and inclusion of all relevant manifests. Exact hashes cannot discover re-encodings. Generic format checks cannot establish annotation accuracy or replace source-specific decoding. Private filesystem permissions and review decisions belong to storage and governance owners. Evidence provenance is scoped to its mission; a symbolic artifact key carries no media bytes. Reproducible symbolic experiments cannot measure physical sensor performance.

The simulator still has limited disaster diversity and no missing-person fixture. PostgreSQL/PostGIS, exact simulation continuation, the integrated MARL environment, trained-provider selection, model artifact resolution and complete provider-version attribution retain their prior limitations. Phase 10A produced no downloaded data, trained weights, new Git milestone, commit or push.
