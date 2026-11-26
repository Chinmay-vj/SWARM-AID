# Phase 10I-A raw integrity coverage

## Result

The Phase 10H audit release remains frozen at
`D:\SWARM-AID-DATA\manifests\phase10h-v1\release.json`, SHA-256
`81b0ed436ce8e2bc3ec260f85a87dc89c28f95dc585e3309d8ae3e88c57e11b8`.
Its verification passed after the Phase 10I-A registry update. The frozen
directory was not changed.

The Phase 10I-A read-only hash pass calculated and recorded a SHA-256 digest
for every current file in the 12 indexed source inventories:

| Source | Files | Historical matches | New baselines |
|---|---:|---:|---:|
| CrisisMMD | 36,205 | 19 | 36,186 |
| ESC-50 | 2,011 | 2,002 | 9 |
| FLAME | 49,995 | 49,995 | 0 |
| FloodNet | 7,031 | 2,343 | 4,688 |
| HERIDAL | 1,604 | 1,603 | 1 |
| HumAID | 3 | 3 | 0 |
| RescueNet | 13,483 | 4,494 | 8,989 |
| SARD | 5,760 | 5,758 | 2 |
| Smoke Detection IoT | 1 | 1 | 0 |
| UCI Air Quality CSV | 1 | 1 | 0 |
| USGS Water Data | 1 | 1 | 0 |
| WiSARD | 100,794 | 56,130 | 44,664 |
| **Total indexed sources** | **216,889** | **122,350** | **94,539** |

Phase 10H had historical content-hash references for 122,350 of 216,889
indexed files (56.411344%). The Phase 10I-A artifact now has current
per-file SHA-256 values for all 216,889 indexed files. Of these, 122,350
match historical references; 94,539 have only a newly calculated baseline.
Every source inventory fingerprint matches its Phase 10G fingerprint. There
were zero historical mismatches, historical references missing from the
current inventory, inaccessible files, or files detected changing during
hashing.

The UCI workbook
`D:\SWARM-AID\datasets\raw\sensors\AirQualityUCI.xlsx` is not part of the
indexed UCI CSV source root. It was separately checked against its frozen
Phase 10H SHA-256 reference
`c92d102bb35cd4c0b42c0b6a1336c4065ccdca7069f80a6890ee1b7e3124bd5d`;
the hash matched and ZIP CRC validation passed. Counting this supplementary
workbook, the measured raw inventory is 216,890 files and 89,935,597,089
bytes. The indexed 12-source total is 89,934,298,892 bytes.

## Interpretation and limitations

- A matching historical digest establishes a match to the recorded reference,
  not publisher authenticity or licence.
- A new baseline records the current bytes only. It does not prove that the
  file is unchanged from before the baseline was calculated.
- Zero inaccessible raw files means all files in the 12 configured source
  inventories were readable during this pass. It does not include the separate
  ACL-protected processed pilot directory or inaccessible alert journals.
- No raw file was modified, moved, or regenerated.

## Private audit artifacts

Per-file path, size, status, and digest records are stored outside the
repository at
`D:\SWARM-AID-DATA\manifests\phase10i-a-raw-v1\`. The `summary.json` records
per-source inventory fingerprints and classifications. `checksums.json`
binds the summary and twelve JSONL detail files to the frozen Phase 10H release
SHA-256. Its SHA-256 is
`9cbf71b49af7c6e020fd2de8770a4358cb5c59b5388a41e021cf4cb23f739b88`.

The Phase 10H audit evidence remains historical and unmodified. See the
[final dataset integrity audit](FINAL_DATASET_INTEGRITY_AUDIT.md) and the
[Phase 10I-A completion report](../PHASE_10I_A_COMPLETION_REPORT.md).
