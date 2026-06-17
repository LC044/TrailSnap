$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$WebsiteDir = Join-Path $RepoRoot 'package\website'

Push-Location $WebsiteDir

try {
    if (-not (Test-Path (Join-Path $WebsiteDir 'node_modules'))) {
        Write-Host 'Installing website dependencies...'
        pnpm install --frozen-lockfile
    }

    Write-Host 'Ensuring Playwright browser is installed...'
    pnpm exec playwright install chromium

    $env:TS_API_BASE_URL = 'http://localhost:8800'
    $env:TS_WEB_BASE_URL = 'http://localhost:8082'
    $env:TS_PHOTO_DIR = '/testdata/photos'

    Write-Host 'Running system smoke tests...'
    pnpm test:e2e:system
}
finally {
    Pop-Location
}
