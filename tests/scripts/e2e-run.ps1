<#
.SYNOPSIS
    Run Playwright E2E tests in the running docker-compose E2E stack.
#>
param([ValidateSet('p0','smoke','all')][string]$Level='p0')
# Force UTF-8 console encoding (cross-platform: Windows + Linux pwsh)
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
if ($PSVersionTable.PSVersion.Major -ge 7) {
  try { [Console]::InputEncoding = [System.Text.Encoding]::UTF8 } catch {}
}
if ($IsWindows -or ($env:OS -eq 'Windows_NT')) {
  cmd /c chcp 65001 > $null 2>&1
}
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
  # Playwright 1.60 testDir 必须是单目录；all 套件 = p0 + smoke 串行执行两次
  switch ($Level) {
    'p0'    {
      $env:TS_E2E_SUITE = 'p0'
      Write-Host "Level=p0 (TS_E2E_SUITE=p0) API=$($env:TS_API_BASE_URL) Web=$($env:TS_WEB_BASE_URL) User=$($env:TS_TEST_USERNAME)"
      & pnpm test:e2e
    }
    'smoke' {
      $env:TS_E2E_SUITE = 'smoke'
      Write-Host "Level=smoke (TS_E2E_SUITE=smoke) API=$($env:TS_API_BASE_URL) Web=$($env:TS_WEB_BASE_URL) User=$($env:TS_TEST_USERNAME)"
      & pnpm test:e2e
    }
    'all'   {
      Write-Host "Level=all (TS_E2E_SUITE=p0 then =smoke) API=$($env:TS_API_BASE_URL) Web=$($env:TS_WEB_BASE_URL) User=$($env:TS_TEST_USERNAME)"
      $env:TS_E2E_SUITE = 'p0'
      Write-Host '[1/2] Running P0...'
      & pnpm test:e2e
      if ($LASTEXITCODE -ne 0) { throw "P0 failed $LASTEXITCODE" }
      $env:TS_E2E_SUITE = 'smoke'
      Write-Host '[2/2] Running smoke...'
      & pnpm test:e2e
    }
  }
  if ($LASTEXITCODE -ne 0) { throw "Tests failed $LASTEXITCODE" }
  Write-Host 'E2E tests passed.'
} finally { Pop-Location }
