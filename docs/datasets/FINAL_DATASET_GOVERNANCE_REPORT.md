# Release governance and privacy

**Zero public or native records are approved for training.** Private review indexes can reference restricted source assets. Publisher statements, repository access and local byte identity each establish different facts. No signed, task-scoped licence and privacy decision was found for these releases. Public exports may contain identifiable imagery, accounts, locations or voices and require separate authorization.

| Source | Evidence and unresolved terms | Required decision before export or training |
|---|---|---|
| HERIDAL | Local Roboflow v1 export and COCO boxes. Chain to the original IPSAR imagery and derivative permissions incomplete. | Verify origin, participant/location scope and attribution. |
| SARD | Roboflow v17 TILES_3x3 README records undefined licence. | Establish rights to tiles, labels and derivative use from source owner; review participant imagery. |
| FloodNet | Supervised v1.0 publisher identifies CDLA Permissive terms. | Match acquired version, preserve notices and confirm scope for property imagery. |
| RescueNet | Authors identify CC BY-NC-ND for the dataset. Processed labels and distribution of adaptations need source-specific review. | Document permitted purpose, attribution and handling of derivative outputs and locations. |
| FLAME | Local classification and mask directories have no recorded task approval. | Pin component release and rights, including modified frames and property/location content. |
| WiSARD | Folder names identify a v1 collection of human search imagery; authoritative edition and acquisition terms are unpinned. | Review visible/thermal participant imagery, paths, metadata, redistribution and source credit. |
| ESC-50 | Author’s ledger identifies CC BY-NC for the collection and clip-specific credits/terms. | Record clip attribution and intended noncommercial scope; review voices. |
| Smoke | Experimental CSV; upstream grant for the specific export unverified. | Trace export and credit, assess time/location sensitivity and alarm provenance. |
| UCI | Catalogue attributes CC BY alongside research/noncommercial language. | Obtain a version-specific determination before commercial use, modification or sharing. |
| USGS | Federal source may include third-party exceptions. Local export lacks a complete retrieval record. | Verify query, agency, attribution and release scope for station locations. |
| CrisisMMD | QCRI card names CC BY-NC-SA 4.0; underlying posts and third-party media have separate interests. | Review source terms, attribution, share-alike, handles, recognizable people, locations and redistribution. |
| HumAID | QCRI card metadata names CC BY-NC-SA 4.0 and licensing prose indicates CC BY-NC 4.0. | Obtain written resolution for the captured shards and underlying posts. Restrict identifying personal disclosures. |
| Model 1, pilot and expanded Model 2 | Symbolic project-generated artifacts. Native registry has unverified licence and pending privacy; first-look reviewer records belong in private storage. | Document task scope, weak supervision, reviewer access and approval authority. |

Five acquired sources (SARD, FLAME, WiSARD, CrisisMMD and HumAID) lack entries in the Phase 10A registry. Earlier download-status fields on other entries also predate local acquisition. The Phase 10H manifest records the acquired releases separately and grants no new permissions. Missing terms, version information and permission to redistribute or modify remain unresolved rather than defaulting to permissive. Keep raw posts, usernames, images, location data, private forms and per-record indexes outside Git. Share aggregate results and locally resolvable checksum references.

Publisher evidence and local provenance: [source-by-source acquisition audit](DATASET_ACQUISITION_AUDIT.md), [ESC-50 licence and ledger](https://github.com/karolpiczak/ESC-50/blob/master/LICENSE), [QCRI HumAID card](https://huggingface.co/datasets/QCRI/HumAID-all), [QCRI CrisisMMD card](https://huggingface.co/datasets/QCRI/CrisisMMD), [sensor licence and provenance audit](SENSOR_DATASET_VALIDATION_REPORT.md).

## Phase 10I-A registry addendum

The versioned [registry reconciliation](REGISTRY_RECONCILIATION_REPORT.md)
adds SARD, FLAME, WiSARD, HumAID, and CrisisMMD without changing the
Phase 10A-pinned registry. All 12 indexed public sources are represented in
the new typed snapshot; their licence and verification statuses remain
`unverified`, and privacy remains `pending`. Registration records local
availability only and does not grant training approval.
