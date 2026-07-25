<#
.SYNOPSIS
    启动测试服务（dev 本地进程 或 docker compose 栈）。

.DESCRIPTION
    CI 与本地共用本脚本（由 run-tests.ps1 调用，也可单独运行）。
    -Mode dev    ：启动本地 uv/pnpm 进程（server / AI / frontend），端口幂等。
    -Mode docker ：docker compose up -d（tests/docker/docker-compose.yml）。
    两种模式都在服务端口就绪后做 AI 模型预热（轮询 /embedding/text 到 200），
    确保 e2e 的 AI 用例不会被未就绪的模型跳过。

    环境变量单一来源 tests/.env.test（由 Import-EnvFile 加载到会话，子进程继承）。

.PARAMETER EnvFile
    环境变量文件路径，默认 tests/.env.test。

.PARAMETER Mode
    dev | docker。不传则按 TS_TEST_ENV 推断：docker/ci → docker，否则 dev。

.PARAMETER Component
    server | ai | website | all。dev 模式下决定起哪些本地进程；docker 模式起整个栈。
#>
param(
    [string]$EnvFile,
    [ValidateSet('dev', 'docker')][string]$Mode,
    [ValidateSet('server', 'ai', 'website', 'all')][string]$Component = 'all'
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $EnvFile) { $EnvFile = Join-Path $RepoRoot 'tests\.env.test' }
if (-not [System.IO.Path]::IsPathRooted($EnvFile)) { $EnvFile = Join-Path $RepoRoot $EnvFile }
if (-not (Test-Path $EnvFile)) {
    Write-Host "找不到环境变量文件：$EnvFile" -ForegroundColor Red
    Write-Host "请先复制模板：Copy-Item 'tests\.env.test.example' 'tests\.env.test' 后按需编辑。" -ForegroundColor Yellow
    exit 1
}

. (Join-Path $PSScriptRoot 'Import-EnvFile.ps1')
Import-EnvFile -Path $EnvFile
. (Join-Path $PSScriptRoot 'test-services-lib.ps1')

if (-not $Mode) {
    $Mode = if ($env:TS_TEST_ENV -in 'docker', 'ci') { 'docker' } else { 'dev' }
}

$ArtifactsDir = Join-Path $RepoRoot 'tests\artifacts'
New-Item -ItemType Directory -Force -Path $ArtifactsDir | Out-Null

Write-Host "==> 启动测试服务  Mode=$Mode  Component=$Component  Env=$EnvFile" -ForegroundColor Cyan
Write-Host "  API=$($env:TS_API_BASE_URL)  Web=$($env:TS_WEB_BASE_URL)  AI=$($env:TS_AI_API_URL)  DB=$($env:TS_DB_URL)" -ForegroundColor DarkGray

