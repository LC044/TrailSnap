<#
.SYNOPSIS
TrailSnap - Windows 一键安装脚本

.DESCRIPTION
自动配置 Docker、设置镜像加速源、启动 TrailSnap。
支持交互式和非交互式模式、GPU 加速、升级和卸载。

.EXAMPLE
# 交互式安装
.\install.ps1

# 非交互式安装
.\install.ps1 -PhotoDir "D:\Photos" -ChinaMirrors -Yes

# GPU 模式
.\install.ps1 -PhotoDir "D:\Photos" -AiMode gpu

# 升级
.\install.ps1 -Upgrade

# 卸载
.\install.ps1 -Uninstall -Purge
#>

[CmdletBinding()]
param(
    [string]$PhotoDir = "",
    [string]$InstallDir = "",
    [int]$FrontendPort = 8082,
    [int]$ServerPort = 8800,
    [int]$AiPort = 8801,
    [int]$PostgresPort = 5532,
    [string]$Timezone = "Asia/Shanghai",
    [ValidateSet("cpu", "gpu")]
    [string]$AiMode = "cpu",
    [string]$Tag = "latest",
    [switch]$ChinaMirrors,
    [switch]$Yes,
    [switch]$Upgrade,
    [switch]$Uninstall,
    [switch]$Purge,
    [string]$AddPhotoDir = "",
    [switch]$Help
)

# ── 设置控制台编码为 UTF-8 ────────────────────────────────────────────────────
# Windows 默认使用 GBK 编码，中文会显示为乱码。强制切换到 UTF-8 输出。
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
    chcp 65001 > $null 2>&1
} catch {}

# ── 常量 ──────────────────────────────────────────────────────────────────────
$ScriptVersion = "1.5.2"
$DefaultInstallDir = Join-Path $env:USERPROFILE "trailsnap"
$DefaultPgDb = "trailsnap"
$DefaultPgUser = "trailsnap"

# Promote param to script scope so functions can access it
$script:InstallDir = $InstallDir
$script:ComposeCmd = ""
$script:LogFile = ""
$script:PgPassword = ""

$ChinaMirrorList = @(
    "https://docker.1ms.run",
    "https://docker.xuanyuan.me",
    "https://dockerproxy.net",
    "https://docker.1panel.live",
    "https://dockerproxy.cn",
    "https://docker.nastool.de",
    "https://docker.agsv.top",
    "https://docker.agsvpt.work",
    "https://docker.m.daocloud.io",
    "https://dockerhub.anzu.vip",
    "https://docker.chenby.cn",
    "https://docker.jijiai.cn"
)

# ── 工具函数 ──────────────────────────────────────────────────────────────────

function Write-Banner {
    Write-Host ""
    Write-Host "  +===============================================+" -ForegroundColor Cyan
    Write-Host "  |                                               |" -ForegroundColor Cyan
    Write-Host "  |       TrailSnap (行影集) — 一键安装           |" -ForegroundColor Cyan
    Write-Host "  |       AI 驱动的自托管相册                     |" -ForegroundColor Cyan
    Write-Host "  |                                               |" -ForegroundColor Cyan
    Write-Host "  +===============================================+" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Info {
    param([string]$Message)
    Write-Host "[信息]  $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[警告]  $Message" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Message)
    Write-Host "[错误] $Message" -ForegroundColor Red
}

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message" -ForegroundColor Blue
}

function Stop-Script {
    param([string]$Message)
    Write-Err $Message
    Write-Log "FATAL: $Message"
    exit 1
}

function Read-Prompt {
    param(
        [string]$Prompt,
        [string]$Default = ""
    )
    if ($Yes) {
        return $Default
    }
    $display = if ($Default) { " [$Default]" } else { "" }
    $answer = Read-Host "${Prompt}${display}"
    if ([string]::IsNullOrWhiteSpace($answer)) { return $Default } else { return $answer }
}

function Read-YesNo {
    param(
        [string]$Prompt,
        [string]$Default = "n"
    )
    if ($Yes) {
        return ($Default -eq "y")
    }
    $indicator = if ($Default -eq "y") { "Y/n" } else { "y/N" }
    $answer = Read-Host "${Prompt} [$indicator]"
    if ([string]::IsNullOrWhiteSpace($answer)) { $answer = $Default }
    return ($answer -match "^[yY]")
}

# ── 随机密码生成 ──────────────────────────────────────────────────────────────
# 生成安全的随机数据库密码，避免硬编码默认密码
function New-RandomPassword {
    param([int]$Length = 16)
    $chars = @(48..57) + @(65..90) + @(97..122) # 0-9, A-Z, a-z
    -join ($chars | Get-Random -Count $Length | ForEach-Object { [char]$_ })
}

# ── 日志记录 ──────────────────────────────────────────────────────────────────
# 同时写入控制台和日志文件，方便安装失败后排查
function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logLine = "[$timestamp] $Message"
    if ($script:LogFile -and (Test-Path (Split-Path $script:LogFile -Parent) -ErrorAction SilentlyContinue)) {
        Add-Content -Path $script:LogFile -Value $logLine -Encoding UTF8
    }
}

# ── 获取局域网 IP ────────────────────────────────────────────────────────────

function Get-LanIP {
    try {
        $adapters = Get-NetIPAddress -AddressFamily IPv4 |
            Where-Object { $_.IPAddress -ne "127.0.0.1" -and $_.PrefixOrigin -ne "WellKnown" -and $_.SuffixOrigin -ne "Link" } |
            Sort-Object -Property InterfaceAlias

        $defaultGateway = Get-NetRoute -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty InterfaceIndex -Unique

        foreach ($gw in $defaultGateway) {
            $ip = $adapters | Where-Object { $_.InterfaceIndex -eq $gw } | Select-Object -First 1 -ExpandProperty IPAddress
            if ($ip) { return $ip }
        }

        $first = $adapters | Select-Object -First 1 -ExpandProperty IPAddress
        if ($first) { return $first }
    } catch {}
    return $null
}

# ── 硬件预检 ──────────────────────────────────────────────────────────────────

function Test-Hardware {
    Write-Step "检查硬件资源..."

    # 检查磁盘空间
    $installDrive = if ($script:InstallDir) {
        $resolvedParent = Split-Path $script:InstallDir -Parent
        if (Test-Path $resolvedParent) {
            (Resolve-Path $resolvedParent).Drive.Name
        } else {
            $env:SystemDrive.Substring(0,1)
        }
    } else {
        $env:SystemDrive.Substring(0,1)
    }
    if (-not $installDrive) { $installDrive = $env:SystemDrive.Substring(0,1) }

    try {
        $disk = Get-PSDrive -Name $installDrive -ErrorAction Stop
        $freeGB = [math]::Round($disk.Free / 1GB, 1)
        if ($freeGB -lt 10) {
            Write-Err "磁盘 ${installDrive}: 剩余空间仅 ${freeGB} GB，不足以安装 TrailSnap（至少需要 10 GB）。"
            Write-Err "请清理磁盘空间后重试。"
            Stop-Script "磁盘空间不足。"
        } elseif ($freeGB -lt 15) {
            Write-Warn "磁盘 ${installDrive}: 剩余空间 ${freeGB} GB，安装 TrailSnap（含 AI 镜像）可能需要 10-15 GB。"
            Write-Warn "如果空间不足，可能导致下载失败。建议先清理磁盘。"
            if (-not (Read-YesNo "是否继续安装？" "n")) {
                Stop-Script "已取消。"
            }
        } else {
            Write-Info "磁盘 ${installDrive}: 剩余空间 ${freeGB} GB，满足安装要求。"
        }
        Write-Log "硬件检查: 磁盘 ${installDrive}: ${freeGB} GB 可用"
    } catch {
        Write-Warn "无法检测磁盘空间，跳过检查。"
    }

    # 检查内存
    try {
        $os = Get-CimInstance Win32_OperatingSystem
        $totalRAM_GB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
        if ($totalRAM_GB -lt 4) {
            Write-Warn "系统内存 ${totalRAM_GB} GB，运行 AI 服务可能会卡顿。"
            Write-Warn "建议至少 4 GB 内存。可以选择 CPU 模式（不启用 GPU 加速）。"
        } else {
            Write-Info "系统内存 ${totalRAM_GB} GB，满足运行要求。"
        }
        Write-Log "硬件检查: 内存 ${totalRAM_GB} GB"
    } catch {
        Write-Warn "无法检测系统内存，跳过检查。"
    }
}

