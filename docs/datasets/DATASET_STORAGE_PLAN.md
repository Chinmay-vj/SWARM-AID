# Storage and capacity

On 2026-11-25, a read-only disk-usage query on D: reported **392,154,832,896 bytes free** of 456,782,770,176 (365.2 GiB free). This is a workspace measurement at inspection time. Candidate archive sizes, expanded sizes and future training artifacts remain unknown until a specific release is verified.

For budgeting, estimate peak bytes as archive + immutable expanded raw + processed derivatives + temporary conversion peak + annotations/manifests + training artifacts + operating reserve. As a planning example only, 10 GiB archives + 20 GiB raw + 15 GiB derivatives + 10 GiB scratch + 1 GiB annotations + 5 GiB artifacts totals 61 GiB before reserve. Measure the actual target volume, quota and backup needs before each approved acquisition. Sharing a source through manifest references avoids replicating it per consumer.

`configs/datasets/storage.json` selects `datasets`, resolving to `D:\SWARM-AID\datasets` when invoked from the project root. The CLI gives the process environment variable `SWARM_DATASET_ROOT` precedence. Acquisition directories supplied for this audit are under `raw/<modality>/<dataset>`. Reference existing files relative to the common root. Creating a layout is a separate operation and does not establish that the downloaded files are present. See the [current storage audit](DATASET_STORAGE_AUDIT.md).

| Release directories | Purpose |
|---|---|
| raw/, licenses/ | Immutable source files and terms; use versioned releases and write access restricted to ingestion. |
| interim/, processed/, annotations/ | Scratch, derived artifacts and label files. Preserve original references and conversion digests. |
| manifests/, metadata/, splits/ | Versioned sample index, provenance and official/grouped assignments. |
| simulation/operational/, simulation/evaluator/ | Separate symbolic histories and truth-derived research outputs. Apply separate access permissions. |
| indexes/rgb, thermal, audio, sensors, paired | Relative references to shared source assets. |
| indexes/model1, indexes/model2, artifacts/ | Consumer indexes and privately stored future artifacts. |

The layout helper creates empty directories only. Dataset media, local manifests, caches and scratch remain under the ignored data root. Commit reviewed, nonprivate manifests/configuration and schemas under configs/datasets/, documentation under docs/datasets/, and tiny generated fixtures in tests. Keep weights and individual-level records out of Git. Raw immutability and directory access controls must be enforced by the chosen storage system.
