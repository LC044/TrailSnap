<#
.SYNOPSIS
TrailSnap (行影集) — One-Click Installation Script for Windows

.DESCRIPTION
Automatically configures Docker, sets up registry mirrors, and starts TrailSnap.
Supports interactive and non-interactive modes, GPU acceleration, and upgrade/uninstall.

.EXAMPLE
# Interactive install
.\install.ps1

# Non-interactive install
.\install.ps1 -PhotoDir "D:\Photos" -ChinaMirrors -Yes

# GPU mode
.\install.ps1 -PhotoDir "D:\Photos" -AiMode gpu

# Upgrade
.\install.ps1 -Upgrade

# Uninstall
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
    [ValidateSet("latest", "master")]
    [string]$Tag = "latest",
    [switch]$ChinaMirrors,
    [switch]$Yes,
    [switch]$Upgrade,
    [switch]$Uninstall,
    [switch]$Purge,
    [switch]$Help
)

# ── Constants ────────────────────────────────────────────────────────────────
$ScriptVersion = "1.0.0"
$DefaultInstallDir = Join-Path $env:USERPROFILE "trailsnap"
$DefaultPgDb = "trailsnap"
$DefaultPgUser = "trailsnap"
$DefaultPgPassword = "trailsnap"

# Fix Chinese display: ensure console uses UTF-8 encoding
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
try { chcp 65001 >$null } catch {}

# Promote param to script scope so functions can access it
$script:InstallDir = $InstallDir
$script:ComposeCmd = ""

$ChinaMirrorList = @(
    "https://docker.1ms.run",
    "https://docker.xuanyuan.me",
    "https://dockerproxy.net"
)

# ── Utility Functions ────────────────────────────────────────────────────────

function Write-Banner {
    Write-Host ""
    Write-Host "  ╔═══════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "  ║                                               ║" -ForegroundColor Cyan
    Write-Host "  ║       TrailSnap  行影集  — 一键安装           ║" -ForegroundColor Cyan
    Write-Host "  ║       AI-Powered Self-Hosted Photo Album      ║" -ForegroundColor Cyan
    Write-Host "  ║                                               ║" -ForegroundColor Cyan
    Write-Host "  ╚═══════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO]  $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARN]  $Message" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message" -ForegroundColor Blue
}

function Stop-Script {
    param([string]$Message)
    Write-Err $Message
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
    if ([string]::IsNullOrWhiteSpace($answer)) { $Default } else { $answer }
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
    $answer -match "^[yY]"
}

# ── Docker Detection & Installation ─────────────────────────────────────────

function Test-DockerInstalled {
    $cmd = Get-Command docker -ErrorAction SilentlyContinue
    return ($null -ne $cmd)
}

function Test-DockerRunning {
    try {
        $result = docker info 2>&1
        # docker info returns non-zero exit code when daemon is not running
        if ($LASTEXITCODE -eq 0) {
            return $true
        }
        return $false
    } catch {
        return $false
    }
}

function Get-ComposeCmd {
    # Try Docker Compose V2 plugin
    try {
        $null = docker compose version 2>&1
        if ($LASTEXITCODE -eq 0) {
            return "docker compose"
        }
    } catch {}
    # Try Docker Compose V1 standalone
    $cmd = Get-Command docker-compose -ErrorAction SilentlyContinue
    if ($null -ne $cmd) {
        return "docker-compose"
    }
    return $null
}

function Install-DockerDesktop {
    Write-Step "Installing Docker Desktop..."

    # Check winget
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Info "Installing Docker Desktop via winget..."
        winget install Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
        Write-Info "Docker Desktop installed. Please start it from the Start Menu."
        Write-Warn "You may need to restart this script after Docker Desktop starts."
        Stop-Script "Please start Docker Desktop and re-run this script."
    } else {
        Write-Host ""
        Write-Err "winget is not available. Please install Docker Desktop manually:"
        Write-Host "  https://docs.docker.com/desktop/install/windows-install/" -ForegroundColor Cyan
        Write-Host ""
        Stop-Script "Docker is required. Please install it and re-run this script."
    }
}

