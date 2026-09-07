<#
.SYNOPSIS
    TrailSnap 测试统一入口（CI 与本地共用）。

.DESCRIPTION
    一个命令驱动 unit / integration / e2e 三层测试。
    服务生命周期委托给 services-up.ps1 / services-down.ps1（dev 本地进程 或 docker compose）。
    环境变量单一来源：tests/.env.test（由 Import-EnvFile 加载到会话，子进程继承）。

    四个维度：
      -EnvFile    第一个位置参数，环境变量文件路径，不传则默认 tests\.env.test
      -Layer      unit | integration | e2e | all
      -Level      dev | scan | smoke | p0 | p1 | all | light | full（深度/套件；默认读 TS_E2E_SUITE，再不行 smoke）
                  unit/integration → pytest -m 映射（smoke→-m smoke，其余不加 -m）；e2e → run-e2e.mjs <level>
      -Component  server | ai | website | cli | all
      -Mode       dev | docker（默认按 TS_TEST_ENV：docker/ci→docker，否则 dev）
      -Scope      all | photo | album | face | ocr | ... （unit/integration 业务域过滤）
      -ScanPrep   auto | true | false（e2e 是否先 scan；默认 false）

    最简打通流程：
      .\tests\scripts\run-tests.ps1                                 # 默认 = server+ai 的 smoke 单元
      .\tests\scripts\run-tests.ps1 -Layer e2e -Level p0           # 本地 dev 进程跑 p0
      .\tests\scripts\run-tests.ps1 -Layer e2e -Level full         # 本地 dev 进程跑 full
      .\tests\scripts\run-tests.ps1 -Layer e2e -Level p0 -Mode docker   # 起 compose 栈跑 p0（同 CI）
      .\tests\scripts\run-tests.ps1 -StopServices                  # 按端口清理服务（含孤儿子进程）

.PARAMETER EnvFile
    环境变量文件路径（第一个位置参数）。不传则默认 tests\.env.test。
    仓库只提交模板 tests\.env.test.example；本地配置需先从模板复制一份。

.PARAMETER Layer
    unit       后端/AI 纯函数与契约测试（无外部服务，秒级）
    integration后端集成测试（需 DB）
    e2e        前端 Playwright（run-e2e.mjs <level>）
    all        unit + e2e 串行

.PARAMETER Level
    scan | smoke | p0 | p1 | all | light | full。
    e2e 层直接对应 run-e2e.mjs 的套件名；unit/integration 层做 -m 映射。

.PARAMETER Mode
    dev | docker。dev=本地 uv/pnpm 进程；docker=compose 栈。

.EXAMPLE
    .\tests\scripts\run-tests.ps1 -Layer unit -Level smoke
    .\tests\scripts\run-tests.ps1 -Layer e2e -Level p0 -Mode docker
    .\tests\scripts\run-tests.ps1 -Layer e2e -Level full
    .\tests\scripts\run-tests.ps1 tests\.env.test-local -StopServices
