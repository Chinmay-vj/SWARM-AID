param([Parameter(Mandatory)][string]$Destination, [switch]$IncludeOptional,
      [string]$Manifest = 'D:\SWARM-AID-DATA\runs\phase11j\migration_manifest.json')
# Copies the manifest's files to <Destination>\repo and \data and verifies every SHA256.
# Dataset licences restrict redistribution: use owner-controlled media only.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$m = Get-Content $Manifest -Raw -Encoding UTF8 | ConvertFrom-Json
$roots = @{ repo = $repo; data = 'D:\SWARM-AID-DATA' }
$files = @($m.files | Where-Object { $_.essential -or $IncludeOptional })
$failed = @()
foreach ($f in $files) {
    $source = Join-Path $roots[$f.root] $f.path
    $target = Join-Path (Join-Path $Destination $f.root) $f.path
    try {
        New-Item -ItemType Directory -Force (Split-Path -Parent $target) | Out-Null
        Copy-Item -LiteralPath $source -Destination $target -Force
        if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $f.sha256) { $failed += $f.path }
    } catch { $failed += "$($f.path): $($_.Exception.Message)" }
}
Copy-Item -LiteralPath $Manifest -Destination (Join-Path $Destination 'migration_manifest.json') -Force
$result = [ordered]@{ verified_at = (Get-Date -Format o); files = $files.Count
    failed = $failed; optional_included = [bool]$IncludeOptional }
$result | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $Destination 'migration_verification.json')
if ($failed.Count) { Write-Output "FAILED $($failed.Count) of $($files.Count):"; $failed; exit 1 }
Write-Output "VERIFIED $($files.Count) files at $Destination"
