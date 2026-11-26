# Dataset infrastructure v1.0

Start from the repository root. The offline package `evaluation.data` depends on the existing core Pydantic installation. It has no runtime role in the agents, API or dashboard. All files named below are relative to the checkout unless an external data root is configured.

```powershell
python -m evaluation.data
python -m evaluation.data --schema manifest
python -m evaluation.data --registry path/to/reviewed-registry.json path/to/inputs.json path/to/targets.json
python -m evaluation.data --verify-files --registry path/to/reviewed-registry.json path/to/inputs.json path/to/targets.json
```

The first command validates the candidate registry. Supply **all manifests in a comparison together**, including partitions from other releases, for leakage checks. A zero exit code on a metadata check establishes structural consistency only. File mode additionally verifies governance statuses, presence, SHA-256 and supported annotation checks. Independent review of source content is still required.

| Contract | Required interpretation |
|---|---|
| Registry | Inventory key is (dataset ID, release version). A candidate may have a null version. Pin a release and its source, rights, attribution and verified digest before collection. Unspecified counts, sizes and formats remain unknown. |
| Manifest | One dataset release, role and manifest revision per document. Format version 1.0 is independent of source release, label schema and mission wire versions. Runtime validators enforce constraints beyond JSON Schema. |
| Sample | Stable original source reference, source sensor/agent ID, licence reference and grouping keys. For crops or conversions, preserve the original parent reference and record transformation settings externally. Root-relative POSIX paths are portable to Windows. |
| Physical input | Actual source asset described by file path, availability and SHA-256. Missing-file status records a known expected asset. Unknown hash prevents promotion into a versioned manifest. Dimensions are (width,height); record audio rate in Hz when known. |
| Synthetic symbolic input | Evidence objects retain the original UUID, origin, capture tick, modality and opaque artifact key. Record mission, scenario, seed and sampling tick. Preserve original observation UUID whenever an observation already exists. The symbolic sample has no media file or dimensions. |
| Targets | Separate manifests for training targets and evaluator labels. Match to operational rows by dataset/version/sample ID. Training targets require a label source and schema version. Human adjudication requires a review reference. |

Use the [Model 1](MODEL1_DATA_REQUIREMENTS.md), [Model 2](MODEL2_DATA_REQUIREMENTS.md) and [MARL](MARL_DATA_REQUIREMENTS.md) specifications for task-specific eligibility. Required context can be unknown at inventory time. At release review, record source platform, viewpoint, capture conditions and coordinate frame in release metadata where available. Grid cells use `swarm-aid:grid`; record physical coordinates only with documented units, reference system and privacy approval.

### Pipeline ownership

A future source adapter implements `SourceAdapter.ingest` over immutable raw files. Emit one typed Sample per original item. Use `SampleTransform.transform` for annotation conversion and preprocessing, retaining parent and transform version. Serialize Manifest with Pydantic; run collection validation before freezing group assignments. SHA-256 identifies exact duplicates, grouping metadata captures lineage, and validation returns per-split counts for reporting. Save manifest bytes and their digest with the report. Future source adapters own decoding, semantic annotation checks and near-duplicate review.

### Future model artifact record

Use a small release JSON document containing provider_id (stable consumer/task name), provider_version, artifact_id (immutable identifier), artifact_sha256, training dataset IDs and versions, manifest versions **and byte digests**, input/output schema versions, code commit, training config digest and reproducible config reference, seeds, evaluation run ID, held-out split digest and metrics with denominators. Record Python range, dependencies, supported modalities, missing-input behavior and CPU memory/runtime measurements. Check digest, schema compatibility and CPU load before enabling an adapter. Continue using existing deterministic providers until a future provider passes independent validation. No trained artifact is registered in 10A.