# ── Docker 检测与安装 ─────────────────────────────────────────────────────────

function Test-DockerInstalled {
    $cmd = Get-Command docker -ErrorAction SilentlyContinue
    if ($null -ne $cmd) {
        return $true
    }
    
    # 尝试在默认安装路径中查找（解决刚安装完未刷新环境变量的问题）
    $defaultPath = "$env:ProgramFiles\Docker\Docker\resources\bin"
    if (Test-Path "$defaultPath\docker.exe") {
        $env:PATH += ";$defaultPath"
        return $true
    }
    
    return $false
}

function Test-DockerRunning {
    try {
        $result = docker info 2>&1
        if ($LASTEXITCODE -eq 0) {
            return $true
        }
        return $false
    } catch {
        return $false
    }
}

function Get-ComposeCmd {
    try {
        $null = docker compose version 2>&1
        if ($LASTEXITCODE -eq 0) {
            return "docker compose"
        }
    } catch {}
    $cmd = Get-Command docker-compose -ErrorAction SilentlyContinue
    if ($null -ne $cmd) {
        return "docker-compose"
    }
    return $null
}

function Install-DockerDesktop {
    Write-Step "正在安装 Docker Desktop..."

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Info "正在通过 winget 安装 Docker Desktop..."
        winget install Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
        Write-Info "Docker Desktop 已安装，请从开始菜单启动。"
        Write-Warn "Docker Desktop 启动后，请重新运行本脚本。"
        Stop-Script "请启动 Docker Desktop 后重新运行本脚本。"
    } else {
        Write-Host ""
        Write-Err "winget 不可用，无法自动安装 Docker Desktop。"
        Write-Info "正在打开 Docker Desktop 下载页面..."
        # 检测系统架构，选择对应下载链接
        $dockerUrl = if ([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture -eq [System.Runtime.InteropServices.Architecture]::Arm64) {
            "https://desktop.docker.com/win/main/arm64/Docker%20Desktop%20Installer.exe"
        } else {
            "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe"
        }
        Start-Process $dockerUrl
        Write-Host ""
        Stop-Script "请安装 Docker Desktop 后重新运行本脚本。"
    }
}

function New-ResumeShortcut {
    # 在桌面创建"继续安装 TrailSnap"快捷方式
    # 使用纯 ASCII 文本避免 bat 文件编码乱码问题
    $desktopPath = [Environment]::GetFolderPath("Desktop")
    $shortcutPath = Join-Path $desktopPath "Continue-TrailSnap-Install.bat"
    $scriptPath = $PSCommandPath
    if (-not $scriptPath) {
        $scriptPath = $MyInvocation.PSCommandPath
    }

    $batContent = @"
@echo off
chcp 65001 >nul 2>&1
echo.
echo   =============================================
echo   ^|   Continue TrailSnap Installation         ^|
echo   =============================================
echo.
powershell -ExecutionPolicy Bypass -File "$scriptPath"
del "%~f0"
"@
    Set-Content -Path $shortcutPath -Value $batContent -Encoding ASCII
    Write-Info "已在桌面创建快捷方式：Continue-TrailSnap-Install.bat"
    Write-Info "重启电脑后双击桌面图标即可继续安装。"
    return $shortcutPath
}

function Ensure-WSL2 {
    Write-Step "检查 WSL2..."
    # 使用 wsl --list --verbose 检查 WSL2 是否真正可用
    $wslReady = $false
    try {
        $wslList = wsl --list --verbose 2>&1
        # 如果 wsl 命令执行成功，并且输出不包含提示安装的消息，就认为可用
        if ($LASTEXITCODE -eq 0 -and $wslList -notmatch "has no installed distributions|wsl --install") {
            $wslReady = $true
        }
    } catch {}

    if ($wslReady) {
        Write-Info "WSL2 已安装且可用。"
        return
    }

    # WSL2 未安装或不可用
    Write-Warn "WSL2 未安装或未完成配置。"
    if (Read-YesNo "是否现在安装 WSL2？" "y") {
        wsl --install --no-distribution
        Write-Host ""
        Write-Host "  +===========================================================+" -ForegroundColor Yellow
        Write-Host "  |                                                           |" -ForegroundColor Yellow
        Write-Host "  |   !! 需要重启电脑才能完成 WSL2 安装 !!                   |" -ForegroundColor Yellow
        Write-Host "  |                                                           |" -ForegroundColor Yellow
        Write-Host "  |   重启后，请双击桌面上的 Continue-TrailSnap-Install.bat  |" -ForegroundColor Yellow
        Write-Host "  |   即可继续安装，无需再次手动运行脚本。                   |" -ForegroundColor Yellow
        Write-Host "  |                                                           |" -ForegroundColor Yellow
        Write-Host "  +===========================================================+" -ForegroundColor Yellow
        Write-Host ""

        # 创建桌面快捷方式
        New-ResumeShortcut

        Stop-Script "请重启电脑后，双击桌面上的 Continue-TrailSnap-Install.bat 继续安装。"
    } else {
        Stop-Script "WSL2 是 Docker Desktop 在 Windows 上的必需组件。"
    }
}

function Ensure-Docker {
    Write-Step "检查 Docker..."

    Ensure-WSL2

    if (-not (Test-DockerInstalled)) {
        Write-Warn "Docker 未安装。"
        if (Read-YesNo "是否自动安装 Docker Desktop？" "y") {
            Install-DockerDesktop
        } else {
            Stop-Script "Docker 是必需的。请手动安装：https://docs.docker.com/desktop/install/windows-install/"
        }
    }

    if (-not (Test-DockerRunning)) {
        Write-Warn "Docker Desktop 未运行。"
        Write-Info "正在启动 Docker Desktop..."
        $dockerExe = Get-Command "Docker Desktop" -ErrorAction SilentlyContinue
        if (-not $dockerExe) {
            $paths = @(
                "${env:ProgramFiles}\Docker\Docker\Docker Desktop.exe",
                "${env:LOCALAPPDATA}\Programs\Docker\Docker\Docker Desktop.exe"
            )
            foreach ($p in $paths) {
                if (Test-Path $p) {
                    $dockerExe = $p
                    break
                }
            }
        }
        if ($dockerExe) {
            Start-Process $dockerExe
            Write-Info "等待 Docker Desktop 启动..."
            $retries = 0
            while (-not (Test-DockerRunning) -and $retries -lt 60) {
                Start-Sleep -Seconds 3
                $retries++
                Write-Host -NoNewline "."
            }
            Write-Host ""
            if (-not (Test-DockerRunning)) {
                Stop-Script "Docker Desktop 未能在规定时间内启动。请手动启动后重新运行本脚本。"
            }
        } else {
            Stop-Script "未找到 Docker Desktop。请手动启动后重新运行本脚本。"
        }
    }

    Write-Info "Docker 已运行。"
    Write-Log "Docker 检查通过"

    $script:ComposeCmd = Get-ComposeCmd
    if (-not $script:ComposeCmd) {
        Stop-Script "未找到 Docker Compose。请确保 Docker Desktop 已正确安装。"
    }

    Write-Info "Compose 命令：$($script:ComposeCmd)"
}

# ── 端口检查（自动分配） ─────────────────────────────────────────────────────

function Test-PortAvailable {
    param([int]$Port)
    try {
        $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
        return ($null -eq $connections -or $connections.Count -eq 0)
    } catch {
        $netstat = netstat -an 2>&1 | Select-String ":${Port}\s"
        return ($null -eq $netstat)
    }
}

function Get-SuggestedPort {
    param([int]$BasePort)
    for ($offset = 1; $offset -lt 100; $offset++) {
        $candidate = $BasePort + $offset
        if (Test-PortAvailable $candidate) {
            return $candidate
        }
    }
    return $BasePort + 1
}

