[CmdletBinding()]
param(
    [switch]$SkipInstall,

    [ValidateSet('all', 'nsis', 'msi', 'dmg', 'appimage', 'deb')]
    [string]$Bundles = 'all'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory)]
        [string]$FilePath,

        [Parameter(Mandatory)]
        [string[]]$ArgumentList,

        [string]$WorkingDirectory
    )

    if ($WorkingDirectory) {
        Push-Location $WorkingDirectory
    }

    try {
        & $FilePath @ArgumentList
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($ArgumentList -join ' ')"
        }
    }
    finally {
        if ($WorkingDirectory) {
            Pop-Location
        }
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$websiteDir = Join-Path $repoRoot 'package\website'
$serverDir = Join-Path $repoRoot 'package\server'
$desktopDir = Join-Path $repoRoot 'package\desktop'

if (-not $SkipInstall) {
    Invoke-NativeCommand pnpm @('--dir', $websiteDir, 'install', '--frozen-lockfile')
    Invoke-NativeCommand pnpm @('--dir', $desktopDir, 'install', '--frozen-lockfile')
    Invoke-NativeCommand uv @('sync', '--project', $serverDir, '--group', 'dev')
}

Invoke-NativeCommand pnpm @('--dir', $websiteDir, 'build')
Invoke-NativeCommand uv @('run', 'python', 'scripts/build_desktop_runtime.py') $serverDir

$sidecarSource = Join-Path $serverDir 'dist\trailsnap-server'
$sidecarTarget = Join-Path $desktopDir 'server-dist\trailsnap-server'
$resolvedDesktopDir = [System.IO.Path]::GetFullPath($desktopDir).TrimEnd('\') + '\'
$resolvedSidecarTarget = [System.IO.Path]::GetFullPath($sidecarTarget)
if (-not $resolvedSidecarTarget.StartsWith($resolvedDesktopDir, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to replace sidecar outside desktop workspace: $resolvedSidecarTarget"
}
if (Test-Path -LiteralPath $sidecarTarget) {
    Remove-Item -LiteralPath $sidecarTarget -Recurse -Force
}
New-Item -ItemType Directory -Path (Split-Path $sidecarTarget) -Force | Out-Null
Copy-Item -LiteralPath $sidecarSource -Destination $sidecarTarget -Recurse

if ($Bundles -eq 'all') {
    Invoke-NativeCommand pnpm @('--dir', $desktopDir, 'build')
}
else {
    Invoke-NativeCommand pnpm @('--dir', $desktopDir, 'exec', 'tauri', 'build', '--bundles', $Bundles)
}