function Ensure-WSL2 {
    Write-Step "Checking WSL2..."
    try {
        $wslStatus = wsl --status 2>&1
        Write-Info "WSL2 is available."
    } catch {
        Write-Warn "WSL2 is not installed."
        if (Read-YesNo "Install WSL2 now?" "y") {
            wsl --install --no-distribution
            Write-Warn "WSL2 installed. A system restart may be required."
            Stop-Script "Please restart your computer and re-run this script."
        } else {
            Stop-Script "WSL2 is required for Docker Desktop on Windows."
        }
    }
}

function Ensure-Docker {
    Write-Step "Checking Docker..."

    # Check WSL2 first (required for Docker Desktop on Windows)
    Ensure-WSL2

    if (-not (Test-DockerInstalled)) {
        Write-Warn "Docker is not installed."
        if (Read-YesNo "Do you want to install Docker Desktop automatically?" "y") {
            Install-DockerDesktop
        } else {
            Stop-Script "Docker is required. Please install it: https://docs.docker.com/desktop/install/windows-install/"
        }
    }

    # Check Docker is running
    if (-not (Test-DockerRunning)) {
        Write-Warn "Docker Desktop is not running."
        Write-Info "Starting Docker Desktop..."
        $dockerExe = Get-Command "Docker Desktop" -ErrorAction SilentlyContinue
        if (-not $dockerExe) {
            # Try common install paths
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
            Write-Info "Waiting for Docker Desktop to start..."
            $retries = 0
            while (-not (Test-DockerRunning) -and $retries -lt 60) {
                Start-Sleep -Seconds 3
                $retries++
                Write-Host -NoNewline "."
            }
            Write-Host ""
            if (-not (Test-DockerRunning)) {
                Stop-Script "Docker Desktop did not start. Please start it manually and re-run this script."
            }
        } else {
            Stop-Script "Cannot find Docker Desktop. Please start it manually and re-run this script."
        }
    }

    Write-Info "Docker is running."

    # Detect compose command
    $script:ComposeCmd = Get-ComposeCmd
    if (-not $script:ComposeCmd) {
        Stop-Script "Docker Compose not found. Please ensure Docker Desktop is properly installed."
    }

    Write-Info "Using compose command: $script:ComposeCmd"
}

# ── Port Check ───────────────────────────────────────────────────────────────

