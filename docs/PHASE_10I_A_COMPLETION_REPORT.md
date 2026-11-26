# Phase 10I-A completion report

**Status: automated Phase 10I-A work complete; human and access blockers remain.**
**Overall training decision: NO-GO.** This report closes Phase 10I-A only. It
does not authorize Phase 10I-B, Phase 11, data release, or model training.

## Registry reconciliation

The five indexed public sources missing from the original Phase 10A registry
were **SARD, FLAME, WiSARD, HumAID, and CrisisMMD**. They have been added to
the additive typed snapshot
`configs/datasets/registry.phase10i-v1.json`. The snapshot retains all 14
original registry entries, contains 19 entries total, and marks all 12
indexed public sources locally available. The original registry and frozen
Phase 10H evidence were not overwritten.

No training approval was granted. For every indexed public source, licence
and verification remain `unverified`, and privacy remains `pending`. Split
and integrity details that do not exist in the Phase 10A Pydantic contract
remain in the reconciliation report rather than being added as schema-breaking
properties. See the [registry reconciliation report](datasets/REGISTRY_RECONCILIATION_REPORT.md)
for each source's version evidence, provenance, path, modalities, annotation
formats, task candidates, metadata, split risks, and integrity status.

## Frozen release and raw integrity

The Phase 10H release
`D:\SWARM-AID-DATA\manifests\phase10h-v1\release.json` was verified after the
registry update. Its SHA-256 remains
`81b0ed436ce8e2bc3ec260f85a87dc89c28f95dc585e3309d8ae3e88c57e11b8`; the
historical release directory was not altered.

The Phase 10H raw audit had historical content-hash references for 122,350
of 216,889 indexed files (56.411344%). The Phase 10I-A pass recorded a current
SHA-256 for all 216,889 indexed files:

- 122,350 match historical references.
- 94,539 are newly calculated baselines without historical references.
- Zero historical mismatches, missing reference files, inaccessible files,
  or changes during hashing.
- All 12 source inventory fingerprints match Phase 10G.