# ── GPU 检查 ──────────────────────────────────────────────────────────────────

function Test-GpuSupport {
    $nvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if (-not $nvidiaSmi) {
        Write-Warn "未检测到 nvidia-smi，GPU 不可用。"
        return $false
    }

    Write-Info "检测到 NVIDIA GPU："
    $gpuInfo = & nvidia-smi --query-gpu name,memory.total --format=csv,noheader 2>$null
    if ($gpuInfo) {
        $gpuInfo | ForEach-Object { Write-Info "  - $_" }
    }

    $dockerInfo = docker info 2>&1 | Out-String
    if ($dockerInfo -notmatch "nvidia") {
        Write-Warn "Docker 中未检测到 NVIDIA Container Toolkit。"
        Write-Warn "GPU 模式可能无法使用。详见：https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html"
        if (-not (Read-YesNo "仍使用 GPU 模式？" "n")) {
            return $false
        }
    }

    return $true
}

# ── 国内镜像源 ────────────────────────────────────────────────────────────────

# 判断当前是否位于中国大陆：依次看时区、系统区域设置、公网 IP 归属地
function Test-InChina {
    # 显式指定 -ChinaMirrors 时直接认定
    if ($ChinaMirrors) { return $true }

    # 1) 时区（Windows 时区 ID 为 "China Standard Time"）
    try {
        $tzId = [System.TimeZoneInfo]::Local.Id
        if ($tzId -match "China Standard Time|Asia/Shanghai|Asia/Chongqing|Asia/Urumqi|Asia/Harbin") {
            return $true
        }
    } catch {}

    # 2) 系统区域设置
    try {
        $cult = [System.Globalization.CultureInfo]::CurrentCulture.Name
        if ($cult -ieq "zh-CN" -or $cult -ieq "zh-Hans") { return $true }
    } catch {}

    # 3) 公网 IP 归属地兜底
    try {
        $country = (Invoke-RestMethod -Uri "https://ipinfo.io/country" -TimeoutSec 5 -ErrorAction Stop).Trim()
        if ($country -eq "CN") { return $true }
    } catch {}

    return $false
}

# 测试单个镜像源可达性：/v2/ 端点返回 200/401/403 均视为可用
function Test-Mirror {
    param([string]$Mirror)
    $code = 0
    try {
        $resp = Invoke-WebRequest -Uri "$Mirror/v2/" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        $code = [int]$resp.StatusCode
    } catch {
        if ($_.Exception.Response) {
            $code = [int]$_.Exception.Response.StatusCode
        } else {
            return $false
        }
    }
    return ($code -eq 200 -or $code -eq 401 -or $code -eq 403)
}

# 重启 Docker Desktop 以使 daemon.json 配置生效
function Restart-DockerDesktop {
    Write-Info "正在重启 Docker Desktop 以应用镜像源配置..."

    # 优先尝试优雅关闭，超时后再强制结束
    $dockerProc = Get-Process "Docker Desktop" -ErrorAction SilentlyContinue
    if ($dockerProc) {
        try {
            $dockerProc | Stop-Process -Force -ErrorAction Stop
        } catch {}
        Write-Info "已关闭 Docker Desktop，等待进程退出..."
        Start-Sleep -Seconds 5
    }

    # 同时清理可能残留的后端进程
    Get-Process -Name "com.docker.backend","vpnkit-bridge","com.docker.service" -ErrorAction SilentlyContinue |
        ForEach-Object { try { $_ | Stop-Process -Force -ErrorAction SilentlyContinue } catch {} }

    # 启动 Docker Desktop
    $dockerExe = "${env:ProgramFiles}\Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path $dockerExe)) {
        $dockerExe = "${env:LOCALAPPDATA}\Programs\Docker\Docker\Docker Desktop.exe"
    }
    if (-not (Test-Path $dockerExe)) {
        Write-Warn "未找到 Docker Desktop 可执行文件，请手动重启 Docker Desktop。"
        return $false
    }

    Start-Process $dockerExe
    Write-Info "等待 Docker Desktop 重新启动..."
    $retries = 0
    while (-not (Test-DockerRunning) -and $retries -lt 60) {
        Start-Sleep -Seconds 3
        $retries++
        Write-Host -NoNewline "."
    }
    Write-Host ""

    if (-not (Test-DockerRunning)) {
        Write-Warn "Docker Desktop 未能在规定时间内重启完成。"
        return $false
    }

    Write-Info "Docker Desktop 已重启。"
    return $true
}

# 自动写入 Docker daemon.json 并重启 Docker Desktop 使镜像加速源生效
# 仅当显式 -ChinaMirrors 或检测到位于中国大陆时才配置；仅写入可达的镜像源
function Configure-Mirrors {
    # 决定是否配置：显式 -ChinaMirrors 或检测到位于中国大陆
    if (-not $ChinaMirrors) {
        if (Test-InChina) {
            Write-Info "检测到当前位于中国大陆，自动配置 Docker 镜像加速源。"
        } else {
            Write-Info "未检测到位于中国大陆，跳过镜像加速源配置。（如需启用请加 -ChinaMirrors 参数）"
            return
        }
    }

    Write-Step "配置 Docker 镜像加速源..."

    # 测试每个镜像源的可达性，仅保留可用者
    Write-Info "测试镜像源可达性（仅保留可用源）..."
    $availableMirrors = @()
    foreach ($mirror in $ChinaMirrorList) {
        Write-Host -NoNewline "  测试 ${mirror} ... "
        if (Test-Mirror $mirror) {
            Write-Host "可用" -ForegroundColor Green
            $availableMirrors += $mirror
        } else {
            Write-Host "不可达，跳过" -ForegroundColor Yellow
        }
    }

    if ($availableMirrors.Count -eq 0) {
        Write-Warn "没有可用的镜像源，跳过配置。"
        return
    }

    $dockerConfigDir = Join-Path $env:USERPROFILE ".docker"
    $daemonJsonPath = Join-Path $dockerConfigDir "daemon.json"

    if (-not (Test-Path $dockerConfigDir)) {
        New-Item -ItemType Directory -Path $dockerConfigDir -Force | Out-Null
    }

    # 读取并解析现有 daemon.json，保留已有字段（兼容 PowerShell 5.1 与 7+）
    $config = $null
    if (Test-Path $daemonJsonPath) {
        try {
            $raw = Get-Content $daemonJsonPath -Raw -Encoding UTF8
            if (-not [string]::IsNullOrWhiteSpace($raw)) {
                $config = $raw | ConvertFrom-Json
            }
        } catch {
            $backupPath = "$daemonJsonPath.bak"
            Copy-Item $daemonJsonPath $backupPath -Force
            Write-Warn "现有 daemon.json 解析失败，已备份至 $backupPath"
            $config = $null
        }
    }

    # 构建有序字典，保留原配置并覆盖 registry-mirrors
    $newConfig = [ordered]@{}
    if ($config) {
        $config.PSObject.Properties | ForEach-Object {
            $newConfig[$_.Name] = $_.Value
        }
    }

    # 若已配置相同的镜像源集合（忽略顺序），则无需重复写入与重启
    $existing = @($newConfig["registry-mirrors"] | Where-Object { $_ })
    if ($existing.Count -gt 0) {
        $existingSorted = ($existing | Sort-Object) -join ","
        $availableSorted = ($availableMirrors | Sort-Object) -join ","
        if ($existingSorted -eq $availableSorted) {
            Write-Info "镜像加速源已配置且与当前可用集合一致，无需重复操作。"
            Write-Log "镜像加速源已存在，跳过写入"
            return
        }
    }

    $newConfig["registry-mirrors"] = $availableMirrors
    $jsonOut = $newConfig | ConvertTo-Json -Depth 10
    Set-Content -Path $daemonJsonPath -Value $jsonOut -Encoding UTF8

    Write-Info "已写入可用镜像加速源到 $daemonJsonPath"
    Write-Host ""
    Write-Host "  {" -ForegroundColor White
    Write-Host "    `"registry-mirrors`": [" -ForegroundColor White
    foreach ($mirror in $availableMirrors) {
        Write-Host "      `"$mirror`"," -ForegroundColor White
    }
    Write-Host "    ]" -ForegroundColor White
    Write-Host "  }" -ForegroundColor White
    Write-Host ""
    Write-Log "已写入 Docker 镜像加速源配置: $daemonJsonPath"

    # 重启 Docker Desktop 使配置生效
    if (-not (Restart-DockerDesktop)) {
        Write-Warn "配置已写入，但 Docker Desktop 未能自动重启。"
        Write-Info "请手动重启 Docker Desktop 后重新运行本脚本。"
        if (-not (Read-YesNo "是否在手动重启后继续？" "y")) {
            Stop-Script "请重启 Docker Desktop 后重新运行脚本。"
        }
    }
}