function Test-PortAvailable {
    param([int]$Port)
    try {
        $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
        return ($null -eq $connections -or $connections.Count -eq 0)
    } catch {
        # Fallback: try netstat
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

# ── GPU Check ────────────────────────────────────────────────────────────────

function Test-GpuSupport {
    $nvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if (-not $nvidiaSmi) {
        Write-Warn "nvidia-smi not found. GPU is not available."
        return $false
    }

    Write-Info "NVIDIA GPU detected:"
    $gpuInfo = & nvidia-smi --query-gpu name,memory.total --format=csv,noheader 2>$null
    if ($gpuInfo) {
        $gpuInfo | ForEach-Object { Write-Info "  - $_" }
    }

    # Check nvidia-container-toolkit via docker info
    $dockerInfo = docker info 2>&1 | Out-String
    if ($dockerInfo -notmatch "nvidia") {
        Write-Warn "NVIDIA Container Toolkit not detected in Docker."
        Write-Warn "GPU mode may not work. See: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html"
        if (-not (Read-YesNo "Still use GPU mode?" "n")) {
            return $false
        }
    }

    return $true
}

# ── China Mirrors ────────────────────────────────────────────────────────────

function Configure-Mirrors {
    if (-not $ChinaMirrors) {
        if (-not (Read-YesNo "是否配置国内 Docker 镜像加速源？(Configure China Docker mirror?)" "y")) {
            return
        }
    }

    Write-Step "Configuring Docker registry mirrors..."
    Write-Host ""
    Write-Info "Docker Desktop 镜像源配置方法："
    Write-Info "  1. 打开 Docker Desktop → Settings → Docker Engine"
    Write-Info "  2. 在 JSON 配置中添加："
    Write-Host ""
    Write-Host "  {" -ForegroundColor White
    Write-Host "    `"registry-mirrors`": [" -ForegroundColor White
    foreach ($mirror in $ChinaMirrorList) {
        Write-Host "      `"$mirror`"," -ForegroundColor White
    }
    Write-Host "    ]" -ForegroundColor White
    Write-Host "  }" -ForegroundColor White
    Write-Host ""
    Write-Info "  3. 点击 Apply & Restart"
    Write-Host ""

    if (-not (Read-YesNo "配置完成后继续？(Continue after configuration?)" "y")) {
        Stop-Script "请配置镜像源后重新运行脚本。"
    }
}

# ── Configuration Collection ────────────────────────────────────────────────

function Collect-Config {
    Write-Step "Collecting configuration..."

    # Installation directory
    if ([string]::IsNullOrWhiteSpace($script:InstallDir)) {
        $script:InstallDir = Read-Prompt "Installation directory" $DefaultInstallDir
    }
    # Validate install directory: if not exist, ask to create or re-enter
    while ($true) {
        if (Test-Path $script:InstallDir) {
            break
        }
        $installParent = Split-Path $script:InstallDir -Parent
        if (Test-Path $installParent) {
            # Parent exists, we can create it
            if (Read-YesNo "Installation directory does not exist: $($script:InstallDir). Create it?" "y") {
                try {
                    New-Item -ItemType Directory -Path $script:InstallDir -Force | Out-Null
                    Write-Info "Created directory: $($script:InstallDir)"
                    break
                } catch {
                    Write-Err "Failed to create directory: $($script:InstallDir)"
                    if ($Yes) {
                        Stop-Script "Cannot create installation directory. Please check permissions."
                    }
                }
            }
        } else {
            Write-Warn "Parent directory does not exist: $installParent"
        }
        if ($Yes) {
            Stop-Script "Installation directory does not exist and cannot be created: $($script:InstallDir)"
        }
        $script:InstallDir = Read-Prompt "Installation directory" $DefaultInstallDir
    }

    # Photo directory (required)
    if ([string]::IsNullOrWhiteSpace($PhotoDir)) {
        while ($true) {
            $PhotoDir = Read-Prompt "Photo directory path (comma-separated for multiple)" ""
            if ([string]::IsNullOrWhiteSpace($PhotoDir)) {
                Write-Warn "Photo directory is required."
                if ($Yes) {
                    Stop-Script "Photo directory must be specified with -PhotoDir in non-interactive mode."
                }
                continue
            }
            break
        }
    }

    # Validate photo directories: if not exist, ask to create or re-enter
    $validatedDirs = @()
    $photoDirs = $PhotoDir -split "," | ForEach-Object { $_.Trim() }
    foreach ($dir in $photoDirs) {
        $currentDir = $dir
        while ($true) {
            if (Test-Path $currentDir) {
                $validatedDirs += $currentDir
                break
            }
            # Directory doesn't exist — ask what to do
            if ($Yes) {
                Write-Warn "Photo directory does not exist: $currentDir"
                Stop-Script "Photo directory must exist. Please create it or specify a valid path with -PhotoDir."
            }
            Write-Warn "Photo directory does not exist: $currentDir"
            Write-Host "  1) Create this directory"
            Write-Host "  2) Enter a different path"
            Write-Host "  3) Abort"
            $choice = Read-Host "Choose [1/2/3]"
            switch ($choice) {
                "1" {
                    try {
                        New-Item -ItemType Directory -Path $currentDir -Force | Out-Null
                        Write-Info "Created directory: $currentDir"
                        $validatedDirs += $currentDir
                        break
                    } catch {
                        Write-Err "Failed to create directory: $currentDir. Please check permissions."
                        continue
                    }
                }
                "2" {
                    $newDir = Read-Prompt "Photo directory path" ""
                    if (-not [string]::IsNullOrWhiteSpace($newDir)) {
                        $currentDir = $newDir
                        continue  # re-validate
                    }
                }
                default {
                    Stop-Script "Aborted."
                }
            }
        }
    }

    # Rebuild PhotoDir from validated paths
    $script:PhotoDir = $validatedDirs -join ","

    # Port checks
    $portPairs = @(
        @{ Name = "Frontend";  Var = "FrontendPort";  Default = 8082 },
        @{ Name = "Backend API"; Var = "ServerPort";  Default = 8800 },
        @{ Name = "AI service";  Var = "AiPort";      Default = 8801 },
        @{ Name = "PostgreSQL";  Var = "PostgresPort"; Default = 5532 }
    )

    foreach ($pair in $portPairs) {
        $currentVal = Get-Variable $pair.Var -ValueOnly -Scope Script
        if (-not (Test-PortAvailable $currentVal)) {
            $suggested = Get-SuggestedPort $currentVal
            Write-Warn "Port $($currentVal) is in use."
            $newPort = [int](Read-Prompt "  Use port" $suggested)
            Set-Variable $pair.Var $newPort -Scope Script
        }
    }

    # AI mode
    if ($AiMode -eq "gpu") {
        if (-not (Test-GpuSupport)) {
            Write-Warn "Falling back to CPU mode."
            $script:AiMode = "cpu"
        }
    }
}

# ── File Generation ─────────────────────────────────────────────────────────

function Generate-EnvFile {
    Write-Step "Generating .env file..."

    $envContent = @"
# TrailSnap Configuration — generated by install.ps1 v$ScriptVersion
# https://github.com/LC044/TrailSnap

# Photo directory (comma-separated for multiple mounts)
PHOTO_DIR=$PhotoDir

# Ports
FRONTEND_PORT=$FrontendPort
SERVER_PORT=$ServerPort
AI_PORT=$AiPort
POSTGRES_PORT=$PostgresPort

# Timezone
TZ=$Timezone

# Docker image tag (latest or master)
IMAGE_TAG=$Tag

# AI mode: cpu or gpu
AI_MODE=$AiMode

# Database
POSTGRES_DB=$DefaultPgDb
POSTGRES_USER=$DefaultPgUser
POSTGRES_PASSWORD=$DefaultPgPassword
"@

    $envPath = Join-Path $script:InstallDir ".env"
    Set-Content -Path $envPath -Value $envContent -Encoding UTF8 -NoNewline
    Write-Info "Created $envPath"
}

function Generate-ComposeFile {
    Write-Step "Generating docker-compose.yml..."

    # Build photo volume mounts
    $photoDirs = $PhotoDir -split "," | ForEach-Object { $_.Trim() }
    $photoVolumes = @()
    $mountIndex = 1
    foreach ($dir in $photoDirs) {
        if ($photoDirs.Count -eq 1) {
            $photoVolumes += "      - ${dir}:/app/Photos/:ro"
        } else {
            $photoVolumes += "      - ${dir}:/app/Photos${mountIndex}/:ro"
        }
        $mountIndex++
    }
    $photoVolumeStr = $photoVolumes -join "`n"

    # GPU block
    $gpuBlock = ""
    $aiImageTag = '${IMAGE_TAG}'
    if ($AiMode -eq "gpu") {
        $aiImageTag = '${IMAGE_TAG}-gpu'
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
    ports:
      - "`${POSTGRES_PORT}:5432"
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
        restart: true

  ai:
    image: siyuan044/trailsnap-ai:$aiImageTag
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
    Write-Info "Created $composePath"
}

# ── Health Check ─────────────────────────────────────────────────────────────

function Wait-ForService {
    param(
        [string]$Name,
        [scriptblock]$TestBlock,
        [int]$TimeoutSeconds = 60
    )

    $interval = 5
    $elapsed = 0
    Write-Host -NoNewline "  Waiting for ${Name}..."

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

    Write-Host " FAILED" -ForegroundColor Red
    return $false
}

function Test-HealthCheck {
    Write-Step "Running health checks..."

    # Load env for ports
    $envFilePath = Join-Path $script:InstallDir ".env"
    if (Test-Path $envFilePath) {
        Get-Content $envFilePath | ForEach-Object {
            if ($_ -match "^([^#][^=]+)=(.*)$") {
                Set-Item -Path "env:$($Matches[1])" -Value $Matches[2]
            }
        }
    }

    $failed = $false

    # Postgres — check container health
    $pgOk = Wait-ForService "postgres" {
        $status = docker inspect --format='{{.State.Health.Status}}' trailsnap-postgres 2>$null
        $status -match "healthy"
    } -TimeoutSeconds 60
    if (-not $pgOk) { $failed = $true }

    # AI service
    $aiOk = Wait-ForService "ai" {
        try {
            $resp = Invoke-WebRequest -Uri "http://localhost:${AiPort}/health-check" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            $resp.StatusCode -eq 200
        } catch { $false }
    } -TimeoutSeconds 90
    if (-not $aiOk) { $failed = $true }

    # Server
    $srvOk = Wait-ForService "server" {
        try {
            $resp = Invoke-WebRequest -Uri "http://localhost:${ServerPort}/docs" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            $resp.StatusCode -eq 200
        } catch { $false }
    } -TimeoutSeconds 90
    if (-not $srvOk) { $failed = $true }

    # Frontend
    $feOk = Wait-ForService "frontend" {
        try {
            $resp = Invoke-WebRequest -Uri "http://localhost:${FrontendPort}" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            $resp.StatusCode -eq 200
        } catch { $false }
    } -TimeoutSeconds 60
    if (-not $feOk) { $failed = $true }

    if ($failed) {
        Write-Host ""
        Write-Err "Some services failed health checks."
        Write-Info "Checking logs..."
        Push-Location $script:InstallDir
        Invoke-Compose "--env-file .env logs --tail=50"
        Pop-Location
        Write-Host ""
        Write-Warn "You can check logs manually: cd ${script:InstallDir}; $($script:ComposeCmd) --env-file .env logs -f"
        return $false
    }

    return $true
}

# ── Pull & Start ─────────────────────────────────────────────────────────────

function Invoke-Compose {
    param([string]$Arguments)
    # docker compose is a two-word command; & "docker compose" fails in PowerShell
    # because it treats the whole string as one executable name.
    # Split into command + args, then use & with the executable and pass args separately.
    $parts = $script:ComposeCmd -split ' ', 2
    $exe = $parts[0]
    $subArgs = if ($parts.Count -gt 1) { "$($parts[1]) $Arguments" } else { $Arguments }
    & $exe $subArgs.Split(' ')
}

function Pull-Images {
    Write-Step "Pulling Docker images..."
    Push-Location $script:InstallDir
    try {
        Invoke-Compose "--env-file .env pull"
        if ($LASTEXITCODE -ne 0) {
            Write-Err "Failed to pull images."
            if (-not $ChinaMirrors) {
                Write-Warn "If you are in China, try re-running with -ChinaMirrors flag."
            }
            Stop-Script "Image pull failed. Please check your network and Docker configuration."
        }
    } finally {
        Pop-Location
    }
}

function Start-Services {
    Write-Step "Starting services..."
    Push-Location $script:InstallDir
    try {
        Invoke-Compose "--env-file .env up -d"
    } finally {
        Pop-Location
    }
    Write-Info "Services started."
}

# ── Success Banner ───────────────────────────────────────────────────────────

function Write-Success {
    Write-Host ""
    Write-Host "  =======================================================" -ForegroundColor Green
    Write-Host "" -ForegroundColor Green
    Write-Host "        TrailSnap (行影集) is now running!" -ForegroundColor Green
    Write-Host "" -ForegroundColor Green
    Write-Host "  =======================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Frontend:     http://localhost:${FrontendPort}" -ForegroundColor White
    Write-Host "  Backend API:  http://localhost:${ServerPort}/docs" -ForegroundColor White
    Write-Host "  AI Service:   http://localhost:${AiPort}/docs" -ForegroundColor White
    Write-Host ""
    Write-Host "  Next steps:" -ForegroundColor Cyan
    Write-Host "  1. Open the frontend URL in your browser"
    Write-Host "  2. Go to More -> Settings -> External Library"
    Write-Host "  3. Add /app/Photos/ to scan your photos"
    Write-Host ""
    Write-Host "  Management commands (run in $($script:InstallDir)):" -ForegroundColor Cyan
    Write-Host "    Stop:      $($script:ComposeCmd) --env-file .env down"
    Write-Host "    Restart:   $($script:ComposeCmd) --env-file .env restart"
    Write-Host "    Logs:      $($script:ComposeCmd) --env-file .env logs -f"
    Write-Host "    Upgrade:   .\install.ps1 -Upgrade"
    Write-Host ""
}

# ── Upgrade ──────────────────────────────────────────────────────────────────

function Do-Upgrade {
    Write-Step "Upgrading TrailSnap..."

    $envFilePath = Join-Path $script:InstallDir ".env"
    if (-not (Test-Path $envFilePath)) {
        Stop-Script "No existing installation found at $($script:InstallDir). Run without -Upgrade to install."
    }

    # Load existing config
    Get-Content $envFilePath | ForEach-Object {
        if ($_ -match "^([^#][^=]+)=(.*)$") {
            $key = $Matches[1].Trim()
            $value = $Matches[2].Trim()
            Set-Item -Path "env:$key" -Value $value
            # Sync script variables
            switch ($key) {
                "FRONTEND_PORT" { $script:FrontendPort = [int]$value }
                "SERVER_PORT"   { $script:ServerPort = [int]$value }
                "AI_PORT"       { $script:AiPort = [int]$value }
                "POSTGRES_PORT" { $script:PostgresPort = [int]$value }
                "TZ"            { $script:Timezone = $value }
                "IMAGE_TAG"     { $script:Tag = $value }
                "AI_MODE"       { $script:AiMode = $value }
                "PHOTO_DIR"     { $script:PhotoDir = $value }
            }
        }
    }

    # Regenerate compose (template may have changed)
    Generate-ComposeFile

    # Pull new images
    Pull-Images

    # Recreate containers
    Push-Location $script:InstallDir
    try {
        Invoke-Compose "--env-file .env up -d --remove-orphans"
    } finally {
        Pop-Location
    }

    # Health check
    Test-HealthCheck | Out-Null

    Write-Success
    Write-Info "Upgrade complete. Your .env configuration was preserved."
}

# ── Uninstall ────────────────────────────────────────────────────────────────

function Do-Uninstall {
    Write-Step "Uninstalling TrailSnap..."

    $composePath = Join-Path $script:InstallDir "docker-compose.yml"
    if (-not (Test-Path $composePath)) {
        Stop-Script "No installation found at $($script:InstallDir)."
    }

    Push-Location $script:InstallDir
    try {
        Invoke-Compose "--env-file .env down" 2>$null
    } finally {
        Pop-Location
    }
    Write-Info "Containers stopped and removed."

    if ($Purge) {
        if (Read-YesNo "This will DELETE all data (database, models, uploads). Are you sure?" "n") {
            Remove-Item -Path (Join-Path $script:InstallDir "pg_data") -Recurse -Force -ErrorAction SilentlyContinue
            Remove-Item -Path (Join-Path $script:InstallDir "data") -Recurse -Force -ErrorAction SilentlyContinue
            Remove-Item -Path (Join-Path $script:InstallDir ".env") -Force -ErrorAction SilentlyContinue
            Remove-Item -Path (Join-Path $script:InstallDir "docker-compose.yml") -Force -ErrorAction SilentlyContinue
            Write-Info "All data deleted."
        }
    } else {
        Write-Info "Data directories preserved at $($script:InstallDir)/"
        Write-Info "To delete data too, run: .\install.ps1 -Uninstall -Purge"
    }

    Write-Info "Uninstall complete."
}

# ── Usage ────────────────────────────────────────────────────────────────────

function Write-Usage {
    Write-Host @"
TrailSnap (行影集) — One-Click Installation Script for Windows

Usage:
  .\install.ps1 [OPTIONS]

Options:
  -PhotoDir <path>       Photo directory (comma-separated for multiple)
  -InstallDir <path>     Installation directory (default: ~/trailsnap)
  -FrontendPort <int>    Frontend port (default: 8082)
  -ServerPort <int>      Backend API port (default: 8800)
  -AiPort <int>          AI service port (default: 8801)
  -PostgresPort <int>    PostgreSQL port (default: 5532)
  -Timezone <tz>         Timezone (default: Asia/Shanghai)
  -AiMode <cpu|gpu>      AI mode (default: cpu)
  -Tag <latest|master>   Docker image tag (default: latest)
  -ChinaMirrors          Configure China Docker registry mirrors
  -Yes                   Non-interactive: accept all defaults
  -Upgrade               Upgrade existing installation
  -Uninstall             Uninstall TrailSnap
  -Purge                 Delete all data (use with -Uninstall)
  -Help                  Show this help message

Examples:
  # Interactive install
  .\install.ps1

  # Non-interactive install with all options
  .\install.ps1 -PhotoDir "D:\Photos" -ChinaMirrors -Yes

  # GPU mode
  .\install.ps1 -PhotoDir "D:\Photos" -AiMode gpu

  # Upgrade
  .\install.ps1 -Upgrade

  # Uninstall (keep data)
  .\install.ps1 -Uninstall

  # Uninstall (delete everything)
  .\install.ps1 -Uninstall -Purge
"@
}

# ── Main ─────────────────────────────────────────────────────────────────────

if ($Help) {
    Write-Usage
    exit 0
}

Write-Banner

# Handle uninstall first
if ($Uninstall) {
    if ([string]::IsNullOrWhiteSpace($script:InstallDir)) {
        $script:InstallDir = Read-Prompt "Installation directory" $DefaultInstallDir
    }
    Do-Uninstall
    exit 0
}

# Set default install dir
if ([string]::IsNullOrWhiteSpace($script:InstallDir)) {
    $script:InstallDir = $DefaultInstallDir
}

# Ensure Docker is available
Ensure-Docker

# Handle upgrade
if ($Upgrade) {
    Do-Upgrade
    exit 0
}

# Configure mirrors (for China)
Configure-Mirrors

# Check for existing installation
$existingCompose = Join-Path $script:InstallDir "docker-compose.yml"
if (Test-Path $existingCompose) {
    Write-Warn "Existing installation found at $($script:InstallDir)."
    if (Read-YesNo "Do you want to upgrade the existing installation?" "y") {
        Do-Upgrade
        exit 0
    } else {
        if (-not (Read-YesNo "Reconfigure and reinstall? (Data will be preserved)" "n")) {
            Stop-Script "Aborted."
        }
    }
}

# Collect configuration
Collect-Config

# Create install directory
New-Item -ItemType Directory -Path $script:InstallDir -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $script:InstallDir "pg_data") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $script:InstallDir "data") -Force | Out-Null

# Generate configuration files
Generate-EnvFile
Generate-ComposeFile

# Pull and start
Pull-Images
Start-Services

# Health check
if (Test-HealthCheck) {
    Write-Success
} else {
    Write-Host ""
    Write-Warn "Some services may need more time to start."
    Write-Info "You can check status with: cd $($script:InstallDir); $($script:ComposeCmd) --env-file .env ps"
    Write-Info "Or view logs with: cd $($script:InstallDir); $($script:ComposeCmd) --env-file .env logs -f"
    Write-Host ""
    Write-Host "  Frontend:     http://localhost:${FrontendPort}" -ForegroundColor White
    Write-Host "  Backend API:  http://localhost:${ServerPort}/docs" -ForegroundColor White
}
