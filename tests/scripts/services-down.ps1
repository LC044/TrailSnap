<#
.SYNOPSIS
    关闭测试服务（dev 本地进程 或 docker compose 栈），并收集日志。

.DESCRIPTION
    与 services-up.ps1 配对。CI 与本地共用。
    -Mode dev    ：按服务端口查找监听进程，taskkill /F /T 杀进程树 + 端口兜底清扫。
    -Mode docker ：docker compose logs 收集到 tests/artifacts/docker-compose.log，再 down -v。
    TS_TEST_KEEP_SERVICES=true 时跳过关闭（保留现场供查看）。

.PARAMETER EnvFile
    环境变量文件路径，默认 tests/.env.test。

.PARAMETER Mode
    dev | docker。不传则按 TS_TEST_ENV 推断。

.PARAMETER Component
    决定清理哪些端口（dev 模式）。docker 模式整栈 down。
#>
param(
    [string]$EnvFile,
    [ValidateSet('dev', 'docker')][string]$Mode,
    [ValidateSet('server', 'ai', 'website', 'all')][string]$Component = 'all'
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..' '..')).Path
if (-not $EnvFile) { $EnvFile = Join-Path $RepoRoot 'tests' '.env.test' }
if (-not [System.IO.Path]::IsPathRooted($EnvFile)) { $EnvFile = Join-Path $RepoRoot $EnvFile }
# EnvFile 可能不存在（例如从未生成），不加载也不报错——端口清理只依赖 TS_* 是否已在会话中。
if (Test-Path $EnvFile) {
    . (Join-Path $PSScriptRoot 'Import-EnvFile.ps1')
    Import-EnvFile -Path $EnvFile
}
. (Join-Path $PSScriptRoot 'test-services-lib.ps1')

if (-not $Mode) {
    $Mode = if ($env:TS_TEST_ENV -in 'docker', 'ci') { 'docker' } else { 'dev' }
}

$ArtifactsDir = Join-Path $RepoRoot 'tests' 'artifacts'
New-Item -ItemType Directory -Force -Path $ArtifactsDir | Out-Null

if (Test-KeepServicesFlag) {
    Write-Host "==> TS_TEST_KEEP_SERVICES=true，保留服务运行，跳过关闭。" -ForegroundColor Green
    exit 0
}

Write-Host "==> 关闭测试服务  Mode=$Mode  Component=$Component" -ForegroundColor Cyan

if ($Mode -eq 'dev') {
    $ports = Get-ServicePorts -Component $Component
    if ($ports.Count -eq 0) {
        Write-Host "  未解析到服务端口（检查 TS_API_BASE_URL / TS_AI_API_URL / TS_WEB_BASE_URL）。" -ForegroundColor Yellow
    } else {
        Clear-ServicePorts -Ports $ports -Reason '停止服务'
        Write-Host "  已清理端口: $($ports -join ', ')" -ForegroundColor Green
    }
}
elseif ($Mode -eq 'docker') {
    $composeFile = Join-Path $RepoRoot 'tests' 'docker' 'docker-compose.yml'
    if (Test-Path $composeFile) {
        $logFile = Join-Path $ArtifactsDir 'docker-compose.log'
        Write-Host "  收集 docker compose logs → $logFile" -ForegroundColor Cyan
        & docker compose -f $composeFile --env-file $EnvFile logs --no-color 2>$null | Out-File -FilePath $logFile -Encoding utf8
        Write-Host "  docker compose down -v..." -ForegroundColor Cyan
        & docker compose -f $composeFile --env-file $EnvFile down -v
    } else {
        Write-Host "  找不到 $composeFile，跳过 docker 关闭。" -ForegroundColor Yellow
    }
}

Write-Host "==> 服务关闭完成" -ForegroundColor Green
