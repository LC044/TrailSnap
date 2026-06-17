$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$ComposeFile = Join-Path $RepoRoot 'tests\docker\docker-compose.e2e.yml'
$ArtifactsDir = Join-Path $RepoRoot 'tests\artifacts'

New-Item -ItemType Directory -Force -Path $ArtifactsDir | Out-Null

Write-Host 'Pulling E2E images...'
docker compose -f $ComposeFile pull

Write-Host 'Starting E2E environment...'
docker compose -f $ComposeFile up -d

function Wait-HttpReady {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$TimeoutSeconds = 180
    )

    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $Deadline) {
        try {
            $Response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 10
            if ($Response.StatusCode -ge 200 -and $Response.StatusCode -lt 500) {
                Write-Host "Ready: $Url"
                return
            }
        }
        catch {
            Start-Sleep -Seconds 3
            continue
        }

        Start-Sleep -Seconds 3
    }

    throw "Timed out waiting for $Url"
}

Wait-HttpReady -Url 'http://localhost:8800/'
Wait-HttpReady -Url 'http://localhost:8082/'

Write-Host 'E2E environment is ready.'
