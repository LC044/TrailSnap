<#
.SYNOPSIS
    TrailSnap 测试统一入口。

.DESCRIPTION
    一个命令驱动 docker / 前端 e2e / 后端单元 / AI 四类测试。
    环境变量单一来源：环境变量文件（默认 tests/.env.test）—— 先加载到会话，
    子进程（uv / pnpm / docker）全部继承。可用第一个位置参数指定别的 .env 文件。
    E2E 可通过 -ScanPrep auto|true|false 显式控制是否先执行 scan 预扫描；
    命令行参数优先级高于 .env 文件中的 TS_E2E_ENABLE_FIXTURE_SCAN。

    四个维度组合：
      EnvFile    第一个位置参数，环境变量文件路径，不传则默认 tests\.env.test
      -Layer     unit | integration | e2e | docker | all   （测哪一层）
      -Component server | ai | website | all               （测哪个组件）
      -Cover     smoke | regression | full                 （跑多深，默认读 .env 文件的 TS_TEST_COVER）
                 unit/integration → pytest -m 标记；e2e → smoke=@smoke / regression=@p0 + P1 / full=全部
      -Scope     all | photo | album | face | ocr | ...     （跑哪个业务域）
      -ScanPrep  auto | true | false                        （e2e 是否先执行 scan；默认 false）

    最简打通流程：
      .\tests\scripts\run-tests.ps1                         # 默认 = server+ai 的 smoke 单元测试

.PARAMETER EnvFile
    环境变量文件路径（第一个位置参数）。不传则默认 tests\.env.test。
    相对路径以仓库根为基准解析。

.PARAMETER Layer
    unit       后端/AI 纯函数与契约测试（无外部服务，秒级）
    integration后端集成测试（需 DB，见 conftest 的 sqlite/pg fixture）
    e2e        前端 Playwright（按 TS_E2E_SUITE 选套件；dev/p0 套件 globalSetup 自动登录一次）
    docker     启动 docker-compose.test.yml 测试栈
    all        unit + e2e 串行

.EXAMPLE
    .\tests\scripts\run-tests.ps1                                        # 默认 env 文件 + smoke 单元
    .\tests\scripts\run-tests.ps1 tests\.env.docker                      # 指定别的 env 文件
    .\tests\scripts\run-tests.ps1 -Layer e2e                             # e2e，Cover 默认 smoke → 仅 @smoke
    .\tests\scripts\run-tests.ps1 -Layer e2e -ScanPrep true              # 先执行 scan 预扫描，再跑 e2e
    .\tests\scripts\run-tests.ps1 -Layer e2e -ScanPrep false             # 显式关闭预扫描，覆盖 .env 设置
    .\tests\scripts\run-tests.ps1 -Layer e2e -Cover regression           # e2e 功能用例（@p0 + P1）
    .\tests\scripts\run-tests.ps1 -Layer e2e -Cover full                 # e2e 全部用例（不加 grep）
    .\tests\scripts\run-tests.ps1 tests\.env.docker -Layer docker        # 用 docker 配置起栈
    .\tests\scripts\run-tests.ps1 -Layer unit -Component server -Cover smoke -Scope album

.NOTES
    e2e dev/p0 套件由 globalSetup 自动登录一次（账号取自 TS_TEST_USERNAME/TS_TEST_PASSWORD，
    默认 e2e-admin）。dev 库若无该账号且 allow_registration=false，受保护页面用例会 skip；
    可临时把 TS_TEST_USERNAME/PASSWORD 指向已有的管理员账号。
    smoke/p0/p1 套件分离：@smoke = 页面打开，@p0 = 功能可用，P1 = 业务深测。
    -ScanPrep=true|false 会直接覆盖 .env 的 TS_E2E_ENABLE_FIXTURE_SCAN；
    仅当 -ScanPrep=auto 时才回退到 .env 或默认 false。
