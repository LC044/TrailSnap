<#
.SYNOPSIS
    测试服务生命周期的共享函数库。

.DESCRIPTION
    services-up.ps1 / services-down.ps1 / run-tests.ps1 共用本文件。
    涵盖：uv 解析、端口探测、端口→PID 解析、进程树清理、
    TS_TEST_RESET_DB / TS_TEST_KEEP_SERVICES 标志解析、测试库删除、AI 模型预热。

    用法：. (Join-Path $PSScriptRoot 'test-services-lib.ps1')
#>

# 解析 uv：PATH 优先，其次常见安装位置，最后回退到包内 .venv 的 python
function Resolve-Uv {
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($p in @(
            "$env:USERPROFILE\.local\bin\uv.exe",
            "$env:USERPROFILE\.cargo\bin\uv.exe",
            "$env:APPDATA\uv\uv.exe"
        )) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

# TCP 端口是否被监听（500ms 超时，不阻塞）
function Test-Port {
    param([int]$Port)
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $connect = $tcp.BeginConnect('127.0.0.1', $Port, $null, $null)
        $success = $connect.AsyncWaitHandle.WaitOne(500, $false)
        if ($success) {
            $tcp.EndConnect($connect)
            $tcp.Close()
            return $true
        } else {
            $tcp.Close()
            return $false
        }
    } catch {
        return $false
    }
}

# 轮询 HTTP 健康端点直到返回 200，或超时返回 $false。
# 必须用应用层探测而非 Test-Port：docker compose 的端口发布在容器一启动就由
# docker-proxy 在宿主侧监听，但此时容器内 uvicorn 可能还没 bind（start.py 仍在
# 跑迁移/导 CSV，冷启动可达 ~100s）。docker-proxy 在后端未就绪时会 accept 再立即
# 关闭连接 → TCP 探测"假就绪"，Playwright 此时请求会 socket hang up。直接打
# /health-check 直到 200 才能确认 uvicorn 已开始服务。
function Wait-HttpReady {
    param(
        [Parameter(Mandatory)][string]$Url,
        [int]$TimeoutSeconds = 180,
        [int]$IntervalSeconds = 2
    )
    $attempts = [int]([math]::Max(1, [math]::Floor($TimeoutSeconds / $IntervalSeconds)))
    for ($i = 1; $i -le $attempts; $i++) {
        try {
            $resp = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 5 -ErrorAction Stop
            if ($resp.StatusCode -eq 200) { return $true }
        } catch {
            # 连接被 reset（docker-proxy 后端未就绪）/ 拒绝 / 5xx → 继续轮询
        }
        Start-Sleep -Seconds $IntervalSeconds
    }
    return $false
}

# 计算本次运行“关心的”服务端口（server + ai，web 仅当 Component 含 website）
function Get-ServicePorts {
    param([string]$Component = 'all')
    $ports = @()
    if ($env:TS_API_BASE_URL) { try { $ports += [int]([System.Uri]$env:TS_API_BASE_URL).Port } catch {} }
    if ($env:TS_AI_API_URL)   { try { $ports += [int]([System.Uri]$env:TS_AI_API_URL).Port } catch {} }
    if ($Component -in 'website', 'all' -and $env:TS_WEB_BASE_URL) {
        try { $ports += [int]([System.Uri]$env:TS_WEB_BASE_URL).Port } catch {}
    }
    return ($ports | Sort-Object -Unique)
}

# 一次性查出哪些端口被哪个 PID 监听。用 netstat -ano 而非 Get-NetTCPConnection：
# 后者依赖 NetTCPIP 的 CIM provider，该 provider 在某些 Windows 状态下会无限阻塞
# （已知问题，无超时参数可设），会导致整个脚本卡死在端口清理环节。netstat 稳定且更快。
function Get-PortListeners {
    param([int[]]$Ports)
    $result = @{}
    if (-not $Ports -or $Ports.Count -eq 0) { return $result }
    $portSet = @{}
    foreach ($p in $Ports) { $portSet[[int]$p] = $true }
    try {
        $lines = netstat -ano -p TCP 2>$null
        foreach ($line in $lines) {
            if ($line -notmatch '\bLISTENING\b') { continue }
            $cols = ($line -split '\s+') | Where-Object { $_ }
            if ($cols.Count -lt 5) { continue }
            if ($cols[1] -notmatch ':(\d+)$') { continue }
            $port = [int]$matches[1]
            if (-not $portSet.ContainsKey($port)) { continue }
            $listenerPid = 0
            if (-not [int]::TryParse($cols[-1], [ref]$listenerPid)) { continue }
            if ($listenerPid -le 0) { continue }
            if (-not $result.ContainsKey($port)) { $result[$port] = @() }
            if ($result[$port] -notcontains $listenerPid) { $result[$port] += $listenerPid }
        }
    } catch {}
    return $result
}

# 杀掉占用指定端口的进程（含其子进程树）。
# 主路径走 taskkill /F /T：tree-kill 递归杀整棵进程树，才能干掉 FastAPI lifespan
# 起的 worker 子进程、AI 服务的 llama-server 子进程、Vite esbuild watcher 等被
# reparent 成孤儿的后代进程；只 Stop-Process 不杀子树会留残余。
function Clear-ServicePorts {
    param([int[]]$Ports, [string]$Reason = '清理')
    if (-not $Ports -or $Ports.Count -eq 0) { return }
    $listeners = Get-PortListeners -Ports $Ports
    foreach ($port in ($Ports | Sort-Object -Unique)) {
        $holderPids = $listeners[$port]
        if (-not $holderPids) { continue }
        foreach ($holderPid in $holderPids) {
            try { $holder = Get-Process -Id $holderPid -ErrorAction Stop } catch { continue }
            Write-Host "  [$Reason] 端口 $port <- PID $holderPid ($($holder.ProcessName))，强制关闭..." -ForegroundColor Yellow
            try {
                & taskkill /F /T /PID $holderPid 2>$null
            } catch {
                Write-Host "    taskkill 不可用，回退 Stop-Process：$($_.Exception.Message)" -ForegroundColor DarkYellow
                try { Stop-Process -Id $holderPid -Force -ErrorAction Stop } catch {}
            }
        }
    }
}

