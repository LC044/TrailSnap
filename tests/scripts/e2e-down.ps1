$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$ComposeFile = Join-Path $RepoRoot 'tests\docker\docker-compose.e2e.yml'
$ArtifactsDir = Join-Path $RepoRoot 'tests\artifacts'
$LogFile = Join-Path $ArtifactsDir 'docker-compose.log'

New-Item -ItemType Directory -Force -Path $ArtifactsDir | Out-Null

Write-Host 'Collecting docker compose logs...'
docker compose -f $ComposeFile logs --no-color | Out-File -FilePath $LogFile -Encoding utf8

Write-Host 'Stopping E2E environment...'
docker compose -f $ComposeFile down -v

Write-Host "Logs saved to $LogFile"
