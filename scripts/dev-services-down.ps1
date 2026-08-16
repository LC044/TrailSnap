<#
.SYNOPSIS
关闭由 dev-services-up.ps1 启动的三个开发终端。

.DESCRIPTION
读取 scripts/.dev-services.state.json 中的 PID，用 taskkill /F /T 关闭整棵
进程树（含 uvicorn / pnpm / python 等子进程）。如果状态文件丢失或 PID 已死，
回退按端口清理（复用 test-services-lib.ps1 的 Clear-ServicePorts）。

端口清理同时使用状态文件里的端口 + 默认端口（8000/8001/5176），以兜底处理
状态文件丢失 / 端口漂移的情况。

.PARAMETER KeepState
只关闭进程、不删除状态文件（调试用，下次启动脚本仍能识别）。
#>
param(
    [switch]$KeepState
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$StateFile = Join-Path $PSScriptRoot '.dev-services.state.json'

# 复用测试脚本里的端口清理（避免重复实现）
. (Join-Path $RepoRoot 'tests/scripts/test-services-lib.ps1')

Write-Host "==> 关闭开发服务" -ForegroundColor Cyan

$portsFromState = @()
$procIdsFromState = @()

# -----------------------------------------------------------------------------
# 1. 读状态文件，关闭其中记录的 PID
# -----------------------------------------------------------------------------
if (Test-Path $StateFile) {
    try {
        $state = Get-Content $StateFile -Raw | ConvertFrom-Json
        # pids 可能是数组也可能是单个数（ConvertFrom-Json 对单元素数组的还原行为）
        if ($null -ne $state.pids) {
            $procIdsFromState = @($state.pids)
        }
        foreach ($prop in 'backendPort', 'aiPort', 'frontendPort') {
            $v = $state.$prop
            if ($null -ne $v -and "$v" -ne '') { $portsFromState += [int]$v }
        }
    } catch {
        Write-Host "  状态文件解析失败，转用默认端口兜底" -ForegroundColor Yellow
    }
} else {
    Write-Host "  未找到状态文件，转用默认端口兜底" -ForegroundColor DarkGray
}

foreach ($procId in $procIdsFromState) {
    $alive = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if (-not $alive) {
        Write-Host "  PID $procId 已不在，跳过" -ForegroundColor DarkGray
        continue
    }
    Write-Host "  关闭 PID $procId ($($alive.ProcessName))..." -ForegroundColor Yellow
    try {
        & taskkill /F /T /PID $procId 2>&1 | Out-Null
    } catch {
        # taskkill 在某些进程上可能拒绝（访问被拒等），回退 Stop-Process
        try { Stop-Process -Id $procId -Force -ErrorAction Stop } catch {}
    }
}
# -----------------------------------------------------------------------------
# 2. 端口兜底清理（状态文件里的端口 + 默认端口），处理漏网之鱼
# -----------------------------------------------------------------------------
$portsToClean = @($portsFromState + 8000, 8001, 5176) | Sort-Object -Unique
Clear-ServicePorts -Ports $portsToClean -Reason '关闭开发服务'

if ((Test-Path $StateFile) -and -not $KeepState) {
    Remove-Item $StateFile -Force
}

Write-Host "==> 关闭完成" -ForegroundColor Green