# ── 配置收集 ──────────────────────────────────────────────────────────────────

function Collect-Config {
    Write-Step "收集配置信息..."

    # 安装目录
    if ([string]::IsNullOrWhiteSpace($script:InstallDir)) {
        $script:InstallDir = Read-Prompt "安装目录" $DefaultInstallDir
    }
    while ($true) {
        if (Test-Path $script:InstallDir) {
            break
        }
        $installParent = Split-Path $script:InstallDir -Parent
        if (Test-Path $installParent) {
            if (Read-YesNo "安装目录不存在：$($script:InstallDir)。是否创建？" "y") {
                try {
                    New-Item -ItemType Directory -Path $script:InstallDir -Force | Out-Null
                    Write-Info "已创建目录：$($script:InstallDir)"
                    break
                } catch {
                    Write-Err "创建目录失败：$($script:InstallDir)"
                    if ($Yes) {
                        Stop-Script "无法创建安装目录，请检查权限。"
                    }
                }
            }
        } else {
            Write-Warn "父目录不存在：$installParent"
        }
        if ($Yes) {
            Stop-Script "安装目录不存在且无法创建：$($script:InstallDir)"
        }
        $script:InstallDir = Read-Prompt "安装目录" $DefaultInstallDir
    }

    # 照片目录（向导式循环输入）
    $validatedDirs = @()

    if ([string]::IsNullOrWhiteSpace($PhotoDir)) {
        # 交互式逐个输入
        Write-Host ""
        Write-Info "请输入您的照片文件夹路径（一次一个，之后可以继续添加）。"
        while ($true) {
            $inputDir = Read-Prompt "照片文件夹路径" ""
            if ([string]::IsNullOrWhiteSpace($inputDir)) {
                if ($validatedDirs.Count -eq 0) {
                    Write-Warn "照片文件夹是必需的。"
                    if ($Yes) {
                        Stop-Script "非交互模式下必须通过 -PhotoDir 指定照片目录。"
                    }
                    continue
                }
                break
            }

            $currentDir = $inputDir.Trim().Trim('"', "'")

            # 验证目录
            while ($true) {
                if (Test-Path $currentDir) {
                    $validatedDirs += $currentDir
                    Write-Info "已添加：$currentDir"
                    break
                }
                if ($Yes) {
                    Write-Warn "照片目录不存在：$currentDir"
                    Stop-Script "照片目录必须存在。请创建后或通过 -PhotoDir 指定有效路径。"
                }
                Write-Warn "目录不存在：$currentDir"
                Write-Host "  1) 创建此目录"
                Write-Host "  2) 输入其他路径"
                Write-Host "  3) 取消"
                $choice = Read-Host "请选择 [1/2/3]"
                switch ($choice) {
                    "1" {
                        try {
                            New-Item -ItemType Directory -Path $currentDir -Force | Out-Null
                            Write-Info "已创建目录：$currentDir"
                            $validatedDirs += $currentDir
                            break
                        } catch {
                            Write-Err "创建目录失败：$currentDir，请检查权限。"
                            continue
                        }
                    }
                    "2" {
                        $newDir = Read-Prompt "照片文件夹路径" ""
                        if (-not [string]::IsNullOrWhiteSpace($newDir)) {
                            $currentDir = $newDir.Trim().Trim('"', "'")
                            continue
                        }
                    }
                    default {
                        Stop-Script "已取消。"
                    }
                }
                break
            }

            # 询问是否继续添加
            if (-not (Read-YesNo "是否继续添加其他照片文件夹？" "n")) {
                break
            }
        }
    } else {
        # 命令行传入 -PhotoDir（逗号分隔兼容）
        $photoDirs = $PhotoDir -split "," | ForEach-Object { $_.Trim().Trim('"', "'") }
        foreach ($dir in $photoDirs) {
            $currentDir = $dir
            while ($true) {
                if (Test-Path $currentDir) {
                    $validatedDirs += $currentDir
                    break
                }
                if ($Yes) {
                    Write-Warn "照片目录不存在：$currentDir"
                    Stop-Script "照片目录必须存在。请创建后或通过 -PhotoDir 指定有效路径。"
                }
                Write-Warn "照片目录不存在：$currentDir"
                Write-Host "  1) 创建此目录"
                Write-Host "  2) 输入其他路径"
                Write-Host "  3) 取消"
                $choice = Read-Host "请选择 [1/2/3]"
                switch ($choice) {
                    "1" {
                        try {
                            New-Item -ItemType Directory -Path $currentDir -Force | Out-Null
                            Write-Info "已创建目录：$currentDir"
                            $validatedDirs += $currentDir
                            break
                        } catch {
                            Write-Err "创建目录失败：$currentDir，请检查权限。"
                            continue
                        }
                    }
                    "2" {
                        $newDir = Read-Prompt "照片文件夹路径" ""
                        if (-not [string]::IsNullOrWhiteSpace($newDir)) {
                            $currentDir = $newDir.Trim().Trim('"', "'")
                            continue
                        }
                    }
                    default {
                        Stop-Script "已取消。"
                    }
                }
            }
        }
    }

    $script:PhotoDir = $validatedDirs -join ","

    # 端口检查（自动分配，无需用户确认）
    $portPairs = @(
        @{ Name = "前端";      Var = "FrontendPort";  Default = 8082 },
        @{ Name = "后端 API";  Var = "ServerPort";    Default = 8800 },
        @{ Name = "AI 服务";   Var = "AiPort";        Default = 8801 },
        @{ Name = "PostgreSQL"; Var = "PostgresPort";  Default = 5532 }
    )

    foreach ($pair in $portPairs) {
        $currentVal = Get-Variable $pair.Var -ValueOnly -Scope Script
        if (-not (Test-PortAvailable $currentVal)) {
            $suggested = Get-SuggestedPort $currentVal
            Write-Info "端口 $($currentVal) 已被占用，已自动分配新端口 $($suggested)。"
            Set-Variable $pair.Var $suggested -Scope Script
        }
    }

    # AI 模式
    $script:DetectedAiMode = $AiMode
    if ($AiMode -eq "gpu") {
        if (-not (Test-GpuSupport)) {
            Write-Warn "将回退到 CPU 模式。"
            $script:DetectedAiMode = "cpu"
        }
    } else {
        try {
            $cpuName = (Get-CimInstance Win32_Processor | Select-Object -First 1).Name
            if ($cpuName -match "Intel") {
                $script:DetectedAiMode = "openvino"
            }
        } catch {}
    }

    # 设置日志文件路径（安装目录已确定）
    $script:LogFile = Join-Path $script:InstallDir "install.log"
}

# ── 安装前确认摘要 ────────────────────────────────────────────────────────────

function Show-ConfirmSummary {
    Write-Host ""
    Write-Host "  ┌─────────────────────────────────────────────┐" -ForegroundColor Cyan
    Write-Host "  │          安装配置确认                        │" -ForegroundColor Cyan
    Write-Host "  ├─────────────────────────────────────────────┤" -ForegroundColor Cyan
    Write-Host "  │  安装目录:  $($script:InstallDir)" -ForegroundColor White
    $photoDisplay = $script:PhotoDir -replace ",", ", "
    Write-Host "  │  照片目录:  $photoDisplay" -ForegroundColor White
    Write-Host "  │  前端端口:  $FrontendPort" -ForegroundColor White
    Write-Host "  │  AI 模式:   $script:DetectedAiMode" -ForegroundColor White
    Write-Host "  │  数据库密码: $script:PgPassword" -ForegroundColor White
    Write-Host "  │              （请妥善保管，升级时自动保留）  " -ForegroundColor Gray
    Write-Host "  └─────────────────────────────────────────────┘" -ForegroundColor Cyan
    Write-Host ""

    if (-not (Read-YesNo "确认以上配置无误，开始安装？" "y")) {
        Stop-Script "已取消。"
    }
    Write-Log "用户确认安装配置"
}