The UCI workbook is a separate supplementary file; its current SHA-256
matches the frozen Phase 10H reference and ZIP CRC validation passed. Including
it, current raw coverage is 216,890 files / 89,935,597,089 bytes. New hashes
are baselines and do not establish historical integrity. Full details and
per-source counts are in the [raw integrity coverage report](datasets/RAW_INTEGRITY_COVERAGE_REPORT.md);
hash records and their checksum binding remain on D: at
`D:\SWARM-AID-DATA\manifests\phase10i-a-raw-v1\`.

## Access diagnosis and storage

The current process is `MSI\Local User`, at medium integrity. The
Administrators group is deny-only; the process is not elevated. These
directories exist but their ACLs, owners, and contents cannot be read:

- `D:\SWARM-AID\datasets\processed\model2\pilot-1`
- `D:\SWARM-AID\runs\phase10g-alert-v2`
- `D:\SWARM-AID\runs\phase10h-alert-v1`

Readable parents are owned by `MSI\CodexSandboxOffline`. Windows returns
access denied for child ACL queries and directory listing. This confirms
effective denial for the current process, but the available evidence cannot
distinguish a child DACL from a host-level access boundary. The 44 alert-case
lineage was not rerun. Contents and size of the protected pilot directory
remain unknown; alert-file existence within the inaccessible directories is
indeterminate. A separate `D:\SWARM-AID\runs\pytest\cache` directory also
exists but is unreadable, so that repository-run storage measurement is
partial; no access change or deletion was attempted.

Measured storage:

| Category | Measured result |
|---|---:|
| Raw/extracted source trees, including supplementary UCI workbook | 216,890 files / 89,935,597,089 bytes |
| External processed datasets | 348 files / 191,090,593 bytes |
| Repository processed datasets | Partial; blocked at `D:\SWARM-AID\datasets\processed\model2\pilot-1` |
| Repository staging (`indexes`, `interim`, `artifacts`, `manifests`, `splits`) | 0 files / 0 bytes |
| External native simulation releases | 13 files / 3,463,652 bytes |
| External annotation artifacts | 2 files / 433,295 bytes |
| Phase 10I-A temporary directory | 0 files / 0 bytes at measurement |
| Phase 10I-A per-file hash artifacts | 14 files / 41,358,785 bytes |
| D-drive validation caches | 182 files / 36,243,264 bytes |
| Local HF cache | 5 files / 178,819,525 bytes |
| D: free space at the final post-validation measurement | 279,926,063,104 bytes (260.70 GiB) |

Repository-local annotations and simulation directories were empty when
measured. The release manifest retains its Phase 10H storage snapshot as
historical evidence; the current storage measurement does not rewrite it.

## Final verification

| Check | Result |
|---|---|
| `python -m pip check` | Passed; no broken requirements. |
| `python -m pytest -q -o cache_dir=D:\SWARM-AID-DATA\phase10i-a\pytest-cache` | **278 passed, 1 skipped, 3 warnings** in 274.32 seconds. |
| `python -m ruff check .` | Passed. |
| `python -m mypy --cache-dir D:\SWARM-AID-DATA\phase10i-a\mypy-cache` | Passed; no issues in 159 source files. |
| `python -m evaluation.data.final_release --root D:\SWARM-AID-DATA --verify` | Passed; frozen Phase 10H release unchanged. |

The skipped test is
`tests/backend_api/test_exports_health_geo.py::test_postgis_migration_geometry_and_spatial_query`;
it requires `SWARM_TEST_POSTGRES_URL` and PostgreSQL/PostGIS, which were not
configured. The three warnings are the existing Starlette/httpx test-client
deprecation and two PettingZoo environment-API deprecations. Test, linter,
type-checker, and temporary paths were directed to D:; the repository's
inaccessible `runs\pytest\cache` was not altered.

## Native safeguards and training approval

The native audit matched its saved checkpoint: 259 reused evidence IDs cross
partitions, 251 are shared with test, and the episode-level overlay excludes
all 13 affected pilot episodes from eligible pooled comparisons. Expanded
field releases have zero evidence-ID overlap with the pilot. Seeds 42, 43,
44, 45, and 46 remain test-only; the development loader rejects protected
mixed releases. No protected evaluation record was edited.

The training path calls collection-wide validation with file verification.
It checks exact registered dataset/version and origin, complete licence,
privacy and verification governance, checksums, content/pair/group/split
constraints, and restricts training batches to operational training rows.
Reserved seeds are rejected by the training guard. Tests cover pending
governance, invalid checksums, cross-split groups, protected seeds, and unknown
dataset versions. Review loaders remain inspection/pipeline-development
paths, not fitting paths. The current contracts do not contain a separate
human-signed release approval or signature field; this is not represented as
verified. No safeguard was weakened.

The final readiness matrix remains **20 BLOCKED learning tasks, zero approved
records**. Review-only pipeline work does not change task readiness or the
NO-GO decision.

## Human review and Phase 10I-B handoff

The 100-example blinded annotation queue remains pending, with zero
submissions or adjudications. The 44 priority same-cell reports remain
unreviewed independently; no human presence was classified as confirmed
distress and no assessment was fabricated.

The machine-readable corrective inventory
`configs/datasets/phase10i_b_tasks.json` contains ten tasks, all
`NOT_STARTED`, with training approval and large-scale split reconstruction
disabled. The [human-readable inventory](datasets/PHASE_10I_CORRECTIVE_TASKS.md)
covers parent-flight/site identity and empty annotations; FLAME near-test
frames and unpaired masks; FloodNet/RescueNet site-event groups; WiSARD flags
and pairing; ESC-50 cross-fold recordings; HumAID cross-partition text;
CrisisMMD repeated events/media; Smoke/USGS missing split assignments; and
sensor horizons, units, and overlapping windows. Existing possible source
metadata and missing identifiers are documented without inventing capture,
flight, event, site, or recording IDs.

**Phase 10I-B is handed off for review only and has not started. Phase 11 has
not started. No training was run.**

## Authorized owner actions

An authorized data owner must either provide read-only list/read/execute
access for the current identity only to the following directories, or place
read-only copies of the required audit files in an already-authorized D-drive
review location:

1. `D:\SWARM-AID\datasets\processed\model2\pilot-1`
2. `D:\SWARM-AID\runs\phase10g-alert-v2`
3. `D:\SWARM-AID\runs\phase10h-alert-v1`

Grant only the narrow read/list/execute access required by policy. Do not
grant Modify or Full Control, change parent ACLs, take ownership, or elevate
the audit process. After authorization, rerun the pilot storage/exclusion
check and existing alert-journal verification while preserving the review
queue. Rights/privacy decisions and independent annotations require their
respective authorized human owners. No user action is required to begin
Phase 10I-B; it must remain NOT_STARTED pending review and explicit
authorization.

See the [file-access blocker report](datasets/FILE_ACCESS_BLOCKER_REPORT.md),
[Phase 10I corrective inventory](datasets/PHASE_10I_CORRECTIVE_TASKS.md),
[final readiness matrix](datasets/TRAINING_READINESS_MATRIX.md), and
[Phase 11 handoff](PHASE_11_HANDOFF.md).