# 把 TS_TEST_RESET_DB 解析为布尔：true/1/yes 视为开启，其余（含空/false）为关闭。
function Test-ResetDbFlag {
    $v = $env:TS_TEST_RESET_DB
    if (-not $v) { return $false }
    return @('true', '1', 'yes') -contains $v.Trim().ToLower()
}

# 把 TS_TEST_KEEP_SERVICES 解析为布尔：true/1/yes 视为开启，其余（含空/false）为关闭。
function Test-KeepServicesFlag {
    $v = $env:TS_TEST_KEEP_SERVICES
    if (-not $v) { return $false }
    return @('true', '1', 'yes') -contains $v.Trim().ToLower()
}

# 删除 TS_DB_URL 指向的目标库：连到维护库 postgres 执行 DROP DATABASE ... WITH (FORCE)。
# 复用于：① services-up dev 模式启动 server 前重置（TS_TEST_RESET_DB=true）；② run-tests -Cleanup。
function Invoke-TestDatabaseDrop {
    param([string]$Reason = '清理', [string]$RepoRoot)
    if ($env:TS_DB_URL -notmatch '^postgresql(?:[^:]*)://([^:]+):([^@]+)@([^:]+):(\d+)/(.*)$') {
        Write-Host "  跳过数据库删除：TS_DB_URL 不是合法的 postgresql 连接串" -ForegroundColor Yellow
        return
    }
    $dbUser = $matches[1]; $dbPass = $matches[2]; $dbHost = $matches[3]; $dbPort = $matches[4]
    $dbName = ($matches[5] -split '\?')[0]
    Write-Host "  ${Reason}测试数据库: $dbName (@ ${dbHost}:${dbPort})" -ForegroundColor Cyan
    $dropScript = @"
import sys
from sqlalchemy import create_engine, text
try:
    engine = create_engine('postgresql://${dbUser}:${dbPass}@${dbHost}:${dbPort}/postgres?connect_timeout=5', isolation_level='AUTOCOMMIT')
    with engine.connect() as conn:
        conn.execute(text('DROP DATABASE IF EXISTS "$dbName" WITH (FORCE);'))
    print('  数据库 $dbName 已删除')
except Exception as e:
    print('  删除数据库失败: ' + str(e))
"@
    $uv = Resolve-Uv
    if ($uv) {
        Push-Location (Join-Path $RepoRoot 'package\server')
        try { & $uv run python -c $dropScript } finally { Pop-Location }
    } else {
        $py = Join-Path $RepoRoot 'package\server\.venv\Scripts\python.exe'
        if (Test-Path $py) {
            & $py -c $dropScript
        } else {
            Write-Host "  跳过数据库删除：找不到 uv 且 $py 不存在" -ForegroundColor Yellow
        }
    }
}

# AI 模型预热：轮询 POST $TS_AI_API_URL/embedding/text 到 200，确认 clip_text 已下载+加载。
# AI 容器 lifespan 后台并发下载模型；HTTP 起来不等于模型就绪。模型未就绪只 warn 不 fail
# （e2e 探针会自动 skip AI 用例，避免阻塞整条流水线）。
function Wait-AiReady {
    param([int]$TimeoutSeconds = 900)
    $aiUrl = $env:TS_AI_API_URL
    if (-not $aiUrl) {
        Write-Host "  跳过 AI 预热：TS_AI_API_URL 未设置" -ForegroundColor DarkGray
        return
    }
    # 死端口（65535 等）直接跳过，避免无意义轮询
    try {
        $aiPort = [int]([System.Uri]$aiUrl).Port
        if ($aiPort -in 65535, 0) {
            Write-Host "  跳过 AI 预热：TS_AI_API_URL=$aiUrl（死端口，本层不依赖 AI）" -ForegroundColor DarkGray
            return
        }
    } catch {}

    $interval = 2
    $attempts = [int]([math]::Max(1, [math]::Floor($TimeoutSeconds / $interval)))
    Write-Host "  预热 AI 模型（轮询 $aiUrl/embedding/text 直到 200，最多 ${TimeoutSeconds}s）..." -ForegroundColor Cyan
    for ($i = 1; $i -le $attempts; $i++) {
        try {
            $resp = Invoke-WebRequest -UseBasicParsing -Method Post -Uri "$aiUrl/embedding/text" `
                -ContentType 'application/json' -Body '{"texts":["warmup"]}' -TimeoutSec 30 `
                -ErrorAction Stop
            if ($resp.StatusCode -eq 200) {
                Write-Host "  AI 模型就绪（${i}x${interval}s）" -ForegroundColor Green
                return
            }
        } catch {
            # 连接拒绝 / 500（模型未就绪）→ 继续轮询
        }
        Start-Sleep -Seconds $interval
    }
    Write-Warning "AI 模型在 ${TimeoutSeconds}s 内未就绪；依赖 AI 的 e2e 用例将被探针跳过。"
}
