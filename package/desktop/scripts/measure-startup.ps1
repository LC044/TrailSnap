# Measure the actual desktop home screen through WebView2, using an isolated
# library. Requires Node.js 22+. Run 0 is warmup (excluded from comparisons).
param(
    [string]$ExePath = "$env:LOCALAPPDATA\TrailSnap\trailsnap-desktop.exe",
    [string]$DataRoot = (Join-Path ([System.IO.Path]::GetTempPath()) "trailsnap-startup-$([guid]::NewGuid())"),
    [ValidateRange(1, 20)]
    [int]$Runs = 5,
    [string]$OutputPath = (Join-Path $PSScriptRoot '..\..\..\output\performance\startup.json'),
    [string]$ServerBinary
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $ExePath -PathType Leaf)) {
    throw "Desktop exe not found: $ExePath"
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw 'Node.js 22+ is required for the desktop startup benchmark.'
}

$benchmarkArguments = @(
    (Join-Path $PSScriptRoot 'measure-startup.cjs'),
    $ExePath, $OutputPath, $DataRoot, [string]$Runs
)
if ($ServerBinary) { $benchmarkArguments += $ServerBinary }
& node @benchmarkArguments
if ($LASTEXITCODE -ne 0) { throw "Desktop benchmark failed (exit $LASTEXITCODE)." }

$report = Get-Content -LiteralPath $OutputPath -Raw | ConvertFrom-Json
$measured = @($report.results | Where-Object run -gt 0)
foreach ($metric in @('backendReadyMs', 'runtimeReadyMs', 'homeShellMs', 'homeDataMs')) {
    $values = @($measured | ForEach-Object { $_.$metric } | Sort-Object)
    $median = $values[[int][math]::Floor($values.Count / 2)]
    if ($values.Count % 2 -eq 0) {
        $median = ($values[$values.Count / 2 - 1] + $values[$values.Count / 2]) / 2
    }
    Write-Host ("{0}: median {1:N3}s, range {2:N3}-{3:N3}s" -f $metric, ($median / 1000), ($values[0] / 1000), ($values[-1] / 1000))
}
Write-Host "Results: $OutputPath"
Write-Host "Isolated library retained at: $DataRoot"
