# Phase 10E | Model 2 structured dataset pilot

**The Phase 10E pipeline and symbolic pilot are ready for human review.** The external release at `D:\SWARM-AID-DATA\processed\model2\pilot-2` contains 510 structured examples. The addendum expands its original 18 forms to a first batch of 50 pending reviews. Training approval remains open.

## Custom dataset generation addendum

Revalidated the frozen simulator release and published five reproducible payloads plus a versioned manifest. Separate native and controlled indices resolve to the original reports and preserve parent, seed and split provenance. All 50 review forms cover all 13 episodes collectively. Five disaster families are represented. Dedicated missing-person search and independently labeled unrelated concurrent incidents remain open simulator requirements. Actual coverage includes one controlled conflict, two duplicate/forwarded cases and one controlled false alarm. [Distribution, scenario coverage, leakage checks, storage and exact commands](datasets/MODEL2_ADDENDUM.md)

All three QCRI HumAID shards were verified at the repository-local D-drive staging path. Their 76,484 rows remain a separate disaster-context source. Across HumAID and CrisisMMD, 220 HumAID rows share a passage of at least 12 words. Rights clarification, overlap adjudication and independent human annotations remain outstanding. CrisisNLP remains postponed. [HumAID compatibility](datasets/HUMAID_COMPATIBILITY_REPORT.md) · [CrisisMMD compatibility](datasets/CRISISMMD_COMPATIBILITY_REPORT.md) · [Active review batch](datasets/MODEL2_HUMAN_REVIEW_GUIDE.md)

The addendum introduced `evaluation/data/humaid.py`, `evaluation/data/model2_addendum.py` and the optional DuckDB datasets dependency. Dataset tests cover the sampling summary, index joins, blank forms and text fingerprints. The external replay verified all five derived payloads. The review CLI opened the first queued case and exported zero completed annotations.

## Readiness and scope

The working branch was main at c41a4066b11116bfc64b74e6120b60e100ec4145, with pre-existing uncommitted Phase 10A–D, paper and configuration work. The Phase 9 completion report exists; a separate Phase 9 audit report was unavailable. Inspected the simulator, Model 1 report generation, registered fault fixtures, command journal and assessment/priority/recommendation implementation, wire types, experiment runner, evaluator and Phase 10A manifest/validation code. The sensor validation report records local availability separately from approval. No public datasets were automatically approved.

The earlier run used the repository-local dataset default. The resumed run selected the requested external root through SWARM_DATASET_ROOT and regenerated the pilot there. The local QCRI CrisisMMD v2.0 download contains 16,058 posts and 18,082 image files. All 18,101 snapshot payloads matched the cached index. The inspector now reads the event TSVs with literal quotation marks in tweet text and checks all nine JSON task views. Public labels have documented mappings. Identical media cross benchmark partitions, and source rights and privacy review remain open. Zero public records entered the symbolic pilot. [Public-source audit](datasets/CRISISMMD_COMPATIBILITY_REPORT.md)

## Results

| Measure | Verified result |
|---|---|
| Source evidence | 13 deterministic episodes, 1,138 command-journal report envelopes, 505 selected native examples |
| Controlled cases | Five reconstructed variants with retained parent IDs |
| Groups | 509 distinct episode-scoped sets of contextual/focal report IDs; 70 baseline incidents |
| Labels | 508 weak, two unresolved; all 510 pending independent review |
| Review | 18 selected cases, zero completed reviews; one separate deterministic scenario reference |
| Split | 234 train, 80 validation, 196 test; reserved seeds 42–46 used only in test |
| Operational scope | 129 actual baseline recommendations; no autonomous physical actions, learned-model results or verified rescue outcomes |
| Storage | 36 files, 6,385,696 bytes for pilot-2. The earlier development snapshot pilot-1 occupies another 4,794,811 bytes and is excluded from counts. |
| Replay | All 35 payload checksums in the external release match the earlier pilot-2 manifest. The canonical sorted JSON checksum map hashes to `aa04c9b0edb2bc9142c0bf140947c8cb909b81f29608fe5e61236239e9352106`. |

