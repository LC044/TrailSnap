<#
.SYNOPSIS
本地构建 TrailSnap AI 扩展并铺到桌面端数据目录，供双击 exe 测试。

.DESCRIPTION
用 PyInstaller 把 package/ai 打成 one-dir 的 trailsnap-ai runtime，连同
installed.json 一起铺到 %LOCALAPPDATA%\TrailSnap\ai-extensions\core-ai\。

desktop 的 app_root 硬编码为 %LOCALAPPDATA%\TrailSnap（见 lib.rs 的
prepare_data_dir），ai_gateway.ensure_sidecar 从 app_root\ai-extensions\<id>\
读已安装扩展并启动入口。铺好后无需在桌面端里再下载/导入 AI 扩展，直接双击
package\desktop\src-tauri\target\release\trailsnap-desktop.exe 即可用 AI。

仅本地测试用：不打包安装包、不改 Rust 代码。

.PARAMETER SkipInstall
跳过 uv sync，用于已同步过依赖的重复构建。

.PARAMETER SkipBuild
跳过 PyInstaller 构建，直接用已有的 package\ai\dist\trailsnap-ai 重新铺装。

.PARAMETER SkipPrecache
跳过 RapidOCR 资源预缓存（首次构建不要用，否则 OCR 模型不会打进包）。

.EXAMPLE
pwsh .\build-ai-local.ps1

.EXAMPLE
pwsh .\build-ai-local.ps1 -SkipInstall -SkipPrecache
#>
[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [switch]$SkipBuild,
    [switch]$SkipPrecache
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
        [System.Runtime.InteropServices.OSPlatform]::Windows
    )) {
    throw '此脚本只在 Windows 上运行（desktop app_root 走 LOCALAPPDATA）。'
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw '找不到 uv：https://docs.astral.sh/uv/getting-started/installation/'
}
& uv --version *> $null
if ($LASTEXITCODE -ne 0) { throw 'uv 不可用，请重装。' }

$repoRoot = $PSScriptRoot
$aiDir = Join-Path $repoRoot 'package\ai'
$desktopDir = Join-Path $repoRoot 'package\desktop'
$tauriConf = Join-Path $desktopDir 'src-tauri\tauri.conf.json'
$runtimeSrc = Join-Path $aiDir 'dist\trailsnap-ai'
$runtimeExe = Join-Path $runtimeSrc 'trailsnap-ai.exe'
$desktopExe = Join-Path $desktopDir 'src-tauri\target\release\trailsnap-desktop.exe'

if (-not (Test-Path -LiteralPath $tauriConf)) {
    throw "找不到 tauri.conf.json：$tauriConf"
}

Write-Host '==> 构建 TrailSnap AI 本地扩展...' -ForegroundColor Cyan
Write-Host "AI 目录: $aiDir"

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$ArgumentList,
        [string]$WorkingDirectory
    )
    if ($WorkingDirectory) { Push-Location $WorkingDirectory }
    try {
        & $FilePath @ArgumentList
        if ($LASTEXITCODE -ne 0) {
            throw "命令失败($LASTEXITCODE): $FilePath $($ArgumentList -join ' ')"
        }
    }
    finally {
        if ($WorkingDirectory) { Pop-Location }
    }
}

if (-not $SkipInstall) {
    Write-Host '==> 同步 AI 依赖 (cpu + desktop)...'
    Invoke-NativeCommand -FilePath uv `
        -ArgumentList @('sync', '--project', $aiDir, '--frozen', '--extra', 'cpu', '--group', 'desktop') `
        -WorkingDirectory $aiDir
}

if (-not $SkipPrecache) {
    Write-Host '==> 预缓存 RapidOCR 资源（首次会下载模型，请等待）...'
    Invoke-NativeCommand -FilePath uv `
        -ArgumentList @('--project', $aiDir, 'run', 'python', '-c',
            'from app.services.ocr_service import load_paddleocr_model; load_paddleocr_model()') `
        -WorkingDirectory $aiDir
}

if (-not $SkipBuild) {
    Write-Host '==> PyInstaller 打包 trailsnap-ai...'
    Invoke-NativeCommand -FilePath uv `
        -ArgumentList @('--project', $aiDir, 'run', 'python', 'scripts/build_desktop_runtime.py') `
        -WorkingDirectory $aiDir
}

