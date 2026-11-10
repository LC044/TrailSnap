<#
.SYNOPSIS
    TrailSnap 文件夹扫描性能测试（一键启动空白测试库）。

.DESCRIPTION
    一行命令完成“启动服务 -> 重置测试库 -> 添加扫描目录 -> 统计任务耗时 ->
    清理环境 -> 输出报告”。底层复用 tests/scripts/services-up.ps1 /
    services-down.ps1 与 tests/performance/scan_folder_benchmark.py。

    默认只启动 server，不启动 AI 和前端；benchmark 会暂停 AI 任务类型，
    只测 SCAN_FOLDER -> PROCESS_BASIC -> EXTRACT_METADATA 本地链路。
    完整 AI 链路是后续扩展项，当前版本不纳入本基准。

    报告默认写入 tests/artifacts/performance/<run-id>/：
      - report.md    人类可读报告
      - report.json  完整原始指标
      - tasks.csv    每个任务的耗时明细
      - console.log  benchmark 控制台输出
      - server.log   本次启动的 server 日志（若可定位）

.PARAMETER EnvFile
    环境变量文件，默认 tests/.env.test。数据库/端口等均从该文件读取。

.PARAMETER Mode
    dev | docker。性能测试当前仅支持 dev 本地进程模式。

.PARAMETER Photos
    生成测试照片的数量，默认 100。用 -SourceFolder 时忽略。

.PARAMETER SourceFolder
    复用已有照片目录做扫描性能测试；不传则自动生成可复现的合成 JPEG。

.PARAMETER KeepServices
    测后保留 server 进程，方便查看现场。隐含 -KeepDatabase。

.PARAMETER KeepDatabase
    测后不删除测试库。默认删除（且只允许库名含 test/perf/ci 的测试库）。

.PARAMETER KeepFixture
    保留自动生成的测试照片目录（默认测后删除）。

.PARAMETER OutputDir
    报告目录的精确路径；不传则自动使用 tests/artifacts/performance/<run-id>。

.PARAMETER TimeoutSeconds
    等待扫描 + 本地处理链路排空的最长秒数，默认 300。

.PARAMETER StallSeconds
    扫描结束后，连续多少秒没有任何核心任务完成就判定“停滞”并提前收尾。
    默认 120 秒。

.EXAMPLE
    pwsh .\tests\scripts\run-perf.ps1

.EXAMPLE
    pwsh .\tests\scripts\run-perf.ps1 -Photos 200

.EXAMPLE
    pwsh .\tests\scripts\run-perf.ps1 -SourceFolder 'D:\Photos\sample'

.EXAMPLE
    pwsh .\tests\scripts\run-perf.ps1 -KeepServices -KeepDatabase
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$EnvFile,

    [ValidateSet('dev', 'docker')]
    [string]$Mode = 'dev',

    [ValidateRange(1, 100000)]
    [int]$Photos = 100,

    [string]$SourceFolder,

    [switch]$KeepServices,

    [switch]$KeepDatabase,

    [switch]$KeepFixture,

    [string]$OutputDir,

    [ValidateRange(10, 86400)]
    [int]$TimeoutSeconds = 300,

    [ValidateRange(0, 3600)]
    [int]$StallSeconds = 120
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..' '..')).Path
if (-not $EnvFile) { $EnvFile = Join-Path $RepoRoot 'tests' '.env.test' }
if (-not [System.IO.Path]::IsPathRooted($EnvFile)) { $EnvFile = Join-Path $RepoRoot $EnvFile }
if (-not (Test-Path $EnvFile)) {
    Write-Host "找不到环境变量文件：$EnvFile" -ForegroundColor Red
    Write-Host "请先从模板复制：Copy-Item 'tests/.env.test.example' 'tests/.env.test'" -ForegroundColor Yellow
    exit 1
}
if ($Mode -eq 'docker') {
    throw '性能测试当前仅支持 -Mode dev；docker 模式的宿主机照片目录映射尚未纳入基准。'
}
if ($KeepServices) { $KeepDatabase = $true }

. (Join-Path $PSScriptRoot 'Import-EnvFile.ps1')
Import-EnvFile -Path $EnvFile
. (Join-Path $PSScriptRoot 'test-services-lib.ps1')

# 本脚本会调用 Python 子进程（benchmark / 删库助手），Windows 控制台默认
# 按本地代码页解码 UTF-8 stdout，中文会变成乱码。统一按 UTF-8 解码。
$previousConsoleEncoding = [Console]::OutputEncoding
$previousOutputEncoding = $OutputEncoding
$previousPythonIoEncodingGlobal = $env:PYTHONIOENCODING
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING = 'utf-8'