#>
[CmdletBinding()]
param(
    # 第一个位置参数：环境变量文件路径，不传则默认 tests\.env.test
    [Parameter(Position = 0)]
    [string]$EnvFile,

    [ValidateSet('unit', 'integration', 'e2e', 'all')]
    [string]$Layer = 'unit',

    [ValidateSet('dev', 'scan', 'smoke', 'p0', 'p1', 'all', 'light', 'full')]
    [string]$Level,

    [ValidateSet('server', 'ai', 'website', 'cli', 'all')]
    [string]$Component = 'all',

    [ValidateSet('dev', 'docker')]
    [string]$Mode,

    [string]$Scope,

    [ValidateSet('auto', 'true', 'false')]
    [string]$ScanPrep = 'auto',

    [switch]$Cleanup,

    # 仅停止当前运行中的本地测试服务（按端口清理，含孤儿子进程），
    # 不启动服务、不跑测试、不动数据库。
    [switch]$StopServices
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..' '..')).Path
if (-not $EnvFile) { $EnvFile = Join-Path $RepoRoot 'tests' '.env.test' }
if (-not [System.IO.Path]::IsPathRooted($EnvFile)) { $EnvFile = Join-Path $RepoRoot $EnvFile }
if (-not (Test-Path $EnvFile)) {
    $exampleRel = Join-Path 'tests' '.env.test.example'
    $exampleAbs = Join-Path $RepoRoot $exampleRel
    Write-Host "找不到环境变量文件：$EnvFile" -ForegroundColor Red
    Write-Host '请先从仓库自带的模板复制一份本地配置，按需编辑后再重跑：' -ForegroundColor Yellow
    if (Test-Path $exampleAbs) {
        $targetRel = Join-Path 'tests' '.env.test'
        Write-Host "    Copy-Item '$exampleRel' '$targetRel'" -ForegroundColor Cyan
    } else {
        Write-Host "（模板 $exampleRel 也不存在，请确认仓库完整性。）" -ForegroundColor Yellow
    }
    exit 1
}

# 1) 加载单一数据源到会话 —— 四方共享的关键
. (Join-Path $PSScriptRoot 'Import-EnvFile.ps1')
Import-EnvFile -Path $EnvFile
. (Join-Path $PSScriptRoot 'test-services-lib.ps1')

# 2) 档位回退：命令行未传则读 .env.test，再不行用默认
if (-not $Level) { $Level = if ($env:TS_E2E_SUITE) { $env:TS_E2E_SUITE.ToLower() } else { 'smoke' } }
if (-not $Scope) { $Scope = if ($env:TS_TEST_SCOPE) { $env:TS_TEST_SCOPE } else { 'all' } }
if (-not $Mode)  { $Mode  = if ($env:TS_TEST_ENV -in 'docker', 'ci') { 'docker' } else { 'dev' } }
switch ($ScanPrep) {
    'true'  { $env:TS_E2E_ENABLE_FIXTURE_SCAN = 'true' }
    'false' { $env:TS_E2E_ENABLE_FIXTURE_SCAN = 'false' }
    default {
        if (-not $env:TS_E2E_ENABLE_FIXTURE_SCAN) { $env:TS_E2E_ENABLE_FIXTURE_SCAN = 'false' }
    }
}

# -StopServices 模式：只关服务，跳过测试
if ($StopServices) {
    & (Join-Path $PSScriptRoot 'services-down.ps1') -EnvFile $EnvFile -Mode $Mode -Component 'all'
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "==== TrailSnap 测试入口 ====" -ForegroundColor Cyan
Write-Host "  Layer     = $Layer"
Write-Host "  Level     = $Level"
Write-Host "  Component = $Component"
Write-Host "  Mode      = $Mode"
Write-Host "  Scope     = $Scope"
Write-Host "  ScanPrep  = $env:TS_E2E_ENABLE_FIXTURE_SCAN"
Write-Host "  API       = $env:TS_API_BASE_URL"
Write-Host "  Web       = $env:TS_WEB_BASE_URL"
Write-Host "  AI        = $env:TS_AI_API_URL"
Write-Host "  DB        = $env:TS_DB_URL"
Write-Host "  ResetDB   = $(if (Test-ResetDbFlag) { 'true' } else { 'false' })"
Write-Host "  KeepSvcs  = $(if (Test-KeepServicesFlag) { 'true' } else { 'false' })"
Write-Host "============================" -ForegroundColor Cyan
Write-Host ""

# 把 Level + Scope 组合成 pytest -m 表达式
#   smoke + album -> "smoke and module_album"
#   非 smoke      -> 不加 cover marker（可叠加 Scope）
function Get-MarkerArg {
    param([string]$Lvl, [string]$Scp)
    $parts = @()
    if ($Lvl -eq 'smoke') { $parts += 'smoke' }
    if ($Scp -and $Scp -ne 'all') { $parts += "module_$Scp" }
    if ($parts.Count -eq 0) { return @() }
    return @('-m', ($parts -join ' and '))
}

# 调 pytest：uv 优先，回退包内 venv python
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
            $py = if ($IsWindows) {
                Join-Path $pkgAbs '.venv' 'Scripts' 'python.exe'
            } else {
                Join-Path $pkgAbs '.venv' 'bin' 'python'
            }
            if (-not (Test-Path $py)) { throw "找不到 uv，且 $py 不存在" }
            & $py -m pytest $TestPath @ExtraArgs -v
        }
        if ($LASTEXITCODE -ne 0) { throw "pytest 失败 ($PackageDir)，退出码 $LASTEXITCODE" }
    }
    finally { Pop-Location }
}

$exitCode = 0
$needServices = $Layer -in 'e2e', 'integration', 'all'

