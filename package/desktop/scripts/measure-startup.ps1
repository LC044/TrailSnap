# Measure TrailSnap desktop end-to-end startup time.
# Timeline: desktop.exe launch -> server.exe spawn -> health-check 200 -> desktop-session OK
param(
    [string]$ExePath = "$env:LOCALAPPDATA\TrailSnap\trailsnap-desktop.exe",
    [string]$LogDir = "$env:LOCALAPPDATA\TrailSnap\logs"
)

$ErrorActionPreference = 'Stop'

Write-Host "Target: $ExePath"
if (-not (Test-Path $ExePath)) { throw "Desktop exe not found: $ExePath" }

# Clean previous logs so timestamps are unambiguous.
Remove-Item (Join-Path $LogDir 'server.log'), (Join-Path $LogDir 'server.err.log') -ErrorAction SilentlyContinue

$t0 = [System.Diagnostics.Stopwatch]::StartNew()
$launchWall = Get-Date
Write-Host ("[+{0:N3}s] launching desktop.exe" -f $t0.Elapsed.TotalSeconds)

Start-Process -FilePath $ExePath

# Wait for the server sidecar process to appear.
$serverProc = $null
while ($t0.Elapsed.TotalSeconds -lt 60) {
    $serverProc = Get-Process trailsnap-server -ErrorAction SilentlyContinue |
        Where-Object { $_.StartTime -gt $launchWall.AddSeconds(-2) } |
        Sort-Object StartTime | Select-Object -First 1
    if ($serverProc) {
        Write-Host ("[+{0:N3}s] trailsnap-server.exe spawned (pid {1})" -f $t0.Elapsed.TotalSeconds, $serverProc.Id)
        break
    }
    Start-Sleep -Milliseconds 50
}
if (-not $serverProc) { throw "trailsnap-server.exe never started within 60s" }

# Poll the desktop-ai log / server log for readiness markers.
$desktopProc = Get-Process trailsnap-desktop -ErrorAction SilentlyContinue |
    Where-Object { $_.StartTime -gt $launchWall.AddSeconds(-5) } |
    Select-Object -First 1

$ready = $false
$sessionOk = $false
while ($t0.Elapsed.TotalSeconds -lt 90) {
    if (Test-Path (Join-Path $LogDir 'server.log')) {
        $log = Get-Content (Join-Path $LogDir 'server.log') -Raw -ErrorAction SilentlyContinue
        if (-not $ready -and $log -match 'Uvicorn running') {
            Write-Host ("[+{0:N3}s] uvicorn accepting connections" -f $t0.Elapsed.TotalSeconds)
            $ready = $true
        }
        if ($log -match 'POST /api/auth/desktop-session') {
            Write-Host ("[+{0:N3}s] desktop-session handshake done (UI unlocked)" -f $t0.Elapsed.TotalSeconds)
            $sessionOk = $true
            break
        }
    }
    Start-Sleep -Milliseconds 50
}

$total = $t0.Elapsed.TotalSeconds
Write-Host ""
Write-Host ("TOTAL desktop launch -> UI ready: {0:N2}s" -f $total)
if (-not $sessionOk) {
    Write-Warning "desktop-session marker not found within timeout; check logs"
}