Relationship and priority supervision address different questions. The weak labels cover routine reports, incident categories, freshness, evidence relationships, urgency and recommendation citation. Expert relevance, evidence sufficiency and free-form summaries have no independently verified targets. Formal recommendations must use the runtime vocabulary. [Input and target specification](datasets/MODEL2_DATASET_SPECIFICATION.md) · [Taxonomy](datasets/MODEL2_LABEL_TAXONOMY.md) · [Evidence grouping](datasets/MODEL2_EVIDENCE_GROUPING.md)

The complete per-scenario, fleet, evidence, assessment, relation, urgency, missing-modality, split and status counts are in [pilot statistics](datasets/MODEL2_DATASET_STATISTICS.md) and the generated statistics.json. Leakage validation protects scenario-seed, mission, episode and transformation lineage. The sample ID is a join key. Feature export excludes the scenario/seed, variant name, evaluator references, future context and baseline targets. Across partitions, 38 simplified context patterns recur. This limits benchmark independence even when there is no shared episode. [Limitations](datasets/MODEL2_DATASET_LIMITATIONS.md) · [Prospective evaluation](datasets/MODEL2_EVALUATION_SPECIFICATION.md)

## Deliverables and checks

New research-only modules in evaluation/data are model2_records.py (types and relationship logic), model2_collect.py (native capture and controlled cases), model2.py (versioned export, validation, review and CLI) and crisismmd.py (local public-source inspection). The generation configuration is configs/datasets/model2_pilot.json. The added test module is tests/unit/test_model2_dataset.py. Documentation consists of this report and the ten Phase 10E documents in docs/datasets linked here. There were no changes to the simulator, command agent, wire protocol or provider contracts.

Reproduce with the [generation guide](datasets/MODEL2_DATASET_GENERATION.md). Reviewers can use the [annotation procedure](datasets/MODEL2_ANNOTATION_GUIDE.md) and [human review workflow](datasets/MODEL2_HUMAN_REVIEW_GUIDE.md).

The dataset validator verifies indexed source hashes, source receipt and journal agreement, sample IDs, timestamps, parent reconstruction, known split assignments, target/evidence links, feature projection and Phase 10A manifest compatibility. It revalidated pilot-2 without error. The generated content passed a full independent replay. Local hashes establish byte identity only; the release metadata is not externally signed.

## Phase 10F decision

### Verification on Windows CPU with Python 3.12.10

The virtual environment launcher points to a missing base executable on this host. Checks used `.tools\phase10a-check\python.exe`, which loads the existing virtual environment's site-packages. Test temporary storage was under `.tools\audit-test-temp` on D:.

| Check from repository root | Exit | Actual result |
|---|---:|---|
| python -m pip check | 0 | No broken requirements. Initial sandboxed invocation exited 1 at Windows known-folder lookup; the authorized host check succeeded. |
| python -m pytest -q | 0 | 257 passed, 1 skipped, 3 deprecation warnings in 178.90 s |
| python -m pytest -q tests/unit/test_model2_dataset.py tests/integration/test_command_agent.py | 0 | 29 passed, 1 deprecation warning in 11.94 s |
| python -m ruff check . | 0 | All checks passed |
| python -m mypy | 0 | Strict checking passed across 137 files |
| python -m evaluation.data.model2 validate --version pilot-2 | 0 | 234 train, 80 validation, 196 test |
| Phase 10A CLI against release registry.json and manifest.json | 0 | Same split counts |
| Viewer / reviewed export smoke check | 0 | First queued feature record opened; zero reviewed records exported |

### Disposition

The simulator limitations and benchmark gaps are documented inputs to a future Phase 10F design review. Independent expert labels, source governance, a leakage-safe public partition and broader scenario diversity remain open. Work stopped at Phase 10E for review.
