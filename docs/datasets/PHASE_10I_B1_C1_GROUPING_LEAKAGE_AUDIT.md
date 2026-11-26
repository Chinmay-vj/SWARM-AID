# Phase 10I-B1/C1 grouping and leakage audit

This audit prepares exclusion candidates and records grouping gaps. It does
not approve a split, certify independent generalization, or expose held-out
records for training.

## Image/video sources

### FLAME

The frozen Phase 10G visual summary covers 49,995 indexed frames and reports
491 training frames near at least one official test frame. Recalculation found
4,419 train/test near-pair matches: 3,213 at Hamming distance 3, 819 at 2,
261 at 1, and 126 at 0. The exclusion overlay removes all 491 distinct
training paths involved. No exact image-content hash groups cross official
train and test. The official test class distribution is unchanged.

The visual audit and this recomputation agree. The near-frame rule is a
conservative exclusion, not a substitute for parent-video grouping; no
verified parent video/capture field is available. The 2,003 segmentation
masks remain unpaired and are not matched by filename similarity.

### HERIDAL and SARD

The available split is the exported train/validation/test assignment, but the
index lacks parent flight/site identifiers. SARD's local metadata describes a
3x3-tile export, so tile-level split separation cannot be treated as
flight-level independence. Empty annotations are not converted to negative
examples absent source policy.

### FloodNet and RescueNet

Index-based image/mask paths are verified and decoded class-pixel totals
match the frozen Phase 10G summaries (2,343 and 4,494 masks, respectively).
Publisher event descriptions identify Hurricane Harvey for FloodNet and
Hurricane Michael for RescueNet. Site/capture groups are not present, so
publisher partitions alone do not establish site-disjoint evaluation.

### WiSARD

The index has zero verified RGB/thermal pairs. The 1,275 flagged records and
11,542 missing sidecars remain unresolved. No synchronization, registration,
calibration, or capture identity is inferred.

## Audio

ESC-50 recording IDs `131943`, `134049`, `209698`, and `234879` cross
publisher folds 2/3 or 4/5. All nine clips from these four recording groups
are excluded from the candidate. The remaining 1,991 clips preserve their
original folds. This does not resolve clip-level terms or convert generic
environmental sound categories into distress labels.

## Sensor sources

- **Smoke:** five counter runs reduce to three identical sensor-signature
  groups (`1`/`2` and `4`/`5` repeat). The draft grouping leaves all 62,630
  rows unassigned; no candidate split is emitted.
- **UCI:** 9,357 timestamp rows support a 24-hour lookback and one-hour-ahead
  `CO(GT)` candidate in mg/m3. The chronological day split yields 7,603
  windows. There are 23 insufficient-lookback and 48 partition-boundary
  purges, 1,683 rows with missing target values, and zero raw-row overlap
  between partitions. This is temporal-only and represents one site.
- **USGS:** 36 interval summaries for one station have 152 overlapping
  interval pairs. These are not treated as a continuous series; no split is
  emitted.

No missing site, event, flight, video, run, or recording identifier has been
invented. Machine-readable details and exclusion paths are in the D-drive
release at `D:\SWARM-AID-DATA\manifests\phase10i-b1-c1-v1`.
