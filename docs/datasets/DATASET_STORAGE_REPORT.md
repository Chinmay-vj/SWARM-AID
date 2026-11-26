# D-drive storage and extraction

The preflight measured 456,782,770,176 bytes of capacity and 280,200,896,512 bytes free. The release uses external D-drive output, with an index budget of 1,024 MiB and a free-space reserve of 20,480 MiB. One immutable-source index is staged at a time. A completed stage is renamed on the same volume. The full-decode pass holds at most one worker batch of image arrays in memory and writes only flags and hashes. Peak disk needs are the final indexes plus the largest unpublished stage. No extracted media or spectrogram cache is required.

| Raw source | Files | Bytes |
|---|---:|---:|
| HERIDAL | 1,604 | 4,441,161,162 |
| SARD | 5,760 | 655,254,689 |
| FloodNet | 7,031 | 13,056,205,581 |
| RescueNet | 13,483 | 23,769,513,801 |
| FLAME | 49,995 | 1,593,347,032 |
| WiSARDv1 | 100,794 | 43,571,345,864 |
| ESC-50 | 2,011 | 884,047,129 |
| Smoke Detection IoT | 1 | 5,834,376 |
| UCI CSV and XLSX | 2 | 2,083,262 |
| USGS | 1 | 12,299 |
| HumAID | 3 | 7,223,756 |
| External CrisisMMD snapshot including local downloader metadata | 36,205 | 1,949,568,138 |

The two raw roots contained no standalone ZIP, 7z, RAR, TAR or GZ bundles. Their current extraction requirement is zero bytes. The UCI workbook is a ZIP-based document containing the same hours as its CSV, with different numeric precision. Only the CSV contributes standardized records. FloodNet and RescueNet visualization masks stay in their original directories. The class-index task points directly to the original label masks. The local CrisisMMD staging directory had no files in the inventory. The external snapshot is authoritative for this run.

The Phase 10F field batches account for another 68,739,396 bytes, and the native pilot for 6,385,696 bytes. These frozen inputs are reused by reference. Additional NASA POWER and CrisisNLP releases were outside the inventory. [Actual derived storage and timing](../PHASE_10G_COMPLETION_REPORT.md)
