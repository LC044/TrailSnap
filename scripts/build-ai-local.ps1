<#
.SYNOPSIS
Build and stage desktop AI in the workspace without touching installed libraries.
#>
[CmdletBinding()]
param([switch]$SkipInstall, [switch]$SkipBuild, [switch]$SkipPrecache)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$aiRoot = Join-Path $repoRoot 'package/ai'
Push-Location $aiRoot
try {
    if (!$SkipInstall) {
        uv sync --frozen --extra cpu --group desktop
        if ($LASTEXITCODE) { throw 'AI dependencies failed' }
    }
    if (!$SkipPrecache) {
        uv run python -c "from app.services.unified_model_manager import ai_model_manager; ai_model_manager.prepare_model('ocr'); from app.services.ocr_service import load_paddleocr_model; load_paddleocr_model()"
        if ($LASTEXITCODE) { throw 'OCR resource preparation failed' }
    }
    if (!$SkipBuild) {
        uv run python scripts/build_desktop_runtime.py
        if ($LASTEXITCODE) { throw 'AI build failed' }
    }
} finally { Pop-Location }
$desktopRoot = [IO.Path]::GetFullPath((Join-Path $repoRoot 'package/desktop')).TrimEnd('\') + '\'
$target = [IO.Path]::GetFullPath((Join-Path $desktopRoot 'ai-dist/trailsnap-ai'))
if (!$target.StartsWith($desktopRoot,[StringComparison]::OrdinalIgnoreCase)) { throw 'AI staging escaped workspace' }
if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
New-Item -ItemType Directory -Path (Split-Path $target) -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $aiRoot 'dist/trailsnap-ai') -Destination $target -Recurse
Write-Host "Bundled AI staged at $target. Rebuild the complete desktop application to install it."