#>
[CmdletBinding()]
param(
    # 第一个位置参数：环境变量文件路径，不传则默认 tests\.env.test
    [Parameter(Position = 0)]
    [string]$EnvFile,

    [ValidateSet('unit', 'integration', 'e2e', 'docker', 'all')]
    [string]$Layer = 'unit',

    [ValidateSet('server', 'ai', 'website', 'all')]
    [string]$Component = 'all',

    [string]$Cover,

    [string]$Scope,

    [ValidateSet('auto', 'true', 'false')]
    [string]$ScanPrep = 'auto',

    [switch]$Cleanup
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $EnvFile) { $EnvFile = Join-Path $RepoRoot 'tests\.env.test' }
# 允许相对路径：以仓库根为基准解析
if (-not [System.IO.Path]::IsPathRooted($EnvFile)) {
    $EnvFile = (Resolve-Path (Join-Path $RepoRoot $EnvFile) -ErrorAction Stop).Path
}

# 1) 加载单一数据源到会话 —— 四方共享的关键
. (Join-Path $PSScriptRoot 'Import-EnvFile.ps1')
Import-EnvFile -Path $EnvFile

# 2) 档位回退：命令行未传则读 .env.test，再不行用默认
if (-not $Cover) { $Cover = if ($env:TS_TEST_COVER) { $env:TS_TEST_COVER } else { 'smoke' } }
if (-not $Scope) { $Scope = if ($env:TS_TEST_SCOPE) { $env:TS_TEST_SCOPE } else { 'all' } }
switch ($ScanPrep) {
    'true'  { $env:TS_E2E_ENABLE_FIXTURE_SCAN = 'true' }
    'false' { $env:TS_E2E_ENABLE_FIXTURE_SCAN = 'false' }
    default {
        if (-not $env:TS_E2E_ENABLE_FIXTURE_SCAN) { $env:TS_E2E_ENABLE_FIXTURE_SCAN = 'false' }
    }
}

# 把 TS_TEST_RESET_DB 解析为布尔：true/1/yes 视为开启，其余（含空/false）为关闭。
# 定义在 banner 之前，因为 banner 就要调用它打印状态。
function Test-ResetDbFlag {
    $v = $env:TS_TEST_RESET_DB
    if (-not $v) { return $false }
    return @('true', '1', 'yes') -contains $v.Trim().ToLower()
}

# 把 TS_TEST_KEEP_SERVICES 解析为布尔：true/1/yes 视为开启，其余（含空/false）为关闭。
# 同样定义在 banner 之前以便打印状态。
function Test-KeepServicesFlag {
    $v = $env:TS_TEST_KEEP_SERVICES
    if (-not $v) { return $false }
    return @('true', '1', 'yes') -contains $v.Trim().ToLower()
}

Write-Host ""
Write-Host "==== TrailSnap 测试入口 ====" -ForegroundColor Cyan
Write-Host "  TS_TEST_ENV = $($env:TS_TEST_ENV)"
Write-Host "  Layer       = $Layer"
Write-Host "  Component   = $Component"
Write-Host "  Cover       = $Cover"
Write-Host "  Scope       = $Scope"
Write-Host "  ScanPrepArg = $ScanPrep"
Write-Host "  API         = $($env:TS_API_BASE_URL)"
Write-Host "  Web         = $($env:TS_WEB_BASE_URL)"
Write-Host "  AI          = $($env:TS_AI_API_URL)"
Write-Host "  DB          = $($env:TS_DB_URL)"
Write-Host "  ScanPrep    = $($env:TS_E2E_ENABLE_FIXTURE_SCAN)"
Write-Host "  ResetDB     = $(if (Test-ResetDbFlag) { 'true (启动 server 前删库)' } else { 'false' })"
Write-Host "  KeepSvcs    = $(if (Test-KeepServicesFlag) { 'true (测后保留服务)' } else { 'false (测后关闭)' })"
Write-Host "============================" -ForegroundColor Cyan
Write-Host ""

