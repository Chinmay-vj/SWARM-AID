<#
.SYNOPSIS
  Start SWARM-AID: validate configuration, migrate, start the backend and the dashboard.

.DESCRIPTION
  Profiles:
    (default)   connected development system: backend (127.0.0.1:8000) + dashboard (127.0.0.1:5173)
    -BackendOnly  backend only
    -FrontendOnly dashboard only (expects a backend on 127.0.0.1:8000)
    -Headless     no services: one integrated headless mission (simulator, Model 1, transport,
                  coordination, Model 2) printed as JSON. Use -Scenario, -Agents, -Seed.

  Safety:
    - Never prints secrets. Never installs Docker, PostgreSQL or npm packages.
    - Never terminates a process it did not start. If a port is occupied by something else, it
      reports it and leaves it alone.
    - Services bind to 127.0.0.1. Processes started here are recorded in runs\system\*.process.json
      so stop_system.ps1 stops only those.
  Simulation research only: there is no physical drone control.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\start_system.ps1
  powershell -ExecutionPolicy Bypass -File scripts\start_system.ps1 -Headless -Scenario wildfire_basic -Agents 10
#>
param(
    [switch]$Headless,
    [switch]$BackendOnly,
    [switch]$FrontendOnly,
    [string]$Scenario = "flood_basic",
    [int]$Agents = 6,
    [int]$Seed = -1,
    [int]$ReadyTimeoutSeconds = 60
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$frontend = Join-Path $root "frontend"
$control = Join-Path $root "runs\system"
$backendPort = 8000
$frontendPort = 5173

function Fail([string]$Message) {
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}
function Info([string]$Message) { Write-Host $Message -ForegroundColor Cyan }
function Ok([string]$Message) { Write-Host $Message -ForegroundColor Green }
function Warn([string]$Message) { Write-Host $Message -ForegroundColor Yellow }

function Get-Listener([int]$Port) {
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
}

function Read-Owned([string]$Name) {
    $file = Join-Path $control "$Name.process.json"
    if (-not (Test-Path $file)) { return $null }
    $record = Get-Content $file -Raw | ConvertFrom-Json
    $process = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
    if ($null -eq $process -or $process.StartTime.ToUniversalTime().ToString("o") -ne $record.start_time) {
        Remove-Item $file -Force
        return $null
    }
    return $record
}

function Write-Owned([string]$Name, $Process, [string]$Url, [string]$Log) {
    $Process.Refresh()
    $record = [ordered]@{
        name       = $Name
        pid        = $Process.Id
        start_time = $Process.StartTime.ToUniversalTime().ToString("o")
        url        = $Url
        log        = $Log
    }
    $record | ConvertTo-Json | Set-Content -Path (Join-Path $control "$Name.process.json") -Encoding utf8
}

function Rotate-Log([string]$Path) {
    # Keep the current and one previous log per stream so logs do not grow without bound.
    if (Test-Path $Path) { Move-Item -Force $Path "$Path.1" }
}

function Wait-Http([string]$Url, $Process, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if ($Process.HasExited) { return $false }
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) { return $true }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

# ---- 1. prerequisites ---------------------------------------------------------------------
if (-not (Test-Path $python)) {
    Fail "Python virtual environment not found at .venv. Create it with Python 3.12: py -3.12 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e "".[dev,simulation,backend]"""
}
$pyVersion = & $python -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ($pyVersion -notin @("3.11", "3.12")) { Fail "Python $pyVersion found in .venv; 3.11 or 3.12 is required." }
Info "Python $pyVersion (.venv)"

New-Item -ItemType Directory -Force -Path $control | Out-Null
Push-Location $root
try {
    # ---- headless profile -----------------------------------------------------------------
    if ($Headless) {
        if ($Seed -lt 0) { Fail "Pass -Seed explicitly (development seeds are 12000-12999)." }
        & $python -m orchestration check --profile headless
        if ($LASTEXITCODE -ne 0) { Fail "Configuration check failed (see above)." }
        & $python -m orchestration run --scenario $Scenario --agents $Agents --seed $Seed --output (Join-Path $root "runs\phase9\headless")
        if ($LASTEXITCODE -ne 0) { Fail "Headless mission failed." }
        Ok "Headless mission completed. Results are under runs\phase9\headless."
        exit 0
    }

    if (-not $BackendOnly) {
        $node = Get-Command node -ErrorAction SilentlyContinue
        if (-not $node) { Fail "Node.js 20 or newer is required for the dashboard (or use -BackendOnly)." }
        $nodeMajor = [int]((& node --version).TrimStart("v").Split(".")[0])
        if ($nodeMajor -lt 20) { Fail "Node.js $nodeMajor found; 20 or newer is required." }
        Info "Node.js $(& node --version)"
        if (-not (Test-Path (Join-Path $frontend "node_modules\vite\bin\vite.js"))) {
            Fail "Dashboard dependencies are not installed. Run once: cd frontend; npm ci"
        }
    }

    # ---- 2. configuration -----------------------------------------------------------------
    $profileName = if ($BackendOnly -or $FrontendOnly) { "connected" } else { "development" }
    & $python -m orchestration check --profile $profileName | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Warn "Fix the errors above. A first-time setup needs .env (copy .env.example, set SWARM_JWT_SECRET >= 32 characters) and: .\.venv\Scripts\python.exe -m alembic upgrade head"
        # Migration is the one error this script can fix itself; re-check after it.
        & $python -m alembic upgrade head | Out-Host
        if ($LASTEXITCODE -ne 0) { Fail "Database migration failed." }
        & $python -m orchestration check --profile $profileName | Out-Null
        if ($LASTEXITCODE -ne 0) { Fail "Configuration check still fails after migration." }
    }

    # ---- 3. backend -----------------------------------------------------------------------
    $backendUrl = "http://127.0.0.1:$backendPort"
    $ownedBackend = Read-Owned "backend"
    $listener = Get-Listener $backendPort
    if ($FrontendOnly) {
        if (-not $listener) { Warn "No backend is listening on port $backendPort; connected mode will show the backend as unreachable." }
    } elseif ($ownedBackend) {
        Warn "Backend already running (started by this script, PID $($ownedBackend.pid)); not starting another."
    } elseif ($listener) {
        try {
            $live = Invoke-WebRequest -Uri "$backendUrl/health/live" -UseBasicParsing -TimeoutSec 2
            Warn "A backend not started by this script is already listening on port $backendPort (PID $($listener.OwningProcess)). Using it; stop_system.ps1 will not stop it."
        } catch {
            Fail "Port $backendPort is used by another program (PID $($listener.OwningProcess)). It was left running. Free the port or stop that program."
        }
    } else {
        & $python -m alembic upgrade head | Out-Host
        if ($LASTEXITCODE -ne 0) { Fail "Database migration failed." }
        # Started without PowerShell redirection: redirected children inherit this console's
        # handles, so piping or redirecting this script's output would block until the
        # services exit. The server writes its own log (current + one previous copy).
        $log = Join-Path $control "backend.log"
        Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $control "backend.stop")
        $process = Start-Process -FilePath $python -ArgumentList @("-m", "orchestration", "serve", "--log", "`"$log`"") -WorkingDirectory $root -WindowStyle Hidden -PassThru
        if (-not (Wait-Http "$backendUrl/health/ready" $process $ReadyTimeoutSeconds)) {
            Get-Content $log -Tail 20 -ErrorAction SilentlyContinue | Out-Host
            if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
            Fail "Backend did not become ready within $ReadyTimeoutSeconds s (log: runs\system\backend.log)."
        }
        Write-Owned "backend" $process $backendUrl $log
        Ok "Backend ready on $backendUrl (PID $($process.Id))"
    }

    # ---- 4. dashboard ---------------------------------------------------------------------
    $dashboardUrl = "http://127.0.0.1:$frontendPort"
    if (-not $BackendOnly) {
        $ownedFrontend = Read-Owned "frontend"
        $listener = Get-Listener $frontendPort
        if ($ownedFrontend) {
            Warn "Dashboard already running (started by this script, PID $($ownedFrontend.pid)); not starting another."
        } elseif ($listener) {
            Warn "Port $frontendPort is already in use (PID $($listener.OwningProcess)); not starting another dashboard and not stopping that process."
        } else {
            $log = Join-Path $control "frontend.log"
            Rotate-Log $log
            $vite = Join-Path $frontend "node_modules\vite\bin\vite.js"
            # cmd.exe writes Vite's output to the log; the node process it starts is the
            # dashboard server and is the process recorded as owned.
            $command = "`"`"$($node.Source)`" `"$vite`" --host 127.0.0.1 --port $frontendPort --strictPort > `"$log`" 2>&1`""
            $shell = Start-Process -FilePath "cmd.exe" -ArgumentList @("/d", "/c", $command) -WorkingDirectory $frontend -WindowStyle Hidden -PassThru
            $process = $null
            $deadline = (Get-Date).AddSeconds(15)
            while (-not $process -and (Get-Date) -lt $deadline -and -not $shell.HasExited) {
                $child = Get-CimInstance Win32_Process -Filter "ParentProcessId=$($shell.Id) AND Name='node.exe'" -ErrorAction SilentlyContinue | Select-Object -First 1
                if ($child) { $process = Get-Process -Id $child.ProcessId -ErrorAction SilentlyContinue }
                else { Start-Sleep -Milliseconds 200 }
            }
            if (-not $process -or -not (Wait-Http $dashboardUrl $process $ReadyTimeoutSeconds)) {
                Get-Content $log -Tail 20 -ErrorAction SilentlyContinue | Out-Host
                if ($process -and -not $process.HasExited) { Stop-Process -Id $process.Id -Force }
                Fail "Dashboard did not respond within $ReadyTimeoutSeconds s (log: runs\system\frontend.log)."
            }
            Write-Owned "frontend" $process $dashboardUrl $log
            Ok "Dashboard ready on $dashboardUrl (PID $($process.Id))"
        }
    }
} finally {
    Pop-Location
}

Write-Host ""
if (-not $BackendOnly) { Write-Host "Dashboard:  $dashboardUrl" }
Write-Host "Backend:    $backendUrl   (API docs: $backendUrl/docs)"
Write-Host "Status:     powershell -ExecutionPolicy Bypass -File scripts\status_system.ps1"
Write-Host "Stop:       powershell -ExecutionPolicy Bypass -File scripts\stop_system.ps1"
Write-Host "Accounts:   python -m backend.cli create-user --username <name> --role <role> (password from SWARM_NEW_USER_PASSWORD)"
