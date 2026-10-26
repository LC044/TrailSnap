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
$aiDir = Join-Path $repoRoot 'package\ai'
$serverDir = Join-Path $repoRoot 'package\server'
$desktopDir = Join-Path $repoRoot 'package\desktop'

if (-not $SkipInstall) {
    Invoke-NativeCommand pnpm @('--dir', $websiteDir, 'install', '--frozen-lockfile')
    Invoke-NativeCommand pnpm @('--dir', $desktopDir, 'install', '--frozen-lockfile')
    Invoke-NativeCommand uv @('sync', '--project', $serverDir, '--group', 'dev')
    Invoke-NativeCommand uv @('sync', '--project', $aiDir, '--extra', 'cpu', '--group', 'desktop')
}

Invoke-NativeCommand pnpm @('--dir', $websiteDir, 'build')
Invoke-NativeCommand uv @('run', 'python', 'scripts/build_desktop_runtime.py') $serverDir
Invoke-NativeCommand uv @('run', 'python', '-c', "from app.services.unified_model_manager import ai_model_manager; ai_model_manager.prepare_model('ocr'); from app.services.ocr_service import load_paddleocr_model; load_paddleocr_model()") $aiDir
Invoke-NativeCommand uv @('run', 'python', 'scripts/build_desktop_runtime.py') $aiDir

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

$aiTarget = Join-Path $desktopDir 'ai-dist\trailsnap-ai'
$resolvedAiTarget = [System.IO.Path]::GetFullPath($aiTarget)
if (-not $resolvedAiTarget.StartsWith($resolvedDesktopDir, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'AI staging path escaped desktop workspace' }
if (Test-Path -LiteralPath $aiTarget) { Remove-Item -LiteralPath $aiTarget -Recurse -Force }
New-Item -ItemType Directory -Path (Split-Path $aiTarget) -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $aiDir 'dist\trailsnap-ai') -Destination $aiTarget -Recurse
Invoke-NativeCommand uv @('run', '--project', $serverDir, 'python', (Join-Path $PSScriptRoot 'validate_components.py'))

if ($Bundles -eq 'all') {
    if ($IsWindows) { Invoke-NativeCommand cargo @('build','--release','--manifest-path','../launcher/Cargo.toml','--target-dir','target') (Join-Path $desktopDir 'src-tauri') }
    Invoke-NativeCommand pnpm @('--dir', $desktopDir, 'build')
}
else {
    if ($IsWindows) { Invoke-NativeCommand cargo @('build','--release','--manifest-path','../launcher/Cargo.toml','--target-dir','target') (Join-Path $desktopDir 'src-tauri') }
    Invoke-NativeCommand pnpm @('--dir', $desktopDir, 'exec', 'tauri', 'build', '--bundles', $Bundles)
}
