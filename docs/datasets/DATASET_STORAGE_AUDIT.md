# Storage audit | 25 November 2026

## Corrected root for the sensor inventory

A subsequent owner correction established `D:\SWARM-AID\datasets` as the actual root. The earlier external-path audit and drive measurement below are historical. The sensor holdings alone measure 7,929,937 bytes. [Phase 10D sensor inventory](SENSOR_DATASET_VALIDATION_REPORT.md)

| D: measurement | Bytes | Decimal GB |
|---|---:|---:|
| Total capacity | 456,782,770,176 | 456.78 |
| Available to this host account | 282,598,920,192 | 282.60 |
| Capacity less available | 174,183,849,984 | 174.18 |
| Headroom above the requested 95 GB reserve | 187,598,920,192 | 187.60 |

Windows DriveInfo supplied the capacity and available-space figures during the read-only host check. Headroom is a shared ceiling for all additional raw data, extraction, derivatives and training artifacts. The current seven-dataset total, per-folder and per-archive sizes, expanded sizes and duplicate storage are **unmeasured**. The volume-wide used figure includes unrelated files. A change since the Phase 10A measurement cannot be attributed to these downloads.

| Dataset | Downloaded bytes | Expanded bytes | Additional temporary bytes | Local image or audio count |
|---|---:|---:|---:|---:|
| HERIDAL | Unknown | Unknown | Unknown | Unknown |
| SARD | Unknown | Unknown | Unknown | Unknown |
| FloodNet | Unknown | Unknown | Unknown | Unknown |
| RescueNet | Unknown | Unknown | Unknown | Unknown |
| FLAME | Unknown | Unknown | Unknown | Unknown |
| WiSARD | Unknown | Unknown | Unknown | Unknown |
| ESC-50 | Unknown | Unknown | Unknown | Unknown |

Before inspection, `configs/datasets/storage.json` resolved to `D:\SWARM-AID\datasets` from the repository root. The process had no `SWARM_DATASET_ROOT` override. The audit corrected the configured root to `D:/SWARM-AID-DATA`. The read-only CLI validates its syntax without requiring the directory to exist. Its schema and path precedence are unchanged. The external root could not be enumerated independently of configuration.

For the approximate 160 GB raw budget, first measure existing archives and expanded raw payloads once, then subtract their total from 160 GB. Remaining room for future datasets is the smaller of raw-budget headroom and volume headroom after planned processing. With an illustrative **additional** 160 GB allocation the current drive would have 27.60 GB available above reserve for all other work. Actual training/preprocessing space depends on current holdings and job sizes; a numeric allocation is premature. All budgets here use decimal GB.

When accessible, sum physical files across the seven roots, separately record archives, extracted files, hard-link aliases and logical member sizes. Count overlapping archive contents as potential duplicates until exact matches are verified. Report already extracted bytes separately from incremental bytes needed. Empty optional directories remain pending. Recheck free bytes immediately before any proposed extraction.
