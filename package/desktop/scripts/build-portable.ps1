[CmdletBinding()]
param([switch]$SkipBuild, [string]$OutputDirectory, [ValidateSet('x86_64','aarch64')][string]$Architecture='x86_64', [string]$WebViewRuntime)
$ErrorActionPreference='Stop'
$repoRoot=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$desktopRoot=Join-Path $repoRoot 'package/desktop'
$rustRoot=Join-Path $desktopRoot 'src-tauri'
if (-not $OutputDirectory) { $OutputDirectory=Join-Path $desktopRoot "dist/portable-$([Guid]::NewGuid())" }
if (-not $SkipBuild) {
    & (Join-Path $PSScriptRoot 'build.ps1') -SkipInstall -Bundles nsis
    if ($LASTEXITCODE -ne 0) { throw 'Desktop build failed' }
}
$version=(Get-Content -LiteralPath (Join-Path $rustRoot 'tauri.conf.json') -Raw | ConvertFrom-Json).version
$runtimeArguments = @()
if ($WebViewRuntime) { $runtimeArguments = @('--webview-runtime', $WebViewRuntime) }
& uv run --project (Join-Path $repoRoot 'package/server') python (Join-Path $PSScriptRoot 'package_portable.py') `
    --program (Join-Path $rustRoot 'target/release') `
    --server (Join-Path $repoRoot 'package/server/dist/trailsnap-server') `
    --launcher (Join-Path $rustRoot 'target/release/trailsnap-launcher.exe') `
    --catalog (Join-Path $rustRoot 'resources/ai-extensions.json') `
    --output $OutputDirectory --version $version --arch $Architecture @runtimeArguments
if ($LASTEXITCODE -ne 0) { throw 'Portable packaging failed' }
