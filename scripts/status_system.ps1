<#
.SYNOPSIS
  Report SWARM-AID status: managed processes, backend health, database, active missions,
  Model 2 and communication state, dashboard and event-stream endpoint. Read-only.
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$control = Join-Path $root "runs\system"

Write-Host "Managed processes (started by start_system.ps1):"
$any = $false
foreach ($name in "backend", "frontend") {
    $file = Join-Path $control "$name.process.json"
    if (-not (Test-Path $file)) { continue }
    $record = Get-Content $file -Raw | ConvertFrom-Json
    $process = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
    $alive = $process -and $process.StartTime.ToUniversalTime().ToString("o") -eq $record.start_time
    $state = if ($alive) { "running" } else { "not running (stale record)" }
    Write-Host ("  {0,-9} PID {1,-7} {2,-26} {3}" -f $name, $record.pid, $state, $record.url)
    $any = $true
}
if (-not $any) { Write-Host "  none" }
Write-Host ""

if (-not (Test-Path $python)) { Write-Host "Python virtual environment not found; cannot query backend status."; exit 1 }
Push-Location $root
try {
    & $python -m orchestration status
    exit $LASTEXITCODE
} finally { Pop-Location }
