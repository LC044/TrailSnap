[CmdletBinding()]
param(
    [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$websiteDir = Join-Path $repoRoot 'package\website'
$serverDir = Join-Path $repoRoot 'package\server'
$desktopDir = Join-Path $repoRoot 'package\desktop'

if (-not $SkipInstall) {
    pnpm --dir $websiteDir install --frozen-lockfile
    pnpm --dir $desktopDir install --frozen-lockfile
    uv sync --project $serverDir --group dev
}

pnpm --dir $websiteDir build
Push-Location $serverDir
try {
    uv run pyinstaller --noconfirm --clean desktop_server.spec
}
finally {
    Pop-Location
}

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

pnpm --dir $desktopDir dist