if (-not (Test-Path -LiteralPath $runtimeExe)) {
    throw "AI runtime 未生成：$runtimeExe（请去掉 -SkipBuild 重新构建）"
}

Write-Host '==> 校验 frozen runtime (--self-check)...'
Invoke-NativeCommand -FilePath $runtimeExe -ArgumentList @('--self-check')

# ---- 铺到 %LOCALAPPDATA%\TrailSnap\ai-extensions\core-ai ----
$dataRoot = Join-Path $env:LOCALAPPDATA 'TrailSnap'
$extRoot = Join-Path $dataRoot 'ai-extensions'
$coreAiDir = Join-Path $extRoot 'core-ai'
$runtimeTarget = Join-Path $coreAiDir 'runtime\trailsnap-ai'
$installedJson = Join-Path $extRoot 'installed.json'

Write-Host '==> 铺装到桌面端数据目录...' -ForegroundColor Cyan
Write-Host "目标: $coreAiDir"

# 铺装会覆盖 exe。desktop 在跑时不能铺：ensure_sidecar 会按需重启 sidecar，
# 可能在复制中途从半成品目录拉起进程。只剩孤儿 sidecar（desktop 已退出）时
# 安全杀掉再继续——这种 sidecar 通常是 psutil 父进程看门狗失灵留下的。
$desktopProc = Get-Process -Name 'trailsnap-desktop' -ErrorAction SilentlyContinue
if ($desktopProc) {
    throw "检测到桌面端正在运行 (trailsnap-desktop)，请先完全关闭它再铺装，避免复制中途 sidecar 被重启。"
}

$sidecar = Get-Process -Name 'trailsnap-ai' -ErrorAction SilentlyContinue
if ($sidecar) {
    Write-Host "==> 发现孤儿 AI sidecar 进程，停止后继续铺装..." -ForegroundColor Yellow
    $sidecar | Stop-Process -Force
    Start-Sleep -Milliseconds 500
}

if (Test-Path -LiteralPath $coreAiDir) {
    Remove-Item -LiteralPath $coreAiDir -Recurse -Force
}
New-Item -ItemType Directory -Path (Join-Path $coreAiDir 'runtime') -Force | Out-Null

Copy-Item -LiteralPath $runtimeSrc -Destination $runtimeTarget -Recurse -Force
$targetExe = Join-Path $runtimeTarget 'trailsnap-ai.exe'
if (-not (Test-Path -LiteralPath $targetExe)) {
    throw "铺装后入口缺失：$targetExe"
}

# 写 installed.json，结构对齐 ai_extension.rs 的 InstalledState / InstalledExtension
# （serde rename_all = "camelCase"，所以字段名用驼峰）。
$conf = Get-Content -LiteralPath $tauriConf -Raw | ConvertFrom-Json
$version = $conf.version
$installedAt = [string]([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())

$installed = [ordered]@{
    schemaVersion = 1
    extensions    = [ordered]@{
        'core-ai' = [ordered]@{
            id           = 'core-ai'
            version      = $version
            platform     = 'win32-x64'
            capabilities = @(
                'face', 'ocr', 'object_detection', 'tickets',
                'classification', 'embedding', 'llm', 'emotion'
            )
            entrypoint   = 'runtime/trailsnap-ai/trailsnap-ai.exe'
            modelPath    = $null
            checksum     = ''
            installedAt  = $installedAt
        }
    }
}
$json = $installed | ConvertTo-Json -Depth 10
# 无 BOM UTF-8：serde_json::from_slice 遇到 UTF-8 BOM 会解析失败。
[System.IO.File]::WriteAllText($installedJson, $json, [System.Text.UTF8Encoding]::new($false))

Write-Host ''
Write-Host '完成。' -ForegroundColor Green
Write-Host "AI 入口:   $targetExe"
Write-Host "状态文件: $installedJson"
Write-Host "版本:     $version"
Write-Host ''
if (Test-Path -LiteralPath $desktopExe) {
    Write-Host '现在双击即可使用 AI（无需在应用内再下载/导入扩展）：' -ForegroundColor Green
    Write-Host "  $desktopExe"
}
else {
    Write-Host 'desktop exe 尚未构建。先构建再双击：' -ForegroundColor Yellow
    Write-Host "  pnpm --dir `"$desktopDir`" exec tauri build --bundles none"
    Write-Host "（或 cargo build --release，在 package/desktop/src-tauri 下）"
}
