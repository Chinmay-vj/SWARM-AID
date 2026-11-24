<#
.SYNOPSIS
  Compatibility entry point (Phase 8). Forwards to scripts\start_system.ps1, which owns service
  startup, readiness checks and process records. See docs/integration/SYSTEM_OPERATIONS.md.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\start_dashboard.ps1
  powershell -ExecutionPolicy Bypass -File scripts\start_dashboard.ps1 -FrontendOnly
#>
param(
    [switch]$FrontendOnly,
    [switch]$BackendOnly
)
& (Join-Path $PSScriptRoot "start_system.ps1") -FrontendOnly:$FrontendOnly -BackendOnly:$BackendOnly
exit $LASTEXITCODE
