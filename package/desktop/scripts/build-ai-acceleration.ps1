[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet('cuda', 'openvino')]
    [string]$Backend,
    [string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (-not $IsWindows -or [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64') {
    throw 'AI acceleration packages currently support Windows x64 only'
}
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$aiRoot = Join-Path $repoRoot 'package/ai'
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $repoRoot 'package/desktop/dist/ai' }
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
$previousEnvironment = $env:UV_PROJECT_ENVIRONMENT
$previousBackend = $env:TS_AI_BUILD_BACKEND
try {
    # Keep the default CPU environment and each accelerator isolated.
    $env:UV_PROJECT_ENVIRONMENT = Join-Path $aiRoot ".venv-desktop-$Backend"
    $env:TS_AI_BUILD_BACKEND = $Backend
    $extra = if ($Backend -eq 'cuda') { 'gpu' } else { 'openvino' }
    $syncArgs = @('sync', '--project', $aiRoot, '--frozen', '--extra', $extra, '--group', 'desktop')
    if ($Backend -eq 'cuda') { $syncArgs += @('--group', 'desktop-cuda') }
    & uv @syncArgs
    if ($LASTEXITCODE -ne 0) { throw 'AI dependency installation failed' }
    Push-Location $aiRoot
    try {
        & uv run --no-sync python scripts/build_desktop_runtime.py
        if ($LASTEXITCODE -ne 0) { throw 'AI runtime build failed' }
        & uv run --no-sync python (Join-Path $PSScriptRoot 'package_ai_runtime.py') pack --source "dist/$Backend/trailsnap-ai" --output $OutputDirectory
        if ($LASTEXITCODE -ne 0) { throw 'AI runtime packaging failed' }
    } finally { Pop-Location }
} finally {
    $env:UV_PROJECT_ENVIRONMENT = $previousEnvironment
    $env:TS_AI_BUILD_BACKEND = $previousBackend
}
