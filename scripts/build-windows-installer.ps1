<#
.SYNOPSIS
Builds the TrailSnap Windows NSIS installer.

.DESCRIPTION
Installs locked project dependencies, builds the Vue frontend, packages the
FastAPI server sidecar, and creates a Windows NSIS installer with Tauri 2.

.PARAMETER SkipInstall
Skips pnpm install and uv sync. Use this for repeated local builds only.

.PARAMETER OpenOutput
Opens the installer output directory after a successful build.

.EXAMPLE
pwsh .\scripts\build-windows-installer.ps1

.EXAMPLE
pwsh .\scripts\build-windows-installer.ps1 -SkipInstall -OpenOutput
#>
[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [switch]$OpenOutput
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
        [System.Runtime.InteropServices.OSPlatform]::Windows
    )) {
    throw 'This script can only build the Windows installer on Windows.'
}

$requiredCommands = @(
    @{ Name = 'pnpm'; InstallHint = 'Install Node.js and pnpm: corepack enable' },
    @{ Name = 'uv'; InstallHint = 'Install uv: https://docs.astral.sh/uv/getting-started/installation/' },
    @{ Name = 'cargo'; InstallHint = 'Install Rust stable: https://rustup.rs/' },
    @{ Name = 'rustc'; InstallHint = 'Install or repair Rust stable: rustup toolchain install stable' }
)

$missingCommands = foreach ($command in $requiredCommands) {
    if (-not (Get-Command $command.Name -ErrorAction SilentlyContinue)) {
        "  - $($command.Name): $($command.InstallHint)"
    }
}

if ($missingCommands) {
    throw "Missing build prerequisites:`n$($missingCommands -join "`n")`nAlso install Microsoft C++ Build Tools and WebView2 when required by Tauri."
}

$unhealthyCommands = foreach ($command in $requiredCommands) {
    $commandName = $command.Name
    & $commandName --version *> $null
    if ($LASTEXITCODE -ne 0) {
        "  - ${commandName}: $($command.InstallHint)"
    }
}

if ($unhealthyCommands) {
    throw "Build prerequisites were found but are not working:`n$($unhealthyCommands -join "`n")"
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$buildScript = Join-Path $repoRoot 'package\desktop\scripts\build.ps1'
$outputDir = Join-Path $repoRoot 'package\desktop\src-tauri\target\release\bundle\nsis'

Write-Host 'Building TrailSnap Windows installer...' -ForegroundColor Cyan
Write-Host "Repository: $repoRoot"

$buildArguments = @{ Bundles = 'nsis' }
if ($SkipInstall) {
    $buildArguments.SkipInstall = $true
}

& $buildScript @buildArguments

$installers = @(Get-ChildItem -LiteralPath $outputDir -Filter '*.exe' -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending)
if ($installers.Count -eq 0) {
    throw "Tauri finished without producing an NSIS installer in: $outputDir"
}

Write-Host ''
Write-Host 'Build completed.' -ForegroundColor Green
foreach ($installer in $installers) {
    $hash = (Get-FileHash -LiteralPath $installer.FullName -Algorithm SHA256).Hash
    $sizeMiB = [Math]::Round($installer.Length / 1MB, 2)
    Write-Host "Installer: $($installer.FullName)"
    Write-Host "Size:      $sizeMiB MiB"
    Write-Host "SHA-256:   $hash"
}

if ($OpenOutput) {
    Start-Process explorer.exe -ArgumentList "`"$outputDir`""
}