try {
    # ---------- 启动服务 ----------
    if ($needServices) {
        & (Join-Path $PSScriptRoot 'services-up.ps1') -EnvFile $EnvFile -Mode $Mode -Component $Component
        if ($LASTEXITCODE -ne 0) { throw "services-up 失败，退出码 $LASTEXITCODE" }
    }

    # ---------- e2e（Playwright）----------
    if ($Layer -in 'e2e', 'all') {
        if ($Component -in 'website', 'all') {
            # TS_TEST_RESET_DB=true 时每轮都是新空库，但 photo-fixtures 的 state cache 跨轮稳定，
            # 上轮 ok=true 会让本轮 globalSetup 跳过扫描 → 空库无照片。注入唯一 prep run id 强制重扫；
            # RESET_DB=false 时维持 'default'，保留跨轮缓存命中。
            if (Test-ResetDbFlag -and -not $env:TS_E2E_PREP_RUN_ID) {
                $env:TS_E2E_PREP_RUN_ID = "reset-$([System.Guid]::NewGuid().ToString('N').Substring(0,12))"
                Write-Host "  TS_TEST_RESET_DB=true → TS_E2E_PREP_RUN_ID=$($env:TS_E2E_PREP_RUN_ID)" -ForegroundColor DarkGray
            }

            $env:TS_E2E_SUITE = $Level
            # 兜底默认值（.env.test 已加载则不覆盖）
            $env:TS_API_BASE_URL  = if ($env:TS_API_BASE_URL)  { $env:TS_API_BASE_URL }  else { 'http://localhost:8800' }
            $env:TS_WEB_BASE_URL  = if ($env:TS_WEB_BASE_URL)  { $env:TS_WEB_BASE_URL }  else { 'http://localhost:3180' }
            $env:TS_PHOTO_DIR     = if ($env:TS_PHOTO_DIR)     { $env:TS_PHOTO_DIR }     else { '/testdata/photos' }
            $env:TS_TEST_USERNAME = if ($env:TS_TEST_USERNAME) { $env:TS_TEST_USERNAME } else { 'e2e-admin' }
            $env:TS_TEST_PASSWORD = if ($env:TS_TEST_PASSWORD) { $env:TS_TEST_PASSWORD } else { 'Passw0rd!123' }

            Write-Host "==> 前端 E2E  suite=$Level  mode=$Mode" -ForegroundColor Green
            $webDir = Join-Path $RepoRoot 'package' 'website'
            Push-Location $webDir
            try {
                if (-not (Test-Path (Join-Path $webDir 'node_modules'))) {
                    Write-Host '  安装 website 依赖...'; pnpm install --frozen-lockfile
                }
                Write-Host '  确保 Playwright chromium 已安装...'; pnpm exec playwright install chromium
                # 统一委托给 run-e2e.mjs，由其处理 scan/p0/p1/smoke/all/light/full
                & node (Join-Path 'playwright' 'run-e2e.mjs') $Level
                if ($LASTEXITCODE -ne 0) { throw "playwright 失败，退出码 $LASTEXITCODE" }
            }
            finally { Pop-Location }
        }
    }

    # ---------- unit / integration（pytest）----------
    if ($Layer -in 'unit', 'integration', 'all') {
        $markerArg = Get-MarkerArg -Lvl $Level -Scp $Scope
        $testPath = if ($Layer -eq 'integration') { 'tests/integration' } else { 'tests/unit' }
        $aiTestPath = 'tests'

        if ($Component -in 'server', 'all') {
            Write-Host "==> 后端 $Layer 测试 (server)" -ForegroundColor Green
            Invoke-Pytest -PackageDir (Join-Path 'package' 'server') -TestPath $testPath -ExtraArgs $markerArg
        }
        if ($Component -in 'ai', 'all') {
            Write-Host "==> AI $Layer 测试 (ai)" -ForegroundColor Green
            Invoke-Pytest -PackageDir (Join-Path 'package' 'ai') -TestPath $aiTestPath -ExtraArgs $markerArg
        }
    }

    # ---------- CLI（在 E2E 完成后运行，确保 E2E 测试账号先初始化）----------
    if ($Layer -in 'unit', 'integration', 'all' -and $Component -in 'cli', 'all') {
        $markerArg = Get-MarkerArg -Lvl $Level -Scp $Scope
        Write-Host "==> CLI $Layer 测试 (cli)" -ForegroundColor Green
        # CLI unit 测试不依赖 server；跳过需要真实后端的 tests/integration
        Invoke-Pytest -PackageDir (Join-Path 'package' 'trailsnap-cli') -TestPath 'tests' -ExtraArgs (@('--ignore=tests/integration') + $markerArg)
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
    # ---- 数据库清理（-Cleanup）----
    if ($Cleanup) {
        if (Test-KeepServicesFlag) {
            Write-Host "==> 跳过 -Cleanup 数据库删除（TS_TEST_KEEP_SERVICES=true）" -ForegroundColor Yellow
        } else {
            Write-Host ""
            Write-Host "==> 清理测试环境..." -ForegroundColor Cyan
            Invoke-TestDatabaseDrop -Reason '测试后清理' -RepoRoot $RepoRoot
        }
    }

    # ---- 关闭服务 ----
    if ($needServices) {
        if (Test-KeepServicesFlag) {
            Write-Host "==> TS_TEST_KEEP_SERVICES=true，保留服务运行（未调用 services-down）" -ForegroundColor Green
        } else {
            & (Join-Path $PSScriptRoot 'services-down.ps1') -EnvFile $EnvFile -Mode $Mode -Component $Component
        }
    }
}

exit $exitCode