# 把 Cover/Scope 组合成 pytest -m 表达式
#   smoke + album -> "smoke and module_album"
#   full / all    -> 不加 -m（跑全部）
function Get-MarkerArg {
    param([string]$c, [string]$s)
    $parts = @()
    if ($c -and $c -ne 'full') { $parts += $c }
    if ($s -and $s -ne 'all') { $parts += "module_$s" }
    if ($parts.Count -eq 0) { return @() }
    return @('-m', ($parts -join ' and '))
}

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

function Invoke-Pytest {
    param([string]$PackageDir, [string]$TestPath, [string[]]$ExtraArgs)
    $pkgAbs = Join-Path $RepoRoot $PackageDir
    Push-Location $pkgAbs
    try {
        $uv = Resolve-Uv
        if ($uv) {
            & $uv run python -m pytest $TestPath @ExtraArgs -v
        }
        else {
            # 回退：直接用包内 venv 的 python（CI 或无 uv 时）
            $py = Join-Path $pkgAbs '.venv\Scripts\python.exe'
            if (-not (Test-Path $py)) { throw "找不到 uv，且 $py 不存在" }
            & $py -m pytest $TestPath @ExtraArgs -v
        }
        if ($LASTEXITCODE -ne 0) { throw "pytest 失败 ($PackageDir)，退出码 $LASTEXITCODE" }
    }
    finally { Pop-Location }
}

