<#
.SYNOPSIS
    Start the E2E docker-compose stack.

.PARAMETER SkipPull
    跳过 `docker compose pull`，本地已 build 的镜像用此选项（CI runner 默认场景）。
    注意：使用此选项前必须确保 compose 文件引用的镜像在本地 Docker 中存在；
    CI workflow 会先 `docker build` 出 :ci 标签并替换 compose 中的 :master 引用。

.PARAMETER ComposeFile
    自定义 compose 文件路径（默认 tests/docker/docker-compose.e2e.yml）。
#>
param(
    [switch]$SkipPull,
    [string]$ComposeFile
)

$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $ComposeFile) { $ComposeFile = Join-Path $RepoRoot 'tests\docker\docker-compose.e2e.yml' }
$ArtifactsDir = Join-Path $RepoRoot 'tests\artifacts'

New-Item -ItemType Directory -Force -Path $ArtifactsDir | Out-Null

if ($SkipPull) {
    Write-Host 'SkipPull: skipping `docker compose pull` (using local images).'
} else {
    Write-Host 'Pulling E2E images...'
    docker compose -f $ComposeFile pull
}

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
