# Phase 10E pilot coverage and leakage validation

The addendum uses the 510 validated examples in `processed/model2/pilot-2`. It adds disjoint, one-based JSONL indices for 505 native command receipts and five controlled presentations. Each index joins to the frozen input line and sample ID. All 1,138 original source reports remain available in the episode ledgers. Baseline predictions and unresolved targets stay in `targets.jsonl`, the controlled reference in `evaluator.json`, and independent reviews in the revision ledger. The two public sources have separate context manifests. All new files live in `D:\SWARM-AID-DATA\manifests\model2\pilot-2-addendum-1`. Its six files total 64,912 bytes alongside the 6,385,696-byte pilot.

## Category coverage

Eligible counts may overlap. Primary counts assign each presentation to exactly one sampling category. In frozen input order, choose the first eligible category still below its goal in the precedence order below. Once all eligible goals are full, use the first eligible category. This describes the existing pilot and preserves every row. These categories are sampling metadata. They do not supply independent training labels.

| Sampling condition in precedence order | Proposed | Eligible | Primary | In review batch |
|---|---:|---:|---:|---:|
| Controlled false alarm | 40 | 1 | 1 | 1 |
| Conflicting evidence | 50 | 1 | 1 | 1 |
| Duplicate or forwarded evidence | 50 | 2 | 2 | 2 |
| Report in transit at a configured command outage tick | 30 | 11 | 11 | 6 |
| Multiple unrelated incidents in one presentation | 30 | 0 | 0 | 0 |
| Missing information | 50 | 40 | 40 | 6 |
| Stale observation | 30 | 37 | 37 | 6 |
| Possible rescue incident | 70 | 68 | 64 | 7 |
| Independent multi-agent observation proxy | 80 | 170 | 124 | 7 |
| Routine observation | 70 | 157 | 97 | 7 |
| Other, including hazards without another qualifying condition | — | 133 | 133 | 7 |
| **Distinct presentations** | **500** | **510** | **510** | **50** |

The false alarm has a deterministic zero-person reference. The conflict, repeat and relay cases are controlled. The fifth controlled case is stale. Missing information counts disabled modalities or explicit target gaps. The 11 outage cases intersect the configured downtime between send and receipt. The journal contains delivered reports, so packet loss or a causal delay cannot be inferred per report. A possible rescue case requires a weak possible-human or uncertain-need assessment. Corroboration requires compatible reports with disjoint evidence origins. Independence remains a proxy. The primary distribution reflects limited source diversity.

## Scenario coverage

| Implemented family | Pilot episodes | Examples |
|---|---:|---:|
| Flood, including command and network fixtures | 9 | 350 |
| Wildfire | 1 | 40 |
| Earthquake | 1 | 40 |
| Cyclone | 1 | 40 |
| Landslide | 1 | 40 |
| Dedicated missing-person search | 0 | 0 |

Cyclone and landslide reuse existing dynamics. The pilot has 70 baseline incident IDs, but each decision context is local to one cell and lacks an independently established target for unrelated concurrent incidents. A dedicated missing-person search, independent multi-incident references, more natural conflicts and report-specific interruption outcomes are requirements for future simulator design review. [Episode plan](../../configs/datasets/model2_pilot.json)

## Validation and manual review

Native validation checked source journal identity, temporal context, feature projection, parent transformations and split consistency. The counts are 234 train, 80 validation and 196 test. Seeds 42–46 occur only in test. The addendum adds zero learning rows or split assignments. All five derived payloads matched a second construction byte for byte. Thirty-eight simplified native context patterns recur across splits. The public overlap screens flagged four shared texts across HumAID splits and 220 HumAID rows with shared passages in CrisisMMD. Public benchmark independence remains unverified. [Native limitations](MODEL2_DATASET_LIMITATIONS.md) · [HumAID inspection](HUMAID_COMPATIBILITY_REPORT.md) · [CrisisMMD inspection](CRISISMMD_COMPATIBILITY_REPORT.md)

The first review batch retains the original 18 forms, then selects by least represented primary category, least represented episode and sample UUID. It includes all 13 episodes and all five controlled cases. All 50 forms are pending and contain no assigned judgments. Use this queue with the existing annotation CLI. [Reviewer instructions](MODEL2_HUMAN_REVIEW_GUIDE.md)

## Reproduction from the repository root

The base generation and full replay commands are in the [pilot generation guide](MODEL2_DATASET_GENERATION.md). For this checkout the Python 3.12 interpreter loads the existing environment's packages. DuckDB 1.4.2, the optional datasets extra, was installed into `.tools/humaid-reader`. These commands validate the base, rebuild the addendum into a fresh external directory and reproduce the shared-passage screen. With a standard environment containing the datasets extra, the equivalent module invocations use `python -m evaluation.data.model2_addendum` and `python -m evaluation.data.humaid`.

```powershell
$env:SWARM_DATASET_ROOT = 'D:\SWARM-AID-DATA'
$source = 'D:\SWARM-AID\datasets\raw\model2\HumAID'
$crisis = Join-Path $env:SWARM_DATASET_ROOT 'raw\multimodal\CrisisMMD'
$out = Join-Path $env:SWARM_DATASET_ROOT ('manifests\model2\replay-' + [guid]::NewGuid())
.tools\phase10a-check\python.exe -m evaluation.data.model2 validate --version pilot-2
.tools\phase10a-check\python.exe -c "import sys,runpy; sys.path.insert(0,'.tools/humaid-reader'); runpy.run_module('evaluation.data.model2_addendum',run_name='__main__')" --root $env:SWARM_DATASET_ROOT --humaid $source --output $out
.tools\phase10a-check\python.exe -c "import sys,runpy; sys.path.insert(0,'.tools/humaid-reader'); runpy.run_module('evaluation.data.humaid',run_name='__main__')" --humaid $source --crisis $crisis
```