# 删除 TS_DB_URL 指向的目标库：连到维护库 postgres 执行 DROP DATABASE ... WITH (FORCE)。
# 复用于两处：① 启动 server 前重置（TS_TEST_RESET_DB=true）；② 测试结束后清理（-Cleanup）。
function Invoke-TestDatabaseDrop {
    param([string]$Reason = '清理')
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
    engine = create_engine('postgresql://${dbUser}:${dbPass}@${dbHost}:${dbPort}/postgres', isolation_level='AUTOCOMMIT')
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

# 计算本次运行“关心的”服务端口（与启动逻辑一致：server + ai，web 仅当 Component 含 website）
function Get-ServicePorts {
    param([string]$Component)
    $ports = @()
    if ($env:TS_API_BASE_URL) { try { $ports += [int]([System.Uri]$env:TS_API_BASE_URL).Port } catch {} }
    if ($env:TS_AI_API_URL)   { try { $ports += [int]([System.Uri]$env:TS_AI_API_URL).Port } catch {} }
    if ($Component -in 'website', 'all' -and $env:TS_WEB_BASE_URL) {
        try { $ports += [int]([System.Uri]$env:TS_WEB_BASE_URL).Port } catch {}
    }
    return ($ports | Sort-Object -Unique)
}

# 杀掉占用指定端口的进程（含其子进程树）。用于：启动前清理 + 测试后兜底清理。
function Clear-ServicePorts {
    param([int[]]$Ports, [string]$Reason = '清理')
    foreach ($port in ($Ports | Sort-Object -Unique)) {
        $conns = @()
        try { $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue } catch {}
        foreach ($c in $conns) {
            $holderPid = $c.OwningProcess
            if (-not $holderPid) { continue }
            try { $holder = Get-Process -Id $holderPid -ErrorAction Stop } catch { continue }
            Write-Host "  [$Reason] 端口 $port <- PID $holderPid ($($holder.ProcessName))，强制关闭进程树..." -ForegroundColor Yellow
            & taskkill /F /T /PID $holderPid 2>&1 | Out-Null
        }
    }
}

$exitCode = 0
$startedProcesses = @()
$startedDocker = $false
$localServiceMode = $false

try {
    # ---------- 启动服务 (根据环境) ----------
    if ($Layer -in 'e2e', 'integration', 'all') {
        if ($env:TS_TEST_ENV -eq 'dev') {
            Write-Host "==> 检查并启动本地开发服务..." -ForegroundColor Cyan
            $localServiceMode = $true

            # 启动前确保服务端口空闲：杀掉任何占用者（上轮残留 / 手动 dev 服务 / 孤儿进程）。
            # 这样后续 Test-Port 必为空闲 → 由本脚本统一拉起全新服务。
            $prePorts = Get-ServicePorts -Component $Component
            if ($prePorts.Count -gt 0) {
                Write-Host "  启动前清理占用服务端口的进程..." -ForegroundColor Cyan
                Clear-ServicePorts -Ports $prePorts -Reason '启动前清理'
                Start-Sleep -Milliseconds 500
            }

            $apiUri = [System.Uri]$env:TS_API_BASE_URL
            $resetDb = Test-ResetDbFlag
            if (-not (Test-Port $apiUri.Port)) {
                if ($resetDb) {
                    Write-Host "  TS_TEST_RESET_DB=true，启动 server 前先删除目标测试库..." -ForegroundColor Cyan
                    Invoke-TestDatabaseDrop -Reason '启动前重置'
                }
                Write-Host "  启动 Server ($($apiUri.Port))..."
                $proc = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "uv", "run", "python", "start.py", "--port", "$($apiUri.Port)" -WorkingDirectory (Join-Path $RepoRoot "package\server") -WindowStyle Hidden -PassThru
                $startedProcesses += $proc
            } elseif ($resetDb) {
                Write-Host "  警告：TS_TEST_RESET_DB=true，但 server 端口 $($apiUri.Port) 已被占用（服务已在运行），跳过重置以免破坏运行中的服务。先停掉该端口服务再重试。" -ForegroundColor Yellow
            }

            $aiUri = [System.Uri]$env:TS_AI_API_URL
            if (-not (Test-Port $aiUri.Port)) {
                Write-Host "  启动 AI 服务 ($($aiUri.Port))..."
                $proc = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "$($aiUri.Port)" -WorkingDirectory (Join-Path $RepoRoot "package\ai") -WindowStyle Hidden -PassThru
                $startedProcesses += $proc
            }

            if ($Component -in 'website', 'all') {
                $webUri = [System.Uri]$env:TS_WEB_BASE_URL
                if (-not (Test-Port $webUri.Port)) {
                    Write-Host "  启动 Frontend ($($webUri.Port))..."
                    $proc = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "pnpm", "dev", "--port", "$($webUri.Port)" -WorkingDirectory (Join-Path $RepoRoot "package\website") -WindowStyle Hidden -PassThru
                    $startedProcesses += $proc
                }
            }

            if ($startedProcesses.Count -gt 0) {
                Write-Host "  等待服务就绪..."
                $maxWait = 30
                while ($maxWait -gt 0) {
                    $serverReady = Test-Port $apiUri.Port
                    $aiReady = Test-Port $aiUri.Port
                    $webReady = if ($Component -in 'website', 'all') { Test-Port $webUri.Port } else { $true }
                    
                    if ($serverReady -and $aiReady -and $webReady) { break }
                    Start-Sleep -Seconds 1
                    $maxWait--
                }
                if ($maxWait -eq 0) {
                    Write-Host "  警告: 部分服务启动超时，可能影响测试！" -ForegroundColor Yellow
                } else {
                    Write-Host "  服务已就绪！" -ForegroundColor Green
                }
            }
        } elseif ($env:TS_TEST_ENV -in 'docker', 'ci') {
            Write-Host "==> 检查 Docker 服务状态..." -ForegroundColor Cyan
            $apiUri = [System.Uri]$env:TS_API_BASE_URL
            if (-not (Test-Port $apiUri.Port)) {
                Write-Host "  启动 Docker 测试栈..."
                $composeFile = Join-Path $RepoRoot 'tests\docker\docker-compose.test.yml'
                & docker compose -f $composeFile --env-file $EnvFile up -d
                if ($LASTEXITCODE -ne 0) { throw "docker compose 启动失败，退出码 $LASTEXITCODE" }
                $startedDocker = $true
                Start-Sleep -Seconds 10
            }
        }
    }

    # ---------- unit / integration（pytest）----------
    if ($Layer -in 'unit', 'integration', 'all') {
        $markerArg = Get-MarkerArg -c $Cover -s $Scope
        $testPath = if ($Layer -eq 'integration') { 'tests/integration' } else { 'tests/unit' }
        $aiTestPath = if ($Layer -eq 'integration') { 'tests' } else { 'tests' }

        if ($Component -in 'server', 'all') {
            Write-Host "==> 后端 $Layer 测试 (server)" -ForegroundColor Green
            Invoke-Pytest -PackageDir 'package\server' -TestPath $testPath -ExtraArgs $markerArg
        }
        if ($Component -in 'ai', 'all') {
            Write-Host "==> AI $Layer 测试 (ai)" -ForegroundColor Green
            Invoke-Pytest -PackageDir 'package\ai' -TestPath $aiTestPath -ExtraArgs $markerArg
        }
    }

    # ---------- e2e（Playwright，env 已注入，e2e-env.ts 自动读取）----------
    if ($Layer -in 'e2e', 'all') {
        if ($Component -in 'website', 'all') {
            # TS_TEST_RESET_DB=true 时每轮都是新空库，但 photo-fixtures 的 state cache
            # 落盘且跨轮稳定（dev 套件经 pnpm test:e2e 跑，TS_E2E_PREP_RUN_ID 缺省='default'），
            # 上轮 ok=true 会让本轮 globalSetup 跳过扫描 → 空库无照片。
            # 给本轮注入唯一 prep run id：跨轮指纹失效 → 强制重扫；同一轮内 globalSetup 与
            # 00-setup 共享该 id → 仍命中缓存避免重复扫描。RESET_DB=false 时维持 'default'，
            # 保留跨轮缓存命中、避免无谓重扫。
            if (Test-ResetDbFlag -and -not $env:TS_E2E_PREP_RUN_ID) {
                $env:TS_E2E_PREP_RUN_ID = "reset-$([System.Guid]::NewGuid().ToString('N').Substring(0,12))"
                Write-Host "  TS_TEST_RESET_DB=true → 本轮 TS_E2E_PREP_RUN_ID=$($env:TS_E2E_PREP_RUN_ID)（强制重扫夹具）" -ForegroundColor DarkGray
            }

            $e2eSuite = if ($env:TS_E2E_SUITE) { $env:TS_E2E_SUITE.ToLower() } else { 'dev' }
            Write-Host "==> 前端 E2E (website)  suite=$e2eSuite  cover=$Cover" -ForegroundColor Green
            Push-Location (Join-Path $RepoRoot 'package\website')
            try {
                switch ($e2eSuite) {
                    'smoke' { & node playwright/run-e2e.mjs smoke }
                    'p0'    { & node playwright/run-e2e.mjs p0 }
                    'p1'    { & node playwright/run-e2e.mjs p1 }
                    'all'   { & node playwright/run-e2e.mjs all }
                    'light' { & node playwright/run-e2e.mjs light }
                    'full'  { & node playwright/run-e2e.mjs full }
                    default {
                        $grepArg = switch ($Cover) {
                            'smoke' { '@smoke' }
                            'regression' { '@p0|P1 - ' }
                            default { $null }
                        }
                        if ($grepArg) { & pnpm test:e2e --grep $grepArg }
                        else { & pnpm test:e2e }
                    }
                }
                if ($LASTEXITCODE -ne 0) { throw "playwright 失败，退出码 $LASTEXITCODE" }
            }
            finally { Pop-Location }
        }
    }

    # ---------- docker（启动测试栈）----------
    if ($Layer -eq 'docker') {
        Write-Host "==> 启动 Docker 测试栈" -ForegroundColor Green
        $composeFile = Join-Path $RepoRoot 'tests\docker\docker-compose.test.yml'
        & docker compose -f $composeFile --env-file $EnvFile up -d
        if ($LASTEXITCODE -ne 0) { throw "docker compose 启动失败，退出码 $LASTEXITCODE" }
        Write-Host "Docker 测试栈已启动。停止：docker compose -f `"$composeFile`" down -v" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "==== 全部通过 ====" -ForegroundColor Green
}
catch {
    Write-Host ""
    Write-Host "==== 测试失败：$($_.Exception.Message) ====" -ForegroundColor Red
    $exitCode = 1
}
finally {
    $keepServices = Test-KeepServicesFlag

    # ---- 数据库清理（-Cleanup）----
    # 保留服务模式下跳过删库：运行中的 server 仍连着库，DROP 会破坏其状态，
    # 且与“保留现场供查看”的意图冲突。
    if ($Cleanup) {
        if ($keepServices) {
            Write-Host "==> 跳过 -Cleanup 数据库删除（TS_TEST_KEEP_SERVICES=true，保留服务与数据）" -ForegroundColor Yellow
        } else {
            Write-Host ""
            Write-Host "==> 清理测试环境..." -ForegroundColor Cyan
            Invoke-TestDatabaseDrop -Reason '测试后清理'
        }
    }

    # ---- Docker 测试栈 ----
    if ($startedDocker) {
        if ($keepServices) {
            Write-Host "==> TS_TEST_KEEP_SERVICES=true，保留 Docker 测试栈运行（未执行 down）" -ForegroundColor Green
        } else {
            Write-Host "==> 停止 Docker 测试栈..." -ForegroundColor Cyan
            $composeFile = Join-Path $RepoRoot 'tests\docker\docker-compose.test.yml'
            & docker compose -f $composeFile --env-file $EnvFile down -v
        }
    }

    # ---- 本地服务 ----
    if ($keepServices) {
        # 保留模式：不关闭本次启动的服务，打印仍在运行的 PID / 端口供查看
        if ($startedProcesses.Count -gt 0) {
            Write-Host "==> TS_TEST_KEEP_SERVICES=true，保留服务运行（不关闭）：" -ForegroundColor Green
            foreach ($proc in $startedProcesses) {
                try { $proc.Refresh() } catch {}
                if ($proc -and -not $proc.HasExited) {
                    Write-Host "  PID $($proc.Id) 仍在运行"
                }
            }
            $keepPorts = Get-ServicePorts -Component $Component
            if ($keepPorts.Count -gt 0) {
                Write-Host "  端口: $($keepPorts -join ', ')"
            }
            Write-Host "  手动停止: taskkill /F /T /PID <pid>，或下次运行会自动清理这些端口" -ForegroundColor DarkGray
        }
    }
    else {
        # 关闭模式：两步——
        #   1) taskkill /F /T 杀掉记录在册的 cmd.exe 包装进程的整棵树
        #      （含 uv → uvicorn → worker / llama-server 等直接子进程）。
        #   2) 按本次运行关心的全部服务端口做兜底清扫：凡仍占用这些端口的
        #      进程一律强制关闭进程树。覆盖包装进程早退 / uv 中间断链导致子进程
        #      被 reparent 成孤儿等情况。仅在 dev 本地服务模式下执行。
        if ($startedProcesses.Count -gt 0) {
            Write-Host "==> 关闭启动的本地服务..." -ForegroundColor Cyan
            foreach ($proc in $startedProcesses) {
                try { $proc.Refresh() } catch {}
                if ($proc -and -not $proc.HasExited) {
                    Write-Host "  关闭进程树 PID: $($proc.Id)"
                    & taskkill /F /T /PID $proc.Id 2>&1 | Out-Null
                }
            }
            Start-Sleep -Milliseconds 500
        }

        if ($localServiceMode) {
            Clear-ServicePorts -Ports (Get-ServicePorts -Component $Component) -Reason '测试后清理'
        }
    }
}

exit $exitCode
