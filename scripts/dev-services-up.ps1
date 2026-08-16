<#
.SYNOPSIS
为本地开发启动 TrailSnap 三个服务（前端 / 后端 / AI），每个服务一个独立终端窗口。

.DESCRIPTION
与 tests/scripts/services-up.ps1（无头后台进程，给测试用）不同，本脚本为每个服务
开一个带可识别标题的 cmd.exe 窗口，方便开发者直接看实时日志、用 Ctrl+C 单独停、
或在窗口里交互。三窗口互不影响，启动后可以根据需要关闭其中任何一个。

启动顺序：后端 -> AI -> 前端。三个终端窗口的 cmd.exe PID 写入
scripts/.dev-services.state.json，由 dev-services-down.ps1 读取后用 taskkill /F /T
关闭整棵进程树（含 uvicorn / pnpm / python 等子进程）。

如果上一次的 PID 还活着，脚本会拒绝启动并提示先运行关闭脚本。

.PARAMETER Reload
后端和 AI 是否用 uvicorn --reload（默认开启）。关闭后改用 python start.py
（带 alembic 迁移 + 5A CSV 导入的初始化流程）。

.PARAMETER BackendPort
后端端口，默认 8000。

.PARAMETER AiPort
AI 服务端口，默认 8001。

.PARAMETER FrontendPort
前端端口，默认 5176。

.PARAMETER SkipFrontend / SkipBackend / SkipAi
跳过对应服务的启动（仅启动另外两个）。配合关闭脚本仍可一键清理。

.EXAMPLE
.\scripts\dev-services-up.ps1
.\scripts\dev-services-down.ps1

.\scripts\dev-services-up.ps1 -Reload:$false      # 后端改用 start.py 初始化
.\scripts\dev-services-up.ps1 -SkipFrontend      # 只起后端 + AI
#>
param(
    [switch]$Reload = $true,
    [int]$BackendPort = 8000,
    [int]$AiPort = 8001,
    [int]$FrontendPort = 5176,
    [switch]$SkipFrontend,
    [switch]$SkipBackend,
    [switch]$SkipAi
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$StateFile = Join-Path $PSScriptRoot '.dev-services.state.json'

# 复用测试脚本里的端口清理 + uv 解析（避免重复实现）
. (Join-Path $RepoRoot 'tests/scripts/test-services-lib.ps1')

# -----------------------------------------------------------------------------
# 1. 防重复启动：上一次启动的 PID 还活着就拒绝
# -----------------------------------------------------------------------------
if (Test-Path $StateFile) {
    try {
        $state = Get-Content $StateFile -Raw | ConvertFrom-Json
        $alive = @()
        foreach ($procId in $state.pids) {
            if (Get-Process -Id $procId -ErrorAction SilentlyContinue) { $alive += $procId }
        }
        if ($alive.Count -gt 0) {
            Write-Host "上一次启动还在运行（PID: $($alive -join ', ')）。" -ForegroundColor Yellow
            Write-Host "请先执行：.\scripts\dev-services-down.ps1" -ForegroundColor Yellow
            exit 1
        }
    } catch {
        # 状态文件解析失败，忽略并清理
        Remove-Item $StateFile -Force -ErrorAction SilentlyContinue
    }
}

# -----------------------------------------------------------------------------
# 2. 启动前清理占用端口的进程（孤儿进程 / 上次漏关 / 手动起的）
# -----------------------------------------------------------------------------
$portsToClear = @()
if (-not $SkipBackend)  { $portsToClear += $BackendPort }
if (-not $SkipAi)       { $portsToClear += $AiPort }
if (-not $SkipFrontend) { $portsToClear += $FrontendPort }

Write-Host "==> 启动前清理端口: $($portsToClear -join ', ')" -ForegroundColor Cyan
Clear-ServicePorts -Ports $portsToClear -Reason '启动前清理'

# -----------------------------------------------------------------------------
# 3. 解析 uv（后端 / AI 必需），找不到就早退
# -----------------------------------------------------------------------------
$uv = Resolve-Uv
if (-not $uv) {
    Write-Host "找不到 uv，请先安装：https://docs.astral.sh/uv/" -ForegroundColor Red
    exit 1
}

$serverDir = Join-Path $RepoRoot 'package/server'
$aiDir     = Join-Path $RepoRoot 'package/ai'
$webDir    = Join-Path $RepoRoot 'package/website'

Write-Host ""
Write-Host "==> 启动开发服务（每个服务一个独立终端窗口）" -ForegroundColor Cyan
Write-Host "    后端  http://localhost:$BackendPort" -ForegroundColor DarkGray
Write-Host "    AI    http://localhost:$AiPort" -ForegroundColor DarkGray
Write-Host "    前端  http://localhost:$FrontendPort" -ForegroundColor DarkGray

$startedPids = @()
# -----------------------------------------------------------------------------
# 4. 启动后端
# -----------------------------------------------------------------------------
if (-not $SkipBackend) {
    $serverCmd = if ($Reload) {
        "title TrailSnap - Backend ($BackendPort) && uv run uvicorn main:app --host 0.0.0.0 --port $BackendPort --reload"
    } else {
        "title TrailSnap - Backend ($BackendPort) && uv run python start.py --port $BackendPort"
    }
    Write-Host "  [1/3] 后端  ($BackendPort)..." -ForegroundColor Green
    $proc = Start-Process -FilePath cmd.exe `
        -ArgumentList '/k', $serverCmd `
        -WorkingDirectory $serverDir `
        -PassThru
    $startedPids += $proc.Id
}

# -----------------------------------------------------------------------------
# 5. 启动 AI
# -----------------------------------------------------------------------------
if (-not $SkipAi) {
    $aiCmd = "title TrailSnap - AI ($AiPort) && uv run uvicorn main:app --host 0.0.0.0 --port $AiPort --reload"
    Write-Host "  [2/3] AI    ($AiPort)..." -ForegroundColor Green
    $proc = Start-Process -FilePath cmd.exe `
        -ArgumentList '/k', $aiCmd `
        -WorkingDirectory $aiDir `
        -PassThru
    $startedPids += $proc.Id
}

# -----------------------------------------------------------------------------
# 6. 启动前端
# -----------------------------------------------------------------------------
if (-not $SkipFrontend) {
    $webCmd = "title TrailSnap - Frontend ($FrontendPort) && pnpm dev --port $FrontendPort"
    Write-Host "  [3/3] 前端  ($FrontendPort)..." -ForegroundColor Green
    $proc = Start-Process -FilePath cmd.exe `
        -ArgumentList '/k', $webCmd `
        -WorkingDirectory $webDir `
        -PassThru
    $startedPids += $proc.Id
}
# -----------------------------------------------------------------------------
# 7. 写入状态文件（关闭脚本读取）
# -----------------------------------------------------------------------------
$state = [ordered]@{
    startedAt    = (Get-Date).ToString('o')
    pids         = $startedPids
    backendPort  = if ($SkipBackend)  { $null } else { $BackendPort }
    aiPort       = if ($SkipAi)       { $null } else { $AiPort }
    frontendPort = if ($SkipFrontend) { $null } else { $FrontendPort }
}
$state | ConvertTo-Json | Set-Content -Path $StateFile -Encoding utf8

Write-Host ""
Write-Host "==> 终端已就位（窗口标题：TrailSnap - Backend / AI / Frontend）" -ForegroundColor Green
Write-Host "    一键关闭：.\scripts\dev-services-down.ps1" -ForegroundColor Yellow
Write-Host "    状态文件：$StateFile" -ForegroundColor DarkGray
