<#
.SYNOPSIS
    Run Playwright E2E tests in the running docker-compose E2E stack.
#>
param([ValidateSet('p0','smoke','all')][string]$Level='p0')
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$WebsiteDir = Join-Path $RepoRoot 'package\website'
Push-Location $WebsiteDir
try {
  if (-not (Test-Path (Join-Path $WebsiteDir 'node_modules'))) { Write-Host 'Installing website dependencies...'; pnpm install --frozen-lockfile }
  Write-Host 'Ensuring Playwright browser is installed...'
  pnpm exec playwright install chromium
  $env:TS_API_BASE_URL  = if ($env:TS_API_BASE_URL)  { $env:TS_API_BASE_URL }  else { 'http://localhost:8800' }
  $env:TS_WEB_BASE_URL  = if ($env:TS_WEB_BASE_URL)  { $env:TS_WEB_BASE_URL }  else { 'http://localhost:8082' }
  $env:TS_PHOTO_DIR     = if ($env:TS_PHOTO_DIR)     { $env:TS_PHOTO_DIR }     else { '/testdata/photos' }
  $env:TS_TEST_USERNAME = if ($env:TS_TEST_USERNAME) { $env:TS_TEST_USERNAME } else { 'e2e-admin' }
  $env:TS_TEST_PASSWORD = if ($env:TS_TEST_PASSWORD) { $env:TS_TEST_PASSWORD } else { 'Passw0rd!123' }
  Write-Host "Level=$Level API=$($env:TS_API_BASE_URL) Web=$($env:TS_WEB_BASE_URL) User=$($env:TS_TEST_USERNAME)"
  switch ($Level) {
    'p0'    { & pnpm test:e2e:p0 }
    'smoke' { & pnpm test:e2e:system }
    'all'   { & pnpm test:e2e:p0; if ($LASTEXITCODE -ne 0) { throw "P0 failed $LASTEXITCODE" }; & pnpm test:e2e:system }
  }
  if ($LASTEXITCODE -ne 0) { throw "Tests failed $LASTEXITCODE" }
  Write-Host 'E2E tests passed.'
} finally { Pop-Location }
