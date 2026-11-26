# Generate and verify a symbolic pilot

From D:\SWARM-AID, use the repository's Windows Python 3.12 environment. Set the Phase 10A storage override for this PowerShell session to select the external pilot. The embedded interpreter below uses the existing environment's packages.

```powershell
$env:SWARM_DATASET_ROOT = 'D:\SWARM-AID-DATA'
.tools\phase10a-check\python.exe -m evaluation.data.model2 validate --version pilot-2
.tools\phase10a-check\python.exe -m evaluation.data.model2 generate --plan configs/datasets/model2_pilot.json --version pilot-reproduction
```

Use an unused version name. For a complete replay including the versioned manifest, use a fresh D:-drive root and the original version. The following PowerShell commands compare the payload maps of the regenerated and released datasets. The generator refuses to overwrite an existing release.

```powershell
$releasedRoot = 'D:\SWARM-AID-DATA'
$env:SWARM_DATASET_ROOT = Join-Path $releasedRoot ('interim\model2\replay-' + [guid]::NewGuid())
.tools\phase10a-check\python.exe -m evaluation.data.model2 generate --plan configs/datasets/model2_pilot.json --version pilot-2
if ($LASTEXITCODE -ne 0) { throw 'Replay generation failed' }
.tools\phase10a-check\python.exe -c "import json,sys; from pathlib import Path; a,b=(json.loads((Path(p)/'processed/model2/pilot-2/release.json').read_bytes())['files'] for p in sys.argv[1:]); print('Matching payload maps:', a == b); sys.exit(a != b)" $releasedRoot $env:SWARM_DATASET_ROOT
$env:SWARM_DATASET_ROOT = $releasedRoot
```

Changing the version changes the dataset manifest and registry. The creation timestamp, working-tree status and software hashes live outside the deterministic payload map.

The plan sets fleet size, registered fixture, seed, partition and a maximum of 40 native inputs per episode. Use one split per scenario across seeds because the engine derives the mission UUID from the scenario. Sampling cycles through strata defined by finding type, inferred relationship, weak assessment, urgency and freshness. This enriches rare conditions; frequencies do not estimate their natural prevalence. Fault scenarios exercise delay, endpoint outage, missing modalities and noise through the existing Fleet and simulator. Controlled variants are derived from retained parents; reconstruction checks their inputs. Only the zero-person routine fixture supports the controlled spurious-sighting reference.

Each release in processed/model2 contains complete source envelopes and normalized receipt files, inputs, predictive feature projection, separate targets and evaluator reference, plan, Phase 10A registry/manifest, pending review forms, statistics and release metadata. Failed final validation preserves the staged directory in interim/model2/quarantine with the error. Do not use a quarantined or interrupted build as a release. Reviewer exports live separately. Original public assets are referenced only after source review; this pilot contains no public media. [Plan](../../configs/datasets/model2_pilot.json)
