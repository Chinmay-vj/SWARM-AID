<#
.SYNOPSIS
  Start the SWARM-AID backend (127.0.0.1:8000) and the Phase 8 dashboard (127.0.0.1:5173).

.DESCRIPTION
  Checks prerequisites, applies migrations, avoids starting a second copy of a service that is
  already listening, and starts each service in its own window. Secrets are never printed.
  Simulation research only: no physical drone control.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\start_dashboard.ps1
  powershell -ExecutionPolicy Bypass -File scripts\start_dashboard.ps1 -FrontendOnly
#>
param(
    [switch]$FrontendOnly,
    [switch]$BackendOnly
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$frontend = Join-Path $root "frontend"

function Test-Port([int]$Port) {
    $conn = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $conn
}

function Fail([string]$Message) {
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}

if (-not $FrontendOnly) {
    if (-not (Test-Path $python)) { Fail "Python virtual environment not found at .venv. Run: py -3.12 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e "".[dev,simulation,backend]""" }
    $envFile = Join-Path $root ".env"
    if (-not (Test-Path $envFile) -and -not $env:SWARM_JWT_SECRET) {
        Fail "No .env and no SWARM_JWT_SECRET. Copy .env.example to .env and set SWARM_JWT_SECRET (>= 32 characters)."
    }
    if (Test-Path $envFile) {
        $secretLine = Select-String -Path $envFile -Pattern '^\s*SWARM_JWT_SECRET\s*=\s*(.+)$' | Select-Object -First 1
        if (-not $secretLine -or $secretLine.Matches[0].Groups[1].Value.Trim().Length -lt 32 -or $secretLine.Line -match 'replace-with') {
            Fail "SWARM_JWT_SECRET in .env is missing, a placeholder, or shorter than 32 characters."
        }
    }
    if (Test-Port 8000) {
        Write-Host "Backend already listening on 127.0.0.1:8000; not starting another." -ForegroundColor Yellow
    } else {
        Push-Location $root
        try {
            & $python -m alembic upgrade head
            if ($LASTEXITCODE -ne 0) { Fail "Database migration failed (see output above)." }
        } finally { Pop-Location }
        Start-Process -FilePath $python -ArgumentList @("-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000") -WorkingDirectory $root -WindowStyle Normal
        Write-Host "Backend starting on http://127.0.0.1:8000" -ForegroundColor Green
    }
}

if (-not $BackendOnly) {
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Fail "Node.js 20+ is required (https://nodejs.org)." }
    if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
        Push-Location $frontend
        try {
            npm ci --no-audit --no-fund
            if ($LASTEXITCODE -ne 0) { Fail "npm ci failed." }
        } finally { Pop-Location }
    }
    if (Test-Port 5173) {
        Write-Host "Dashboard already listening on 127.0.0.1:5173; not starting another." -ForegroundColor Yellow
    } else {
        Start-Process -FilePath "cmd.exe" -ArgumentList @("/c", "npm run dev") -WorkingDirectory $frontend -WindowStyle Normal
        Write-Host "Dashboard starting on http://127.0.0.1:5173" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Dashboard:  http://127.0.0.1:5173"
Write-Host "Backend:    http://127.0.0.1:8000"
Write-Host "API docs:   http://127.0.0.1:8000/docs"
Write-Host "First administrator: .\.venv\Scripts\python.exe -m backend.cli create-user --username admin --role administrator"