$runId = Get-Date -Format 'yyyyMMdd-HHmmss'
if (-not $OutputDir) {
    $OutputDir = Join-Path $RepoRoot 'tests' 'artifacts' 'performance' $runId
} elseif (-not [System.IO.Path]::IsPathRooted($OutputDir)) {
    $OutputDir = Join-Path $RepoRoot $OutputDir
}
$reportDir = [System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
$consoleLog = Join-Path $reportDir 'console.log'
$runStarted = Get-Date

if ($SourceFolder) {
    if (-not (Test-Path $SourceFolder -PathType Container)) {
        Write-Host "找不到照片目录：$SourceFolder" -ForegroundColor Red
        exit 1
    }
    $sourceFolderPath = (Resolve-Path $SourceFolder).Path
}

# 一键入口的默认语义：全新空白库；测后（默认）删库并关服务。
$env:TS_TEST_RESET_DB = if ($KeepDatabase) { 'false' } else { 'true' }
$env:TS_TEST_KEEP_SERVICES = if ($KeepServices) { 'true' } else { 'false' }
$env:TS_PERF_RUN_ID = $runId
$env:TS_PERF_PHOTO_COUNT = "$Photos"
$env:TS_PERF_TIMEOUT_SECONDS = "$TimeoutSeconds"
$env:TS_PERF_STALL_SECONDS = "$StallSeconds"
if ($sourceFolderPath) { $env:TS_PERF_SOURCE_FOLDER = $sourceFolderPath }
else { Remove-Item Env:TS_PERF_SOURCE_FOLDER -ErrorAction SilentlyContinue }
if ($KeepFixture) { $env:TS_PERF_KEEP_FIXTURE = 'true' } else { Remove-Item Env:TS_PERF_KEEP_FIXTURE -ErrorAction SilentlyContinue }

$component = 'server'
$benchmark = Join-Path $RepoRoot 'tests' 'performance' 'scan_folder_benchmark.py'
$exitCode = 0

# 启动前的重置发生在 services-up 内部；这里先做一次同样的库名安全校验，
# 避免误配的 TS_DB_URL 在启动阶段就被 DROP。SQLite 的删除在共享函数里
# 另有限定 tests/artifacts 的路径守卫。
if (-not $KeepDatabase -and $env:TS_DB_URL -match '^postgresql(?:[^:]*)://[^/]+/([^?]+)') {
    $dbName = $matches[1]
    if ($dbName -notmatch '(?i)(test|perf|ci)') {
        Write-Host "拒绝重置非测试库：$dbName（库名需包含 test/perf/ci）。" -ForegroundColor Red
        Write-Host '如只想保留数据，请使用 -KeepDatabase；如确要测试，请修改 TS_DB_URL。' -ForegroundColor Yellow
        exit 1
    }
}

Write-Host ''
Write-Host '==== TrailSnap 文件夹扫描性能测试 ====' -ForegroundColor Cyan
Write-Host "  Env       = $EnvFile"
Write-Host "  Mode      = $Mode"
Write-Host "  Component = $component"
Write-Host "  Photos    = $(if ($sourceFolderPath) { "已有目录 $sourceFolderPath" } else { $Photos })"
Write-Host "  AI tasks  = 暂停（只测本地链路）"
Write-Host "  Timeout   = ${TimeoutSeconds}s (stall=${StallSeconds}s)"
Write-Host "  ResetDB   = $(if ($KeepDatabase) { 'false' } else { 'true' })"
Write-Host "  API       = $($env:TS_API_BASE_URL)"
Write-Host "  DB        = $($env:TS_DB_URL)"
Write-Host "  Report    = $reportDir"
Write-Host '======================================' -ForegroundColor Cyan
Write-Host ''

try {
    & (Join-Path $PSScriptRoot 'services-up.ps1') -EnvFile $EnvFile -Mode $Mode -Component $component -PreserveExisting
    if ($LASTEXITCODE -ne 0) { throw "services-up 失败，退出码 $LASTEXITCODE" }

    $uv = Resolve-Uv
    if (-not $uv) { throw '找不到 uv；性能测试需要 package/server 的 uv 环境' }

    $benchArgs = @(
        'run', 'python', $benchmark,
        '--report-dir', $reportDir,
        '--run-id', $runId,
        '--timeout-seconds', "$TimeoutSeconds",
        '--stall-seconds', "$StallSeconds"
    )
    if ($sourceFolderPath) {
        $benchArgs += @('--source-folder', $sourceFolderPath)
    }
    else {
        $benchArgs += @('--photo-count', "$Photos")
    }
    if ($KeepFixture) { $benchArgs += '--keep-fixture' }

    Write-Host "==> 执行性能基准（日志：$consoleLog）" -ForegroundColor Green
    Push-Location (Join-Path $RepoRoot 'package' 'server')
    $previousPythonIoEncoding = $env:PYTHONIOENCODING
    try {
        $env:PYTHONIOENCODING = 'utf-8'
        & $uv @benchArgs 2>&1 | Tee-Object -FilePath $consoleLog
        $exitCode = $LASTEXITCODE
    }
    finally {
        if ($null -eq $previousPythonIoEncoding) {
            Remove-Item Env:PYTHONIOENCODING -ErrorAction SilentlyContinue
        }
        else {
            $env:PYTHONIOENCODING = $previousPythonIoEncoding
        }
        Pop-Location
    }

    if ($exitCode -ne 0) {
        Write-Host "==> 性能测试返回非零退出码: $exitCode（报告仍会保留）" -ForegroundColor Yellow
    }
}
catch {
    Write-Host "==> 性能测试异常：$($_.Exception.Message)" -ForegroundColor Red
    $exitCode = 1
}
finally {
    # 先关服务再删库，避免 server 在删库后继续写日志/重连。
    if (-not $KeepServices) {
        try {
            & (Join-Path $PSScriptRoot 'services-down.ps1') -EnvFile $EnvFile -Mode $Mode -Component $component -PreserveExisting
        }
        catch {
            Write-Host "  services-down 失败：$($_.Exception.Message)" -ForegroundColor Yellow
        }
    }

    if (-not $KeepDatabase) {
        try {
            Invoke-TestDatabaseDrop -Reason '性能测试后清理' -RepoRoot $RepoRoot -RequireTestName
        }
        catch {
            Write-Host "  测试库清理失败：$($_.Exception.Message)" -ForegroundColor Yellow
            if ($exitCode -eq 0) { $exitCode = 1 }
        }
    }
    else {
        Write-Host '==> 保留测试库（-KeepDatabase / -KeepServices）' -ForegroundColor Yellow
    }

    # 把本次 server 日志一并放进报告目录，方便回看启动/任务异常。
    try {
        $serverLog = Get-ChildItem (Join-Path $RepoRoot 'tests' 'artifacts') -Filter 'server-*.log' -File |
            Where-Object { $_.LastWriteTime -ge $runStarted } |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if ($serverLog) {
            Copy-Item $serverLog.FullName (Join-Path $reportDir 'server.log') -Force
        }
    }
    catch {
        Write-Host "  收集 server 日志失败：$($_.Exception.Message)" -ForegroundColor DarkYellow
    }

    $reportMd = Join-Path $reportDir 'report.md'
    $reportJson = Join-Path $reportDir 'report.json'
    if (-not (Test-Path $reportMd)) {
        @(
            '# TrailSnap 文件夹扫描性能报告'
            ''
            '- 运行状态：**未生成报告**'
            "- 运行 ID：$runId"
            "- 退出码：$exitCode"
            ''
            '性能基准未写出报告，请检查 console.log 与 server.log。'
        ) | Set-Content -Path $reportMd -Encoding utf8
    }

    Write-Host ''
    Write-Host '==== 性能测试结束 ====' -ForegroundColor Cyan
    Write-Host "  退出码 = $exitCode"
    Write-Host "  报告   = $reportMd"
    if (Test-Path $reportJson) {
        try {
            $report = Get-Content $reportJson -Raw | ConvertFrom-Json
            $status = $report.status
            $summary = $report.summary
            if ($summary) {
                Write-Host "  状态   = $status"
                Write-Host "  总耗时 = $($summary.pipeline_seconds) s"
                Write-Host "  吞吐   = $($summary.photos_per_second) 张/秒"
                Write-Host "  完成   = $($summary.core_tasks_completed) / $($summary.core_tasks_expected) 个核心任务"
            }
            else {
                Write-Host "  状态   = $status"
                if ($report.error) { Write-Host "  错误   = $($report.error)" -ForegroundColor Yellow }
            }
        }
        catch {
            Write-Host "  报告解析失败：$($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
    Write-Host '======================' -ForegroundColor Cyan
    [Console]::OutputEncoding = $previousConsoleEncoding
    $OutputEncoding = $previousOutputEncoding
    if ($null -eq $previousPythonIoEncodingGlobal) {
        Remove-Item Env:PYTHONIOENCODING -ErrorAction SilentlyContinue
    }
    else {
        $env:PYTHONIOENCODING = $previousPythonIoEncodingGlobal
    }
}

exit $exitCode