# ── 文件生成 ──────────────────────────────────────────────────────────────────

function Resolve-PgPassword {
    # 重新安装到同一目录时，pg_data 仍是用旧密码初始化的。若此时生成新密码写入
    # .env，server 会因密码不匹配连不上 postgres。故目录下已有 .env 且含密码时复用之。
    $envPath = Join-Path $script:InstallDir ".env"
    if (Test-Path $envPath) {
        $existing = $null
        Get-Content $envPath -ErrorAction SilentlyContinue | ForEach-Object {
            if ($_ -match '^POSTGRES_PASSWORD=(.*)$') {
                $existing = $Matches[1].Trim().Trim('"')
            }
        }
        if ($existing) {
            $script:PgPassword = $existing
            Write-Info "复用已有数据库密码（避免与现存 pg_data 不匹配）"
            return
        }
    }
    if (-not $script:PgPassword) { $script:PgPassword = New-RandomPassword }
}

function Generate-EnvFile {
    Write-Step "生成 .env 配置文件..."

    $envContent = @"
# TrailSnap 配置 — 由 install.ps1 v$ScriptVersion 生成
# https://github.com/LC044/TrailSnap

# 照片目录（逗号分隔，支持多个挂载点）
PHOTO_DIR="$PhotoDir"

# 端口
FRONTEND_PORT=$FrontendPort
SERVER_PORT=$ServerPort
AI_PORT=$AiPort
POSTGRES_PORT=$PostgresPort

# 时区
TZ="$Timezone"

# Docker 镜像版本标签（默认 latest，可修改为指定版本号，如 v1.0.0 等）
IMAGE_TAG="$Tag"

# AI 模式。可选：cpu、gpu、openvino
# GPU 需要用户手动指定，CPU 和 openvino 会自动检测。修改此环境变量可动态调整 AI 镜像。
AI_MODE="$script:DetectedAiMode"

# 数据库
POSTGRES_DB="$DefaultPgDb"
POSTGRES_USER="$DefaultPgUser"
POSTGRES_PASSWORD="$($script:PgPassword)"
"@

    $envPath = Join-Path $script:InstallDir ".env"
    Set-Content -Path $envPath -Value $envContent -Encoding UTF8 -NoNewline
    Write-Info "已创建 $envPath"
    Write-Log "已生成 .env 配置文件"
}

