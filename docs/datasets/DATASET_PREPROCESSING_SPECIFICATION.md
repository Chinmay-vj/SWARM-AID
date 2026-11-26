# Phase 10G preprocessing specification

The offline runner selects each external raw source first and falls back to the repository's D-drive staging directory. It records the resolved source and processing code hashes in a versioned summary. A review index references immutable source files or table rows. It can represent unresolved grouping, licences and labels without inventing values to satisfy the stricter Phase 10A release contract. Publication for model use still requires the Phase 10A registry, manifests, file checks and independent review.

From the repository root, use Python 3.12 with the datasets extra. On this host the following commands use the embedded launcher with the existing virtual environment and two already-installed D-drive libraries.

```powershell
$py = '.tools/phase10a-check/python.exe'
$root = 'D:/SWARM-AID-DATA'
$env:TEMP = (Resolve-Path .tools).Path
$env:TMP = $env:TEMP
$boot = "import sys,runpy;sys.path.extend(['.tools/paper-libs','.tools/humaid-reader']);runpy.run_module(sys.argv.pop(1),run_name='__main__')"
& $py -c $boot evaluation.data.phase10g --root $root --source USGS
& $py -c $boot evaluation.data.phase10g --root $root --limit-mib 1024 --reserve-mib 20480
foreach ($source in 'HERIDAL','SARD','FloodNet','RescueNet','FLAME','WiSARD') {
    & $py -c $boot evaluation.data.visual_quality --root $root --source $source --workers 3
}
& $py -m evaluation.data.field_review --root $root
& $py -c $boot evaluation.data.phase10g_quality --root $root
& $py -c $boot evaluation.data.crisis_decode --root $root
& $py -m evaluation.data.alert_audit --output runs/phase10g-alert-v2
```

The CrisisMMD decode audit reads each indexed event image, decodes each distinct byte hash once and counts exact matches against the six visual indexes. Its private flags and aggregate summary live under `manifests/phase10g-crisis-decode-v1`. Both this audit and the combined quality export require an unused destination. On resumption, check published digests before deciding which command to run. [Phase 10G results](../PHASE_10G_COMPLETION_REPORT.md)

Each source publishes its index, flagged rows and summary by renaming a completed staging directory. The public indexer compares the source inventory, code, configuration and output checksums when resuming. Supply a fresh version for changed input. The independent review batch and alert audit refuse an occupied destination. For fresh reproduction of the same version, use a separate D-drive release root with the same raw and frozen native inputs. The indexer uses one source at a time. Full visual validation accepts one to four CPU workers. Original bytes, EXIF orientation, COCO coordinates, official partitions and source annotation versions remain available. Derived pixel arrays are transient.

Per-source indexes use filenames relative to the recorded source, line numbers for CSV/TSV, one-based Parquet rows, and content or table digests. Index schema 1.0, source-specific taxonomies and original partition names are retained. Native records use the Phase 10E 1.0 schema and taxonomy. The external summaries include generation time, code SHA-256, Git HEAD and actual output hashes. No learned preprocessing parameters were fitted. The independent quality manifest records label counts and overlap checks. Decode or annotation failures from the supplementary pass appear in its separate flags file. Training approval must reconcile both passes.