# ===========================================================================
# dev 模式：本地进程
# ===========================================================================
if ($Mode -eq 'dev') {
    $apiUri = [System.Uri]$env:TS_API_BASE_URL
    $aiUri  = [System.Uri]$env:TS_AI_API_URL
    $webUri = [System.Uri]$env:TS_WEB_BASE_URL

    # 启动前清理占用服务端口的进程（上轮残留 / 手动 dev 服务 / 孤儿进程），
    # 保证后续 Test-Port 必为空闲 → 由本脚本统一拉起全新服务。
    $prePorts = Get-ServicePorts -Component $Component
    if ($prePorts.Count -gt 0) {
        Write-Host "  启动前清理占用服务端口的进程..." -ForegroundColor Cyan
        Clear-ServicePorts -Ports $prePorts -Reason '启动前清理'
        Start-Sleep -Milliseconds 500
    }

    $uv = Resolve-Uv
    if (-not $uv) { throw "找不到 uv（dev 模式需要 uv 启动 server/AI）" }
    $tag = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $serverLog = Join-Path $ArtifactsDir "server-$tag.log"
    $serverErr = Join-Path $ArtifactsDir "server-$tag.err"
    $aiLog = Join-Path $ArtifactsDir "ai-$tag.log"
    $aiErr = Join-Path $ArtifactsDir "ai-$tag.err"
    $webLog = Join-Path $ArtifactsDir "dev-$tag.log"
    $webErr = Join-Path $ArtifactsDir "dev-$tag.err"

    $started = @()

    # TS_TEST_RESET_DB=true 时启动 server 前先删库（全新数据）
    if (Test-ResetDbFlag) {
        Write-Host "  TS_TEST_RESET_DB=true，启动 server 前先删除目标测试库..." -ForegroundColor Cyan
        Invoke-TestDatabaseDrop -Reason '启动前重置' -RepoRoot $RepoRoot
    }

    # Server
    if ($Component -in 'server', 'all') {
        Write-Host "  启动 Server ($($apiUri.Port))..."
        $serverDir = Join-Path $RepoRoot "package\server"
        $proc = Start-Process -FilePath $uv `
            -ArgumentList @('run', 'python', 'start.py', '--port', "$($apiUri.Port)") `
            -WorkingDirectory $serverDir `
            -RedirectStandardOutput $serverLog -RedirectStandardError $serverErr `
            -WindowStyle Hidden -PassThru
        $started += $proc
    }

    # AI
    if ($Component -in 'ai', 'all') {
        Write-Host "  启动 AI 服务 ($($aiUri.Port))..."
        $aiDir = Join-Path $RepoRoot "package\ai"
        $proc = Start-Process -FilePath $uv `
            -ArgumentList @('run', 'uvicorn', 'main:app', '--host', '0.0.0.0', '--port', "$($aiUri.Port)") `
            -WorkingDirectory $aiDir `
            -RedirectStandardOutput $aiLog -RedirectStandardError $aiErr `
            -WindowStyle Hidden -PassThru
        $started += $proc
    }

    # Frontend
    if ($Component -in 'website', 'all') {
        Write-Host "  启动 Frontend ($($webUri.Port))..."
        $webDir = Join-Path $RepoRoot "package\website"
        $proc = Start-Process -FilePath "pnpm.cmd" `
            -ArgumentList @('dev', '--port', "$($webUri.Port)") `
            -WorkingDirectory $webDir `
            -RedirectStandardOutput $webLog -RedirectStandardError $webErr `
            -WindowStyle Hidden -PassThru
        $started += $proc
    }

    # 等待端口就绪
    if ($started.Count -gt 0) {
        Write-Host "  等待服务就绪..." -ForegroundColor Cyan
        $maxWait = 60
        while ($maxWait -gt 0) {
            $serverReady = if ($Component -in 'server', 'all') { Test-Port $apiUri.Port } else { $true }
            $aiReady     = if ($Component -in 'ai', 'all')     { Test-Port $aiUri.Port }  else { $true }
            $webReady    = if ($Component -in 'website', 'all'){ Test-Port $webUri.Port } else { $true }
            if ($serverReady -and $aiReady -and $webReady) { break }
            Start-Sleep -Seconds 1
            $maxWait--
        }
        if ($maxWait -eq 0) {
            $failed = @()
            if (-not $serverReady) { $failed += "Server:$($apiUri.Port)" }
            if (-not $aiReady)     { $failed += "AI:$($aiUri.Port)" }
            if (-not $webReady)    { $failed += "Frontend:$($webUri.Port)" }
            throw "本地服务启动超时：$($failed -join ', ')。日志见 $ArtifactsDir。"
        }
        Write-Host "  服务端口已就绪" -ForegroundColor Green
    }

    # AI 模型预热（dev 模式同样需要，确保模型加载完成）
    if ($Component -in 'ai', 'all') { Wait-AiReady }
}
# ===========================================================================
# docker 模式：compose 栈
# ===========================================================================
elseif ($Mode -eq 'docker') {
    $composeFile = Join-Path $RepoRoot 'tests\docker\docker-compose.yml'
    if (-not (Test-Path $composeFile)) { throw "找不到 compose 文件：$composeFile" }

    $apiUri = [System.Uri]$env:TS_API_BASE_URL
    if (Test-Port $apiUri.Port) {
        Write-Host "  服务端口 $($apiUri.Port) 已被占用，假设栈已在运行，跳过启动。" -ForegroundColor Yellow
    } else {
        Write-Host "  docker compose up -d（$composeFile）..." -ForegroundColor Cyan
        & docker compose -f $composeFile --env-file $EnvFile up -d
        if ($LASTEXITCODE -ne 0) { throw "docker compose up 失败，退出码 $LASTEXITCODE" }

        # 等 server health-check
        Write-Host "  等待 server health-check..." -ForegroundColor Cyan
        $maxWait = 90
        while ($maxWait -gt 0) {
            if (Test-Port $apiUri.Port) { break }
            Start-Sleep -Seconds 2
            $maxWait--
        }
        if ($maxWait -eq 0) {
            & docker compose -f $composeFile --env-file $EnvFile logs --tail=80
            throw "server 容器未在 180s 内监听 $($apiUri.Port)。"
        }
        Write-Host "  server 已就绪" -ForegroundColor Green
    }

    # AI 模型预热（docker 栈里 AI 容器后台下载模型）
    Wait-AiReady
}

Write-Host "==> 服务启动完成" -ForegroundColor Green
