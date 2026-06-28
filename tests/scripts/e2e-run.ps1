<#
.SYNOPSIS
    Run Playwright E2E tests in the running docker-compose E2E stack.

.DESCRIPTION
    统一调用 package/website/playwright/run-e2e.mjs 执行 scan / p0 / p1 / smoke / all。
    可通过 -ScanPrep auto|true|false 显式控制在非 scan 模式下是否先执行 scan 预扫描；
    命令行参数优先级高于 .env 文件中的 TS_E2E_ENABLE_FIXTURE_SCAN。
#>
param(
  [ValidateSet('scan','p0','p1','smoke','all','light','full')][string]$Level='p0',
  [ValidateSet('auto', 'true', 'false')][string]$ScanPrep='auto'
)
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
  switch ($ScanPrep) {
    'true'  { $env:TS_E2E_ENABLE_FIXTURE_SCAN = 'true' }
    'false' { $env:TS_E2E_ENABLE_FIXTURE_SCAN = 'false' }
    default {
      $env:TS_E2E_ENABLE_FIXTURE_SCAN = if ($env:TS_E2E_ENABLE_FIXTURE_SCAN) { $env:TS_E2E_ENABLE_FIXTURE_SCAN } else { 'false' }
    }
  }
  # 统一委托给 package/website/playwright/run-e2e.mjs，由其处理 p0 / p1 / smoke / all
  switch ($Level) {
    'scan'  {
      $env:TS_E2E_SUITE = 'scan'
      Write-Host "Level=scan (TS_E2E_SUITE=scan) ScanPrepArg=$ScanPrep API=$($env:TS_API_BASE_URL) Web=$($env:TS_WEB_BASE_URL) User=$($env:TS_TEST_USERNAME)"
      & node playwright/run-e2e.mjs scan
    }
    'p0'    {
      $env:TS_E2E_SUITE = 'p0'
      Write-Host "Level=p0 (TS_E2E_SUITE=p0) ScanPrepArg=$ScanPrep ScanPrepEnv=$($env:TS_E2E_ENABLE_FIXTURE_SCAN) API=$($env:TS_API_BASE_URL) Web=$($env:TS_WEB_BASE_URL) User=$($env:TS_TEST_USERNAME)"
      & node playwright/run-e2e.mjs p0
    }
    'p1'    {
      $env:TS_E2E_SUITE = 'p1'
      Write-Host "Level=p1 (TS_E2E_SUITE=p1) ScanPrepArg=$ScanPrep ScanPrepEnv=$($env:TS_E2E_ENABLE_FIXTURE_SCAN) API=$($env:TS_API_BASE_URL) Web=$($env:TS_WEB_BASE_URL) User=$($env:TS_TEST_USERNAME)"
      & node playwright/run-e2e.mjs p1
    }
    'smoke' {
      $env:TS_E2E_SUITE = 'smoke'
      Write-Host "Level=smoke (TS_E2E_SUITE=smoke) ScanPrepArg=$ScanPrep ScanPrepEnv=$($env:TS_E2E_ENABLE_FIXTURE_SCAN) API=$($env:TS_API_BASE_URL) Web=$($env:TS_WEB_BASE_URL) User=$($env:TS_TEST_USERNAME)"
      & node playwright/run-e2e.mjs smoke
    }
    'all'   {
      $env:TS_E2E_SUITE = 'all'
      Write-Host "Level=all (TS_E2E_SUITE=all) ScanPrepArg=$ScanPrep ScanPrepEnv=$($env:TS_E2E_ENABLE_FIXTURE_SCAN) API=$($env:TS_API_BASE_URL) Web=$($env:TS_WEB_BASE_URL) User=$($env:TS_TEST_USERNAME)"
      & node playwright/run-e2e.mjs all
    }
    'light' {
      $env:TS_E2E_SUITE = 'light'
      Write-Host "Level=light (TS_E2E_SUITE=light)"
      & node playwright/run-e2e.mjs light
    }
    'full'  {
      $env:TS_E2E_SUITE = 'full'
      Write-Host "Level=full (TS_E2E_SUITE=full)"
      & node playwright/run-e2e.mjs full
    }
  }
  if ($LASTEXITCODE -ne 0) { throw "Tests failed $LASTEXITCODE" }
  Write-Host 'E2E tests passed.'
} finally { Pop-Location }
