<#
.SYNOPSIS
  Stop the SWARM-AID services started by scripts\start_system.ps1, and nothing else.

.DESCRIPTION
  Backend: writes runs\system\backend.stop. The owned backend process (python -m orchestration
  serve) then exits through uvicorn's graceful shutdown, which stops active missions (recorded
  as "stopped", reason "backend shutdown"), persists pending tick data, closes WebSocket
  connections and releases database connections. Only if that does not finish within
  -GraceSeconds is the owned process terminated, and the script says so.

  Dashboard: the owned Vite process holds no mission state and is terminated directly.

  A process is treated as owned only if its PID and start time match the record written at
  start, so a reused PID or an unrelated Python/Node/database process is never touched.
#>
param([int]$GraceSeconds = 45)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$control = Join-Path $root "runs\system"

function Get-OwnedProcess([string]$Name) {
    $file = Join-Path $control "$Name.process.json"
    if (-not (Test-Path $file)) { return $null }
    $record = Get-Content $file -Raw | ConvertFrom-Json
    $process = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
    if ($null -eq $process -or $process.StartTime.ToUniversalTime().ToString("o") -ne $record.start_time) {
        Write-Host "$Name record is stale (process $($record.pid) no longer running); removing record." -ForegroundColor Yellow
        Remove-Item $file -Force
        return $null
    }
    return $process
}

$stoppedAny = $false

$backend = Get-OwnedProcess "backend"
if ($backend) {
    Write-Host "Requesting graceful backend shutdown (PID $($backend.Id))..."
    Set-Content -Path (Join-Path $control "backend.stop") -Value "stop" -Encoding ascii
    if ($backend.WaitForExit($GraceSeconds * 1000)) {
        Write-Host "Backend stopped gracefully." -ForegroundColor Green
    } else {
        Write-Host "Backend did not exit within $GraceSeconds s; terminating the owned process. Active missions will be marked stopped at next startup." -ForegroundColor Yellow
        # The .venv python.exe is a launcher that runs the interpreter as a child process; the
        # server writes the child's PID to backend.state.json. Stop it only if its parent is
        # the owned launcher.
        $stateFile = Join-Path $control "backend.state.json"
        if (Test-Path $stateFile) {
            $serverPid = (Get-Content $stateFile -Raw | ConvertFrom-Json).pid
            $child = Get-CimInstance Win32_Process -Filter "ProcessId=$serverPid" -ErrorAction SilentlyContinue
            if ($child -and $child.ParentProcessId -eq $backend.Id) { Stop-Process -Id $serverPid -Force }
        }
        Stop-Process -Id $backend.Id -Force
    }
    Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $control "backend.process.json"), (Join-Path $control "backend.stop")
    $stoppedAny = $true
}

$frontend = Get-OwnedProcess "frontend"
if ($frontend) {
    Write-Host "Stopping dashboard (PID $($frontend.Id))..."
    Stop-Process -Id $frontend.Id
    $frontend.WaitForExit(10000) | Out-Null
    Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $control "frontend.process.json")
    Write-Host "Dashboard stopped." -ForegroundColor Green
    $stoppedAny = $true
}

foreach ($port in 8000, 5173) {
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) {
        Write-Host "Port $port is still in use by PID $($listener.OwningProcess), which was not started by start_system.ps1; left running." -ForegroundColor Yellow
    }
}
if (-not $stoppedAny) { Write-Host "No services started by start_system.ps1 are running." }
