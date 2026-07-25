<#
.SYNOPSIS
    拉取 TrailSnap 测试照片夹具（独立 LFS 仓库）。

.DESCRIPTION
    e2e 测试的 photos 夹具放在独立 Git 仓库 siyuan044/trailsnap-test-photos，
    用 Git LFS 存储（避免大量 jpg 进入主 repo）。本脚本把该仓库拉（克隆或更新）
    到 tests/fixtures/e2e-photos/，供 docker-compose.e2e.yml 挂载。

    行为：
      - 目标目录是空目录 → git clone + git lfs pull
      - 目标目录是已有 git repo → git fetch + git lfs pull
      - 目标目录非空且不是 git repo → 报错退出

.PARAMETER RepoUrl
    远端 fixture 仓库 URL。默认从 $env:TS_TEST_PHOTOS_REPO 读取，否则用
    https://github.com/siyuan044/trailsnap-test-photos.git。

.PARAMETER TargetDir
    本地目标目录。默认 tests/fixtures/e2e-photos（相对仓库根）。

.EXAMPLE
    .\tests\scripts\sync-test-photos.ps1
    .\tests\scripts\sync-test-photos.ps1 -RepoUrl https://github.com/me/my-fork.git
#>
param(
    [string]$RepoUrl,
    [string]$TargetDir
)

$ErrorActionPreference = 'Stop'

if (-not $RepoUrl) {
    $RepoUrl = if ($env:TS_TEST_PHOTOS_REPO) { $env:TS_TEST_PHOTOS_REPO } `
               else { 'https://github.com/LC044/trailsnap-test-photos.git' }
}
if (-not $TargetDir) { $TargetDir = 'tests/fixtures/e2e-photos' }

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$TargetAbs = if (-not [System.IO.Path]::IsPathRooted($TargetDir)) {
    Join-Path $RepoRoot $TargetDir
} else { $TargetDir }

Write-Host "Repo:   $RepoUrl"
Write-Host "Target: $TargetAbs"

# 1) git + git lfs 前置检查
try { git --version | Out-Null } catch { throw 'git 未安装或不在 PATH' }
try { git lfs version | Out-Null } catch {
    throw 'git-lfs 未安装。请到 https://git-lfs.github.com 安装后再运行。'
}

if (-not (Test-Path $TargetAbs)) {
    New-Item -ItemType Directory -Force -Path $TargetAbs | Out-Null
}

# 2) 判断状态：空目录 → clone；已是 git repo → pull；其他 → 报错
$isGitRepo = Test-Path (Join-Path $TargetAbs '.git')
$hasContent = (Get-ChildItem -Force $TargetAbs -ErrorAction SilentlyContinue `
                | Where-Object { $_.Name -ne '.gitkeep' }).Count -gt 0

if ($isGitRepo) {
    Write-Host 'Pulling latest...'
    git -C $TargetAbs fetch --prune
    git -C $TargetAbs pull --rebase --autostash
} elseif (-not $hasContent) {
    Write-Host 'Cloning (with LFS)...'
    git clone $RepoUrl $TargetAbs
} else {
    throw "目标目录 $TargetAbs 非空且不是 git repo，无法处理。请先手动清空。"
}

# 3) 确保 LFS 对象已下载
Write-Host 'Pulling LFS objects...'
git -C $TargetAbs lfs pull

# 4) 校验 fixtures 结构
$smokeDir = Join-Path $TargetAbs 'fixtures/smoke'
$p0Dir = Join-Path $TargetAbs 'fixtures/p0'
foreach ($d in @($smokeDir, $p0Dir)) {
    if (-not (Test-Path $d)) {
        Write-Warning "缺少目录: $d（远端 fixture 仓库结构不完整）"
    }
}

Write-Host 'Done. fixtures 已就绪。'