function Generate-ComposeFile {
    Write-Step "生成 docker-compose.yml..."

    $photoDirs = $PhotoDir -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ }

    # 升级 / 追加兼容：若已存在 docker-compose.yml 且含 /app/Photos 挂载行，则原样
    # 保留旧挂载目标（如 /app/Photos/ 或 /app/Photos1/ 或 /app/Photos/<name>），否则
    # 升级后容器内路径变化会让数据库里已索引的 file_path 全部失效。仅超出已有数量
    # 的新增目录才按 /app/Photos/<源目录名> 约定生成新挂载。
    # 同时去掉 :ro，保证照片删除等功能可用。
    $existingComposePath = Join-Path $script:InstallDir "docker-compose.yml"
    $preservedLines = @()
    $preservedTargets = @{}
    if (Test-Path $existingComposePath) {
        try {
            $oldLines = Get-Content $existingComposePath -Encoding UTF8
            foreach ($line in $oldLines) {
                if ($line -match ':\s*/app/Photos') {
                    $preservedLines += $line.TrimStart()
                    if ($line -match '/app/Photos[^":\s]*') {
                        $preservedTargets[$Matches[0]] = $true
                    }
                }
            }
        } catch {}
    }

    $photoVolumes = @()
    $usedNames = @{}
    # 已有挂载目标名加入占用集合，避免新增目录撞名
    foreach ($t in $preservedTargets.Keys) {
        $seg = ($t -split '/')[-1]
        if ($seg) { $usedNames[$seg] = $true }
    }

    for ($i = 0; $i -lt $photoDirs.Count; $i++) {
        $dir = $photoDirs[$i]
        if ($i -lt $preservedLines.Count) {
            # 复用已有挂载行，并去掉 :ro（转为可写，支持删除照片）
            $pl = $preservedLines[$i] -replace ':ro\s*(?=")', ''
            $photoVolumes += "      $pl"
            continue
        }
        # 新增目录：取源目录名作为图库标识（保留中文等 UTF-8 名称），清理非法字符
        $baseName = Split-Path $dir -Leaf
        $baseName = ($baseName -replace '[\\/]+', '_').Trim()
        if ([string]::IsNullOrWhiteSpace($baseName)) { $baseName = "gallery" }
        $finalName = $baseName
        $n = 2
        while ($usedNames.ContainsKey($finalName) -or $preservedTargets.ContainsKey("/app/Photos/$finalName")) {
            $finalName = "${baseName}_${n}"
            $n++
        }
        $usedNames[$finalName] = $true

        # 处理 Windows 路径反斜杠与空格，用双引号包裹映射；不使用 :ro
        $escapedDir = $dir -replace '\\', '\\' -replace '"', '\"'
        $photoVolumes += "      - `"${escapedDir}:/app/Photos/${finalName}`""
    }
    $photoVolumeStr = $photoVolumes -join "`n"

    $gpuBlock = ""
    if ($script:DetectedAiMode -eq "gpu") {
        $gpuBlock = @"

    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
"@
    }

    $composeContent = @"
services:
  postgres:
    image: pgvector/pgvector:pg18-trixie
    container_name: trailsnap-postgres
    restart: always
    environment:
      TZ: `${TZ}
      POSTGRES_DB: `${POSTGRES_DB}
      POSTGRES_USER: `${POSTGRES_USER}
      POSTGRES_PASSWORD: `${POSTGRES_PASSWORD}
      POSTGRES_INITDB_ARGS: "--encoding=UTF8 --lc-collate=C --lc-ctype=C"
      PGDATA: /var/lib/postgresql/data/pgdata
    networks: [app-network]
    volumes:
      - ./pg_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U `${POSTGRES_USER} -d `${POSTGRES_DB} -p 5432"]
      interval: 5s
      timeout: 5s
      retries: 5
      start_period: 10s

  server:
    image: siyuan044/trailsnap-server:`${IMAGE_TAG}
    container_name: trailsnap-server
    restart: always
    expose: ["8000"]
    ports:
      - "`${SERVER_PORT}:8000"
    networks: [app-network]
    volumes:
      - ./data:/app/data
$photoVolumeStr
    environment:
      - TZ=`${TZ}
      - DB_URL=postgresql://`${POSTGRES_USER}:`${POSTGRES_PASSWORD}@postgres:5432/`${POSTGRES_DB}
      - RAILWAY_DB_URL=postgresql://`${POSTGRES_USER}:`${POSTGRES_PASSWORD}@postgres:5432/railway
      - AI_API_URL=http://ai:8001
    depends_on:
      postgres:
        condition: service_healthy

  ai:
    image: siyuan044/trailsnap-ai:`${IMAGE_TAG}-`${AI_MODE}
    container_name: trailsnap-ai
    restart: always
    expose: ["8001"]
    ports:
      - "`${AI_PORT}:8001"
    networks: [app-network]
    volumes:
      - ./data:/app/data
    environment:
      - TZ=`${TZ}$gpuBlock

  frontend:
    image: siyuan044/trailsnap-frontend:`${IMAGE_TAG}
    container_name: trailsnap-frontend
    restart: always
    ports:
      - "`${FRONTEND_PORT}:80"
    depends_on: [server]
    networks: [app-network]
    environment:
      - TZ=`${TZ}

networks:
  app-network:
    driver: bridge
"@

    $composePath = Join-Path $script:InstallDir "docker-compose.yml"
    Set-Content -Path $composePath -Value $composeContent -Encoding UTF8 -NoNewline
    Write-Info "已创建 $composePath"
    Write-Log "已生成 docker-compose.yml"
}

# ── 健康检查 ──────────────────────────────────────────────────────────────────

function Wait-ForService {
    param(
        [string]$Name,
        [scriptblock]$TestBlock,
        [int]$TimeoutSeconds = 60
    )

    $interval = 5
    $elapsed = 0
    Write-Host -NoNewline "  等待 ${Name} 启动..."

    while ($elapsed -lt $TimeoutSeconds) {
        try {
            $result = & $TestBlock
            if ($result) {
                Write-Host " OK" -ForegroundColor Green
                return $true
            }
        } catch {}

        Start-Sleep -Seconds $interval
        $elapsed += $interval
        Write-Host -NoNewline "."
    }

    Write-Host " 失败" -ForegroundColor Red
    return $false
}

function Test-HealthCheck {
    Write-Step "运行健康检查..."
    Write-Info "首次启动需初始化数据库并加载 AI 模型，可能需要几分钟，请耐心等待..."

    $envFilePath = Join-Path $script:InstallDir ".env"
    if (Test-Path $envFilePath) {
        Get-Content $envFilePath | ForEach-Object {
            if ($_ -match "^([^#][^=]+)=(.*)$") {
                Set-Item -Path "env:$($Matches[1])" -Value $Matches[2]
            }
        }
    }

    $failed = $false

    $pgOk = Wait-ForService "PostgreSQL" {
        $status = docker inspect --format='{{.State.Health.Status}}' trailsnap-postgres 2>$null
        $status -match "healthy"
    } -TimeoutSeconds 90
    if (-not $pgOk) { $failed = $true }

    # AI 首次启动需加载 OCR/人脸/CLIP 等模型（openvino 尤慢），给到 5 分钟
    $aiOk = Wait-ForService "AI 服务" {
        try {
            $resp = Invoke-WebRequest -Uri "http://localhost:${AiPort}/health-check" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            $resp.StatusCode -eq 200
        } catch { $false }
    } -TimeoutSeconds 300
    if (-not $aiOk) { $failed = $true }

    # 后端首次启动需跑 alembic 迁移 + 导入 5A 景点 CSV，给到 4 分钟
    $srvOk = Wait-ForService "后端" {
        try {
            $resp = Invoke-WebRequest -Uri "http://localhost:${ServerPort}/health-check" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            $resp.StatusCode -eq 200
        } catch { $false }
    } -TimeoutSeconds 240
    if (-not $srvOk) { $failed = $true }

    $feOk = Wait-ForService "前端" {
        try {
            $resp = Invoke-WebRequest -Uri "http://localhost:${FrontendPort}" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            $resp.StatusCode -eq 200
        } catch { $false }
    } -TimeoutSeconds 90
    if (-not $feOk) { $failed = $true }

    if ($failed) {
        Write-Host ""
        Write-Err "部分服务健康检查失败。"
        Write-Info "正在查看日志..."
        Push-Location $script:InstallDir
        Invoke-Compose "--env-file .env logs --tail=50"
        Pop-Location
        Write-Host ""
        Write-Warn "手动查看日志：cd ${script:InstallDir}; $($script:ComposeCmd) --env-file .env logs -f"
        Write-Log "健康检查: 部分服务失败"
        return $false
    }

    Write-Log "健康检查: 全部通过"
    return $true
}

# ── 拉取与启动 ────────────────────────────────────────────────────────────────

function Invoke-Compose {
    param([string]$Arguments)
    # 使用 Invoke-Expression 避免手动按空格拆分参数导致路径含空格时出错
    Invoke-Expression "$($script:ComposeCmd) $Arguments"
}

function Pull-Images {
    Write-Step "拉取 Docker 镜像（可能需要几分钟，如果拉取失败，请检查网络和 Docker 配置。）..."
    if (-not $ChinaMirrors) {
        Write-Info "提示：如果您在中国大陆地区，镜像拉取慢，可取消安装并添加 -ChinaMirrors 参数重新运行"
    }
    Push-Location $script:InstallDir
    try {
        Invoke-Compose "--env-file .env pull"
        if ($LASTEXITCODE -ne 0) {
            Write-Err "拉取镜像失败。"
            if (-not $ChinaMirrors) {
                Write-Warn "如果您在国内，请尝试添加 -ChinaMirrors 参数重新运行。"
            }
            Stop-Script "镜像拉取失败，请检查网络和 Docker 配置。"
        }
    } finally {
        Pop-Location
    }
    Write-Log "Docker 镜像拉取完成"
}

function Start-Services {
    Write-Step "启动服务..."
    Push-Location $script:InstallDir
    try {
        Invoke-Compose "--env-file .env up -d"
    } finally {
        Pop-Location
    }
    Write-Info "服务已启动。"
    Write-Log "Docker 服务已启动"
}

# ── 成功横幅 ──────────────────────────────────────────────────────────────────

function Show-ServiceUrls {
    $lanIP = Get-LanIP
    Write-Host ""
    Write-Host "  访问地址：" -ForegroundColor Cyan
    Write-Host "  💻 本机访问:  http://localhost:${FrontendPort}" -ForegroundColor White
    if ($lanIP) {
        Write-Host "  📱 手机访问:  http://${lanIP}:${FrontendPort}  (需连接同一 Wi-Fi)" -ForegroundColor White
    }
    Write-Host ""
    Write-Host "  后端 API:  http://localhost:${ServerPort}/docs" -ForegroundColor Gray
    Write-Host "  AI 服务:   http://localhost:${AiPort}/docs" -ForegroundColor Gray
    Write-Host ""
}

function Write-Success {
    Write-Host ""
    Write-Host "  =======================================================" -ForegroundColor Green
    Write-Host "" -ForegroundColor Green
    Write-Host "        TrailSnap (行影集) 安装成功！" -ForegroundColor Green
    Write-Host "" -ForegroundColor Green
    Write-Host "  =======================================================" -ForegroundColor Green
    
    Show-ServiceUrls
    
    Write-Host "  下一步：" -ForegroundColor Cyan
    Write-Host "  1. 在浏览器中打开上面的访问地址"
    Write-Host "  2. 进入 更多 → 设置 → 外部图库"
    Write-Host "  3. 页面会自动检测到挂载的照片目录，勾选后点击「添加选中的图库并扫描」即可"
    Write-Host ""
    Write-Host "  管理命令（在 $($script:InstallDir) 目录下运行）：" -ForegroundColor Cyan
    Write-Host "    停止:    $($script:ComposeCmd) --env-file .env down"
    Write-Host "    重启:    $($script:ComposeCmd) --env-file .env restart"
    Write-Host "    日志:    $($script:ComposeCmd) --env-file .env logs -f"
    Write-Host "    升级:    .\install.ps1 -Upgrade"
    Write-Host ""

    # 删除可能存在的桌面快捷方式
    $desktopPath = [Environment]::GetFolderPath("Desktop")
    $shortcutPath = Join-Path $desktopPath "Continue-TrailSnap-Install.bat"
    if (Test-Path $shortcutPath) {
        Remove-Item $shortcutPath -Force -ErrorAction SilentlyContinue
        Write-Info "已清理桌面快捷方式。"
    }

    # 自动打开浏览器
    Write-Info "正在打开浏览器..."
    try {
        Start-Process "http://localhost:${FrontendPort}"
    } catch {
        Write-Warn "无法自动打开浏览器，请手动访问 http://localhost:${FrontendPort}"
    }

    Write-Log "安装成功完成"
}

# ── 升级 ──────────────────────────────────────────────────────────────────────

function Do-Upgrade {
    Write-Step "正在升级 TrailSnap..."

    $envFilePath = Join-Path $script:InstallDir ".env"
    if (-not (Test-Path $envFilePath)) {
        Stop-Script "未在 $($script:InstallDir) 找到已安装的实例。请直接运行（不带 -Upgrade）来安装。"
    }

    # 设置日志文件
    $script:LogFile = Join-Path $script:InstallDir "install.log"

    Get-Content $envFilePath | ForEach-Object {
        if ($_ -match "^([^#][^=]+)=(.*)$") {
            $key = $Matches[1].Trim()
            $value = $Matches[2].Trim().Trim('"')
            Set-Item -Path "env:$key" -Value $value
            switch ($key) {
                "FRONTEND_PORT"   { $script:FrontendPort = [int]$value }
                "SERVER_PORT"     { $script:ServerPort = [int]$value }
                "AI_PORT"         { $script:AiPort = [int]$value }
                "POSTGRES_PORT"   { $script:PostgresPort = [int]$value }
                "TZ"              { $script:Timezone = $value }
                "IMAGE_TAG"       { $script:Tag = $value }
                "AI_MODE"         { $script:DetectedAiMode = $value }
                "PHOTO_DIR"       { $script:PhotoDir = $value }
                "POSTGRES_PASSWORD" { $script:PgPassword = $value }
            }
        }
    }

    Write-Log "开始升级，保留现有配置"

    Generate-ComposeFile
    Pull-Images

    Push-Location $script:InstallDir
    try {
        Invoke-Compose "--env-file .env up -d --remove-orphans"
    } finally {
        Pop-Location
    }

    Test-HealthCheck | Out-Null

    Write-Success
    Write-Info "升级完成。您的 .env 配置已保留。"
}

# ── 添加新照片文件夹 ──────────────────────────────────────────────────────────

function Add-PhotoDir {
    param([string]$NewDir)

    $composePath = Join-Path $script:InstallDir "docker-compose.yml"
    $envPath = Join-Path $script:InstallDir ".env"
    if (-not (Test-Path $composePath) -or -not (Test-Path $envPath)) {
        Stop-Script "未在 $($script:InstallDir) 找到已安装的实例。请先安装 TrailSnap。"
    }
    $script:LogFile = Join-Path $script:InstallDir "install.log"

    if ([string]::IsNullOrWhiteSpace($NewDir)) {
        $NewDir = Read-Prompt "请输入要添加的照片文件夹路径" ""
        if ([string]::IsNullOrWhiteSpace($NewDir)) {
            Stop-Script "未输入路径。"
        }
    }
    $NewDir = $NewDir.Trim().Trim('"', "'")

    # 校验目录存在（不可读时给出明确错误）；不存在时询问是否创建
    while (-not (Test-Path $NewDir)) {
        if ($Yes) {
            Stop-Script "照片目录不存在：$NewDir"
        }
        Write-Warn "目录不存在：$NewDir"
        Write-Host "  1) 创建此目录"
        Write-Host "  2) 输入其他路径"
        Write-Host "  3) 取消"
        $choice = Read-Host "请选择 [1/2/3]"
        switch ($choice) {
            "1" {
                try {
                    New-Item -ItemType Directory -Path $NewDir -Force | Out-Null
                    Write-Info "已创建目录：$NewDir"
                } catch {
                    Write-Err "创建目录失败：$NewDir，请检查权限。"
                    continue
                }
                break
            }
            "2" {
                $alt = Read-Prompt "照片文件夹路径" ""
                if ([string]::IsNullOrWhiteSpace($alt)) { Stop-Script "已取消。" }
                $NewDir = $alt.Trim().Trim('"', "'")
                continue
            }
            default { Stop-Script "已取消。" }
        }
    }

    # 读取现有 .env，保留全部配置
    Get-Content $envPath | ForEach-Object {
        if ($_ -match "^([^#][^=]+)=(.*)$") {
            $key = $Matches[1].Trim()
            $value = $Matches[2].Trim().Trim('"')
            Set-Item -Path "env:$key" -Value $value
            switch ($key) {
                "FRONTEND_PORT"   { $script:FrontendPort = [int]$value }
                "SERVER_PORT"     { $script:ServerPort = [int]$value }
                "AI_PORT"         { $script:AiPort = [int]$value }
                "POSTGRES_PORT"   { $script:PostgresPort = [int]$value }
                "TZ"              { $script:Timezone = $value }
                "IMAGE_TAG"       { $script:Tag = $value }
                "AI_MODE"         { $script:DetectedAiMode = $value }
                "PHOTO_DIR"       { $script:PhotoDir = $value }
                "POSTGRES_PASSWORD" { $script:PgPassword = $value }
            }
        }
    }

    # 去重：若已登记则直接提示
    $existing = if ($script:PhotoDir) { $script:PhotoDir -split "," | ForEach-Object { $_.Trim() } } else { @() }
    $existingResolved = $existing | ForEach-Object { (Resolve-Path $_ -ErrorAction SilentlyContinue).Path }
    $newResolved = (Resolve-Path $NewDir).Path
    if ($existingResolved -and ($existingResolved -contains $newResolved)) {
        Write-Info "该照片文件夹已挂载，无需重复添加：$NewDir"
        return
    }

    # 追加到 PHOTO_DIR
    if ($script:PhotoDir) {
        $script:PhotoDir = "$($script:PhotoDir),$NewDir"
    } else {
        $script:PhotoDir = $NewDir
    }

    Write-Log "添加新照片文件夹：$NewDir"
    Generate-EnvFile
    Generate-ComposeFile

    # 重建 server 容器使新挂载生效（其它容器不受影响）
    Write-Step "应用新挂载并重启服务..."
    Push-Location $script:InstallDir
    try {
        Invoke-Compose "--env-file .env up -d --remove-orphans"
    } finally {
        Pop-Location
    }

    Write-Info "已添加照片文件夹：$NewDir"
    Write-Info "请在「更多 → 设置 → 外部图库」中点击「重新检测」，勾选新目录并添加扫描。"
    Write-Host ""
    Write-Host "  管理命令（在 $($script:InstallDir) 目录下运行）：" -ForegroundColor Cyan
    Write-Host "    日志:    $($script:ComposeCmd) --env-file .env logs -f"
    Write-Host ""
}

# ── 卸载 ──────────────────────────────────────────────────────────────────────

function Do-Uninstall {
    Write-Step "正在卸载 TrailSnap..."

    $composePath = Join-Path $script:InstallDir "docker-compose.yml"
    if (-not (Test-Path $composePath)) {
        Stop-Script "未在 $($script:InstallDir) 找到已安装的实例。"
    }

    Push-Location $script:InstallDir
    try {
        Invoke-Compose "--env-file .env down" 2>$null
    } finally {
        Pop-Location
    }
    Write-Info "容器已停止并移除。"

    if ($Purge) {
        if (Read-YesNo "这将删除所有数据（数据库、模型、上传文件）。确定吗？" "n") {
            Remove-Item -Path (Join-Path $script:InstallDir "pg_data") -Recurse -Force -ErrorAction SilentlyContinue
            Remove-Item -Path (Join-Path $script:InstallDir "data") -Recurse -Force -ErrorAction SilentlyContinue
            Remove-Item -Path (Join-Path $script:InstallDir ".env") -Force -ErrorAction SilentlyContinue
            Remove-Item -Path (Join-Path $script:InstallDir "docker-compose.yml") -Force -ErrorAction SilentlyContinue
            Write-Info "所有数据已删除。"
        }
    } else {
        Write-Info "数据目录已保留在 $($script:InstallDir)/"
        Write-Info "如需删除数据，请运行：.\install.ps1 -Uninstall -Purge"
    }

    Write-Info "卸载完成。"
    if ($script:LogFile -and (Test-Path $script:LogFile)) {
        Write-Log "卸载完成"
    }
}

# ── 使用帮助 ──────────────────────────────────────────────────────────────────

function Write-Usage {
    Write-Host @"
TrailSnap (行影集) — Windows 一键安装脚本

用法：
  .\install.ps1 [选项]

选项：
  -PhotoDir <路径>       照片目录（逗号分隔支持多个）
  -InstallDir <路径>     安装目录（默认：~/trailsnap）
  -FrontendPort <端口>   前端端口（默认：8082）
  -ServerPort <端口>     后端 API 端口（默认：8800）
  -AiPort <端口>         AI 服务端口（默认：8801）
  -PostgresPort <端口>   PostgreSQL 端口（默认：5532）
  -Timezone <时区>       时区（默认：Asia/Shanghai）
  -AiMode <cpu|gpu>      AI 模式（默认：cpu）
  -Tag <版本号>          Docker 镜像版本标签（默认：latest）
  -ChinaMirrors          配置国内 Docker 镜像加速源
  -Yes                   非交互模式：接受所有默认值
  -Upgrade               升级已安装的实例
  -Uninstall             卸载 TrailSnap
  -Purge                 删除所有数据（与 -Uninstall 配合使用）
  -AddPhotoDir <路径>    向已安装实例追加一个新的照片文件夹
  -Help                  显示此帮助信息

示例：
  # 交互式安装
  .\install.ps1

  # 非交互式安装
  .\install.ps1 -PhotoDir "D:\Photos" -ChinaMirrors -Yes

  # GPU 模式
  .\install.ps1 -PhotoDir "D:\Photos" -AiMode gpu

  # 升级
  .\install.ps1 -Upgrade

  # 添加新的照片文件夹
  .\install.ps1 -AddPhotoDir "E:\NewPhotos"

  # 卸载（保留数据）
  .\install.ps1 -Uninstall

  # 卸载（删除所有数据）
  .\install.ps1 -Uninstall -Purge
"@
}

# ── 主流程 ────────────────────────────────────────────────────────────────────

if ($Help) {
    Write-Usage
    exit 0
}

Write-Banner

# 生成随机数据库密码
$script:PgPassword = New-RandomPassword

Write-Log "TrailSnap 安装脚本 v$ScriptVersion 启动"

# 处理卸载
if ($Uninstall) {
    if ([string]::IsNullOrWhiteSpace($script:InstallDir)) {
        $script:InstallDir = Read-Prompt "安装目录" $DefaultInstallDir
    }
    $script:LogFile = Join-Path $script:InstallDir "install.log"
    Do-Uninstall
    exit 0
}

# 处理添加新照片文件夹
if ($AddPhotoDir -ne "") {
    if ([string]::IsNullOrWhiteSpace($script:InstallDir)) {
        $script:InstallDir = Read-Prompt "安装目录" $DefaultInstallDir
    }
    Ensure-Docker
    Add-PhotoDir -NewDir $AddPhotoDir
    exit 0
}

# 检查是否已有安装（未指定 -InstallDir 时检查默认目录，但不写入 $script:InstallDir，
# 以便后续 Collect-Config 仍能交互式询问安装目录）
$checkDir = if ([string]::IsNullOrWhiteSpace($script:InstallDir)) { $DefaultInstallDir } else { $script:InstallDir }
$existingCompose = Join-Path $checkDir "docker-compose.yml"
if (Test-Path $existingCompose) {
    # 在默认目录检测到已有安装时，将其作为操作目标
    $script:InstallDir = $checkDir
    # 如果找到了配置文件，先解析它以获取端口等信息
    $envFilePath = Join-Path $script:InstallDir ".env"
    if (Test-Path $envFilePath) {
        Get-Content $envFilePath | ForEach-Object {
            if ($_ -match "^([^#][^=]+)=(.*)$") {
                $key = $Matches[1].Trim()
                $value = $Matches[2].Trim().Trim('"')
                Set-Item -Path "env:$key" -Value $value
                switch ($key) {
                    "FRONTEND_PORT"   { $script:FrontendPort = [int]$value }
                    "SERVER_PORT"     { $script:ServerPort = [int]$value }
                    "AI_PORT"         { $script:AiPort = [int]$value }
                }
            }
        }
    }

    $isServiceRunning = $false
    # 尝试检测服务状态（这需要 Docker，如果不在此处调用 docker 命令则可以简化）
    try {
        $dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
        if ($dockerCmd) {
            Push-Location $script:InstallDir
            $psOutput = docker compose --env-file .env ps -q 2>$null
            if (-not [string]::IsNullOrWhiteSpace($psOutput)) {
                $isServiceRunning = $true
            }
            Pop-Location
        }
    } catch {}

    Write-Warn "在 $($script:InstallDir) 检测到已有安装。"
    Write-Host "请选择操作："
    Write-Host "  1) 升级到最新版本"
    Write-Host "  2) 重新安装"
    Write-Host "  3) 卸载（保留照片和数据）"
    Write-Host "  4) 卸载（保留照片，删除其他数据）"
    if ($isServiceRunning) {
        Write-Host "  5) 关闭服务"
        Write-Host "  6) 重启服务"
    } else {
        Write-Host "  5) 启动服务"
    }
    Write-Host "  7) 添加新的照片文件夹"
    Write-Host "  0) 退出"

    $choice = Read-Host "请选择 [0-7]"
    switch ($choice) {
        "1" {
            Ensure-Docker
            Configure-Mirrors
            Do-Upgrade
            exit 0
        }
        "2" {
            # 继续执行重新安装流程
        }
        "3" {
            Ensure-Docker
            $Purge = $false
            Do-Uninstall
            exit 0
        }
        "4" {
            Ensure-Docker
            $Purge = $true
            Do-Uninstall
            exit 0
        }
        "5" {
            Ensure-Docker
            if ($isServiceRunning) {
                Push-Location $script:InstallDir
                try {
                    Invoke-Compose "--env-file .env down"
                } finally {
                    Pop-Location
                }
                Write-Info "服务已关闭。"
            } else {
                Push-Location $script:InstallDir
                try {
                    Invoke-Compose "--env-file .env up -d"
                } finally {
                    Pop-Location
                }
                Write-Info "服务已启动。"
                Show-ServiceUrls
            }
            exit 0
        }
        "6" {
            Ensure-Docker
            if ($isServiceRunning) {
                Push-Location $script:InstallDir
                try {
                    Invoke-Compose "--env-file .env restart"
                } finally {
                    Pop-Location
                }
                Write-Info "服务已重启。"
                Show-ServiceUrls
                exit 0
            } else {
                Stop-Script "无效选择。"
            }
        }
        "7" {
            Ensure-Docker
            Add-PhotoDir -NewDir ""
            exit 0
        }
        "0" {
            Stop-Script "已退出。"
        }
        default {
            Stop-Script "无效选择。"
        }
    }
}

# 确保 Docker 可用
Ensure-Docker

# 处理升级
if ($Upgrade) {
    Configure-Mirrors
    Do-Upgrade
    exit 0
}

# 交互式收集配置（安装目录、照片目录、端口、AI 模式）
Collect-Config

# 检查硬件资源（依赖安装目录以判断磁盘空间）
Test-Hardware

# 复用已有 .env 中的数据库密码（重新安装到同一目录时避免与 pg_data 不匹配）
Resolve-PgPassword

# 安装前确认摘要
Show-ConfirmSummary

# 创建安装目录
New-Item -ItemType Directory -Path $script:InstallDir -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $script:InstallDir "pg_data") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $script:InstallDir "data") -Force | Out-Null

# 生成配置文件
Generate-EnvFile
Generate-ComposeFile

# 配置国内镜像加速源（在拉取镜像之前，加速后续下载）
Configure-Mirrors

# 拉取并启动
Pull-Images
Start-Services

# 健康检查
if (Test-HealthCheck) {
    Write-Success
} else {
    $lanIP = Get-LanIP
    Write-Host ""
    Write-Warn "部分服务可能需要更多时间启动。"
    Write-Info "查看状态：cd $($script:InstallDir); $($script:ComposeCmd) --env-file .env ps"
    Write-Info "查看日志：cd $($script:InstallDir); $($script:ComposeCmd) --env-file .env logs -f"
    Write-Host ""
    Write-Host "  访问地址：" -ForegroundColor Cyan
    Write-Host "  💻 本机访问:  http://localhost:${FrontendPort}" -ForegroundColor White
    if ($lanIP) {
        Write-Host "  📱 手机访问:  http://${lanIP}:${FrontendPort}  (需连接同一 Wi-Fi)" -ForegroundColor White
    }
    Write-Host "  后端 API:  http://localhost:${ServerPort}/docs" -ForegroundColor Gray
    Write-Log "安装完成，但部分服务健康检查未通过"
}
