#!/usr/bin/env bash
# =============================================================================
# TrailSnap (行影集) — One-Click Installation Script
# https://github.com/LC044/TrailSnap
#
# Usage:
#   Interactive:      ./install.sh
#   Non-interactive:  ./install.sh --photo-dir /path/to/photos --china-mirrors --yes
#   One-liner:        curl -fsSL https://trailsnap.cn/install.sh | bash
#   Upgrade:          ./install.sh --upgrade
#   Uninstall:        ./install.sh --uninstall [--purge]
# =============================================================================

set -euo pipefail

# ── Constants ────────────────────────────────────────────────────────────────
SCRIPT_VERSION="1.0.0"
DEFAULT_FRONTEND_PORT=8082
DEFAULT_SERVER_PORT=8800
DEFAULT_AI_PORT=8801
DEFAULT_POSTGRES_PORT=5532
DEFAULT_TZ="Asia/Shanghai"
DEFAULT_IMAGE_TAG="latest"
DEFAULT_AI_MODE="cpu"
DEFAULT_INSTALL_DIR="$HOME/trailsnap"
DEFAULT_PG_DB="trailsnap"
DEFAULT_PG_USER="trailsnap"
DEFAULT_PG_PASSWORD="trailsnap"

CHINA_MIRRORS=(
  "https://docker.1ms.run"
  "https://docker.xuanyuan.me"
  "https://dockerproxy.net"
)

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ── Globals ──────────────────────────────────────────────────────────────────
OS=""
ARCH=""
COMPOSE_CMD=""
INSTALL_DIR=""
PHOTO_DIR=""
FRONTEND_PORT=""
SERVER_PORT=""
AI_PORT=""
POSTGRES_PORT=""
TZ=""
IMAGE_TAG=""
AI_MODE=""
CHINA_MIRRORS_FLAG=false
YES_FLAG=false
UPGRADE_FLAG=false
UNINSTALL_FLAG=false
PURGE_FLAG=false

# ── Utility Functions ────────────────────────────────────────────────────────

print_banner() {
  echo -e "${CYAN}"
  echo "  ╔═══════════════════════════════════════════════╗"
  echo "  ║                                               ║"
  echo "  ║       TrailSnap  行影集  — 一键安装           ║"
  echo "  ║       AI-Powered Self-Hosted Photo Album      ║"
  echo "  ║                                               ║"
  echo "  ╚═══════════════════════════════════════════════╝"
  echo -e "${NC}"
}

info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }
step()    { echo -e "${BLUE}==>${NC} ${BOLD}$*${NC}"; }

die() {
  error "$@"
  exit 1
}

prompt_default() {
  local prompt_text="$1"
  local default_val="$2"
  if [[ "$YES_FLAG" == true ]]; then
    echo "$default_val"
    return
  fi
  printf "\033[0;36m%s\033[0m [%s]: " "$prompt_text" "$default_val"
  read -r answer
  echo "${answer:-$default_val}"
}

prompt_yes_no() {
  local prompt_text="$1"
  local default_val="${2:-n}"
  if [[ "$YES_FLAG" == true ]]; then
    [[ "$default_val" == "y" ]] && echo "y" || echo "n"
    return
  fi
  local indicator="y/N"
  [[ "$default_val" == "y" ]] && indicator="Y/n"
  printf "\033[0;36m%s\033[0m [%s]: " "$prompt_text" "$indicator"
  read -r answer
  answer="${answer:-$default_val}"
  [[ "${answer,,}" == "y" || "${answer,,}" == "yes" ]] && echo "y" || echo "n"
}

# ── OS Detection ─────────────────────────────────────────────────────────────

detect_os() {
  step "Detecting operating system..."
  local uname_s
  uname_s="$(uname -s)"

  if [[ "$uname_s" == "Darwin" ]]; then
    OS="macos"
  elif [[ "$uname_s" == "Linux" ]]; then
    if grep -qi "microsoft\|wsl" /proc/version 2>/dev/null; then
      OS="wsl2"
    else
      OS="linux"
    fi
  else
    die "Unsupported OS: $uname_s. This script supports Linux, macOS, and WSL2."
  fi

  ARCH="$(uname -m)"
  [[ "$ARCH" == "x86_64" ]] && ARCH="amd64"
  [[ "$ARCH" == "aarch64" ]] && ARCH="arm64"

  info "Detected: OS=${OS}, Arch=${ARCH}"
}

# ── Docker Detection & Installation ─────────────────────────────────────────

detect_docker() {
  if command -v docker &>/dev/null; then
    return 0
  fi
  return 1
}

detect_compose_cmd() {
  # Docker Compose V2 plugin
  if docker compose version &>/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
    return 0
  fi
  # Docker Compose V1 standalone
  if command -v docker-compose &>/dev/null; then
    COMPOSE_CMD="docker-compose"
    return 0
  fi
  return 1
}

install_docker_linux() {
  step "Installing Docker on Linux..."

  if [[ "$(id -u)" -ne 0 ]]; then
    warn "Docker installation requires sudo."
  fi

  # Detect distro family
  if [[ -f /etc/debian_version ]] || grep -qi "debian\|ubuntu" /etc/os-release 2>/dev/null; then
    install_docker_debian
  elif [[ -f /etc/redhat-release ]] || grep -qi "rhel\|centos\|fedora" /etc/os-release 2>/dev/null; then
    install_docker_rhel
  elif command -v apt-get &>/dev/null; then
    install_docker_debian
  else
    die "Cannot auto-install Docker on this distro. Please install Docker manually: https://docs.docker.com/get-docker/"
  fi
}

install_docker_debian() {
  step "Installing Docker via apt (Debian/Ubuntu)..."
  sudo apt-get update -qq
  sudo apt-get install -y -qq ca-certificates curl gnupg

  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
    sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null
  sudo chmod a+r /etc/apt/keyrings/docker.gpg

  local codename
  codename="$(. /etc/os-release && echo "$VERSION_CODENAME")"
  local arch
  arch="$(dpkg --print-architecture)"

  echo "deb [arch=${arch} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${codename} stable" | \
    sudo tee /etc/apt/sources.list.d/docker.list >/dev/null

  sudo apt-get update -qq
  sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin

  sudo systemctl enable --now docker
  info "Docker installed successfully."
}

install_docker_rhel() {
  step "Installing Docker via dnf/yum (RHEL/CentOS/Fedora)..."
  sudo dnf install -y dnf-utils || sudo yum install -y yum-utils
  sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo || \
    sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo

  sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin || \
    sudo yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

  sudo systemctl enable --now docker
  info "Docker installed successfully."
}

install_docker_macos() {
  step "Installing Docker on macOS..."
  if command -v brew &>/dev/null; then
    brew install --cask docker
    info "Docker Desktop installed via Homebrew. Please start it from Applications."
  else
    die "Homebrew not found. Please install Docker Desktop manually: https://docs.docker.com/desktop/install/mac-install/"
  fi
}

install_docker_wsl2() {
  step "Setting up Docker for WSL2..."
  if command -v docker.exe &>/dev/null || command -v docker &>/dev/null; then
    info "Docker detected. If it's Docker Desktop, make sure it's running."
    return
  fi
  die "Docker not found in WSL2. Please install Docker Desktop for Windows: https://docs.docker.com/desktop/install/windows-install/"
}

ensure_docker() {
  step "Checking Docker..."

  if ! detect_docker; then
    warn "Docker is not installed."
    local answer
    answer="$(prompt_yes_no "Do you want to install Docker automatically?" "y")"
    if [[ "$answer" == "y" ]]; then
      case "$OS" in
        linux)  install_docker_linux ;;
        macos)  install_docker_macos ;;
        wsl2)   install_docker_wsl2 ;;
        *)      die "Cannot auto-install Docker on $OS" ;;
      esac
    else
      die "Docker is required. Please install it manually: https://docs.docker.com/get-docker/"
    fi
  fi

  # Add user to docker group on Linux
  if [[ "$OS" == "linux" ]] && [[ "$(id -u)" -ne 0 ]] && ! groups "$(whoami)" | grep -q docker; then
    info "Adding current user to docker group..."
    sudo usermod -aG docker "$(whoami)" 2>/dev/null || true
    warn "You may need to log out and log back in for the docker group to take effect."
    warn "Or run: newgrp docker"
  fi

  # Check Docker daemon is running
  if ! docker info &>/dev/null; then
    warn "Docker daemon is not running."
    if [[ "$OS" == "linux" ]]; then
      info "Starting Docker daemon..."
      sudo systemctl start docker || die "Failed to start Docker. Please start it manually."
    elif [[ "$OS" == "macos" || "$OS" == "wsl2" ]]; then
      info "Waiting for Docker Desktop to start..."
      local retries=0
      while ! docker info &>/dev/null && [[ $retries -lt 30 ]]; do
        sleep 2
        retries=$((retries + 1))
        echo -n "."
      done
      echo ""
      if ! docker info &>/dev/null; then
        die "Docker Desktop is not responding. Please start it and re-run this script."
      fi
    fi
  fi

  info "Docker is running."

  # Detect compose command
  if ! detect_compose_cmd; then
    if [[ "$OS" == "linux" ]]; then
      warn "Docker Compose not found. Installing docker-compose-plugin..."
      sudo apt-get install -y -qq docker-compose-plugin 2>/dev/null || \
        sudo dnf install -y -q docker-compose-plugin 2>/dev/null || \
        die "Failed to install Docker Compose. Please install it manually."
      COMPOSE_CMD="docker compose"
    else
      die "Docker Compose not found. Please install it: https://docs.docker.com/compose/install/"
    fi
  fi

  info "Using compose command: ${COMPOSE_CMD}"
}

# ── China Mirrors ────────────────────────────────────────────────────────────

test_mirror() {
  local mirror="$1"
  curl -sfSL --connect-timeout 5 "${mirror}/v2/" &>/dev/null
}

configure_mirrors_linux() {
  step "Configuring Docker registry mirrors for China..."

  local available_mirrors=()
  for mirror in "${CHINA_MIRRORS[@]}"; do
    info "Testing mirror: ${mirror}..."
    if test_mirror "$mirror"; then
      available_mirrors+=("\"$mirror\"")
      info "  ✓ Available"
    else
      warn "  ✗ Unreachable"
    fi
  done

  if [[ ${#available_mirrors[@]} -eq 0 ]]; then
    warn "No mirrors are reachable. Skipping mirror configuration."
    return
  fi

  local mirrors_json
  mirrors_json=$(IFS=,; echo "${available_mirrors[*]}")

  local daemon_json="/etc/docker/daemon.json"
  if [[ -f "$daemon_json" ]]; then
    # Merge with existing config using python
    if command -v python3 &>/dev/null; then
      python3 -c "
import json, sys
with open('$daemon_json') as f:
    cfg = json.load(f)
cfg['registry-mirrors'] = [${mirrors_json}]
with open('$daemon_json', 'w') as f:
    json.dump(cfg, f, indent=2)
"
    else
      # Fallback: overwrite
      echo "{\"registry-mirrors\": [${mirrors_json}]}" | sudo tee "$daemon_json" >/dev/null
    fi
  else
    echo "{\"registry-mirrors\": [${mirrors_json}]}" | sudo tee "$daemon_json" >/dev/null
  fi

  sudo systemctl restart docker
  info "Docker mirrors configured and Docker restarted."
}

configure_mirrors() {
  if [[ "$CHINA_MIRRORS_FLAG" != true ]]; then
    local answer
    answer="$(prompt_yes_no "是否配置国内 Docker 镜像加速源？(Configure China Docker mirror?)" "y")"
    [[ "$answer" != "y" ]] && return
  fi

  case "$OS" in
    linux)
      configure_mirrors_linux
      ;;
    macos|wsl2)
      echo ""
      info "Docker Desktop 镜像源配置方法："
      info "  1. 打开 Docker Desktop → Settings → Docker Engine"
      info "  2. 在 JSON 配置中添加："
      echo ""
      echo '  {'
      echo '    "registry-mirrors": ['
      for mirror in "${CHINA_MIRRORS[@]}"; do
        echo "      \"${mirror}\","
      done
      echo '    ]'
      echo '  }'
      echo ""
      info "  3. 点击 Apply & Restart"
      echo ""
      local cont
      cont="$(prompt_yes_no "配置完成后继续？(Continue after configuration?)" "y")"
      [[ "$cont" != "y" ]] && die "请配置镜像源后重新运行脚本。"
      ;;
  esac
}

# ── Port Check ───────────────────────────────────────────────────────────────

check_port_available() {
  local port="$1"
  if ss -tlnp 2>/dev/null | grep -q ":${port} "; then
    return 1
  fi
  if lsof -i ":${port}" &>/dev/null 2>&1; then
    return 1
  fi
  if netstat -tlnp 2>/dev/null | grep -q ":${port} "; then
    return 1
  fi
  return 0
}

suggest_port() {
  local base_port="$1"
  local offset=1
  while [[ $offset -lt 100 ]]; do
    local candidate=$((base_port + offset))
    if check_port_available "$candidate"; then
      echo "$candidate"
      return
    fi
    offset=$((offset + 1))
  done
  echo "$((base_port + 1))"
}

# ── GPU Check ────────────────────────────────────────────────────────────────

check_gpu_support() {
  if ! command -v nvidia-smi &>/dev/null; then
    warn "nvidia-smi not found. GPU is not available."
    return 1
  fi

  info "NVIDIA GPU detected:"
  nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | while read -r line; do
    info "  - $line"
  done

  # Check nvidia-container-toolkit
  if ! docker info 2>/dev/null | grep -q "nvidia"; then
    warn "NVIDIA Container Toolkit not detected."
    warn "GPU mode may not work. Install: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html"
    local answer
    answer="$(prompt_yes_no "Still use GPU mode?" "n")"
    [[ "$answer" != "y" ]] && return 1
  fi

  return 0
}

# ── Configuration Collection ────────────────────────────────────────────────

collect_config() {
  step "Collecting configuration..."

  # Installation directory
  INSTALL_DIR="$(prompt_default "Installation directory" "$DEFAULT_INSTALL_DIR")"

  # Photo directory (required, no safe default)
  if [[ -z "$PHOTO_DIR" ]]; then
    while true; do
      PHOTO_DIR="$(prompt_default "Photo directory path (comma-separated for multiple)" "")"
      if [[ -z "$PHOTO_DIR" ]]; then
        warn "Photo directory is required."
        if [[ "$YES_FLAG" == true ]]; then
          die "Photo directory must be specified with --photo-dir in non-interactive mode."
        fi
        continue
      fi
      break
    done
  fi

  # Validate photo directories exist
  IFS=',' read -ra PHOTO_DIRS <<< "$PHOTO_DIR"
  for dir in "${PHOTO_DIRS[@]}"; do
    dir="$(echo "$dir" | xargs)"  # trim whitespace
    if [[ ! -d "$dir" ]]; then
      if [[ "$YES_FLAG" == true ]]; then
        warn "Photo directory does not exist: $dir (will be created or may cause issues)"
      else
        local answer
        answer="$(prompt_yes_no "Directory does not exist: ${dir}. Continue anyway?" "n")"
        [[ "$answer" != "y" ]] && die "Please provide a valid photo directory."
      fi
    fi
  done

  # Ports
  FRONTEND_PORT="$(prompt_default "Frontend port" "$DEFAULT_FRONTEND_PORT")"
  SERVER_PORT="$(prompt_default "Backend API port" "$DEFAULT_SERVER_PORT")"
  AI_PORT="$(prompt_default "AI service port" "$DEFAULT_AI_PORT")"
  POSTGRES_PORT="$(prompt_default "PostgreSQL port" "$DEFAULT_POSTGRES_PORT")"

  # Check ports
  for port_var in FRONTEND_PORT SERVER_PORT AI_PORT POSTGRES_PORT; do
    local port="${!port_var}"
    if ! check_port_available "$port"; then
      local suggested
      suggested="$(suggest_port "$port")"
      warn "Port ${port} is in use."
      local new_port
      new_port="$(prompt_default "  Use port" "$suggested")"
      eval "${port_var}=\"${new_port}\""
    fi
  done

  # Timezone
  TZ="$(prompt_default "Timezone" "$DEFAULT_TZ")"

  # AI mode
  if [[ -z "$AI_MODE" ]]; then
    AI_MODE="$(prompt_default "AI mode (cpu/gpu)" "$DEFAULT_AI_MODE")"
  fi
  if [[ "$AI_MODE" == "gpu" ]]; then
    if ! check_gpu_support; then
      warn "Falling back to CPU mode."
      AI_MODE="cpu"
    fi
  fi

  # Image tag
  IMAGE_TAG="$(prompt_default "Image tag (latest/master)" "$DEFAULT_IMAGE_TAG")"
}

# ── File Generation ─────────────────────────────────────────────────────────

generate_env() {
  step "Generating .env file..."
  cat > "${INSTALL_DIR}/.env" << EOF
# TrailSnap Configuration — generated by install.sh v${SCRIPT_VERSION}
# https://github.com/LC044/TrailSnap

# Photo directory (comma-separated for multiple mounts)
PHOTO_DIR=${PHOTO_DIR}

# Ports
FRONTEND_PORT=${FRONTEND_PORT}
SERVER_PORT=${SERVER_PORT}
AI_PORT=${AI_PORT}
POSTGRES_PORT=${POSTGRES_PORT}

# Timezone
TZ=${TZ}

# Docker image tag (latest or master)
IMAGE_TAG=${IMAGE_TAG}

# AI mode: cpu or gpu
AI_MODE=${AI_MODE}

# Database
POSTGRES_DB=${DEFAULT_PG_DB}
POSTGRES_USER=${DEFAULT_PG_USER}
POSTGRES_PASSWORD=${DEFAULT_PG_PASSWORD}
EOF

  chmod 600 "${INSTALL_DIR}/.env"
  info "Created ${INSTALL_DIR}/.env"
}

generate_compose() {
  step "Generating docker-compose.yml..."

  # Build photo volume mounts
  local photo_volumes=""
  local mount_index=1
  IFS=',' read -ra PHOTO_DIRS <<< "$PHOTO_DIR"
  for dir in "${PHOTO_DIRS[@]}"; do
    dir="$(echo "$dir" | xargs)"
    if [[ ${#PHOTO_DIRS[@]} -eq 1 ]]; then
      photo_volumes+="      - ${dir}:/app/Photos/:ro"
    else
      photo_volumes+="      - ${dir}:/app/Photos${mount_index}/:ro"
    fi
    mount_index=$((mount_index + 1))
  done

  # GPU block
  local gpu_block=""
  local ai_image_tag='${IMAGE_TAG}'
  if [[ "$AI_MODE" == "gpu" ]]; then
    ai_image_tag='${IMAGE_TAG}-gpu'
    gpu_block="
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]"
  fi

  cat > "${INSTALL_DIR}/docker-compose.yml" << COMPOSE_EOF
services:
  postgres:
    image: pgvector/pgvector:pg18-trixie
    container_name: trailsnap-postgres
    restart: always
    environment:
      TZ: \${TZ}
      POSTGRES_DB: \${POSTGRES_DB}
      POSTGRES_USER: \${POSTGRES_USER}
      POSTGRES_PASSWORD: \${POSTGRES_PASSWORD}
      POSTGRES_INITDB_ARGS: "--encoding=UTF8 --lc-collate=C --lc-ctype=C"
      PGDATA: /var/lib/postgresql/data/pgdata
    networks: [app-network]
    ports:
      - "\${POSTGRES_PORT}:5432"
    volumes:
      - ./pg_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U \${POSTGRES_USER} -d \${POSTGRES_DB} -p 5432"]
      interval: 5s
      timeout: 5s
      retries: 5
      start_period: 10s

  server:
    image: siyuan044/trailsnap-server:\${IMAGE_TAG}
    container_name: trailsnap-server
    restart: always
    expose: ["8000"]
    ports:
      - "\${SERVER_PORT}:8000"
    networks: [app-network]
    volumes:
      - ./data:/app/data
${photo_volumes}
    environment:
      - TZ=\${TZ}
      - DB_URL=postgresql://\${POSTGRES_USER}:\${POSTGRES_PASSWORD}@postgres:5432/\${POSTGRES_DB}
      - RAILWAY_DB_URL=postgresql://\${POSTGRES_USER}:\${POSTGRES_PASSWORD}@postgres:5432/railway
      - AI_API_URL=http://ai:8001
    depends_on:
      postgres:
        condition: service_healthy
        restart: true

  ai:
    image: siyuan044/trailsnap-ai:${ai_image_tag}
    container_name: trailsnap-ai
    restart: always
    expose: ["8001"]
    ports:
      - "\${AI_PORT}:8001"
    networks: [app-network]
    volumes:
      - ./data:/app/data
    environment:
      - TZ=\${TZ}${gpu_block}

  frontend:
    image: siyuan044/trailsnap-frontend:\${IMAGE_TAG}
    container_name: trailsnap-frontend
    restart: always
    ports:
      - "\${FRONTEND_PORT}:80"
    depends_on: [server]
    networks: [app-network]
    environment:
      - TZ=\${TZ}

networks:
  app-network:
    driver: bridge
COMPOSE_EOF

  info "Created ${INSTALL_DIR}/docker-compose.yml"
}

# ── Health Check ─────────────────────────────────────────────────────────────

wait_for_service() {
  local name="$1"
  local test_cmd="$2"
  local timeout="${3:-60}"
  local interval=5
  local elapsed=0

  echo -n "  Waiting for ${name}..."
  while [[ $elapsed -lt $timeout ]]; do
    if eval "$test_cmd" &>/dev/null; then
      echo " ✓"
      return 0
    fi
    sleep "$interval"
    elapsed=$((elapsed + interval))
    echo -n "."
  done
  echo " ✗"
  return 1
}

health_check() {
  step "Running health checks..."

  # Load env for ports
  source "${INSTALL_DIR}/.env" 2>/dev/null || true

  local failed=false

  # Postgres — check container health
  wait_for_service "postgres" \
    "docker inspect --format='{{.State.Health.Status}}' trailsnap-postgres 2>/dev/null | grep -q healthy" \
    60 || failed=true

  # AI service — check /health-check endpoint
  wait_for_service "ai" \
    "curl -sf http://localhost:${AI_PORT}/health-check" \
    90 || failed=true

  # Server — check /docs endpoint
  wait_for_service "server" \
    "curl -sf http://localhost:${SERVER_PORT}/docs -o /dev/null" \
    90 || failed=true

  # Frontend — check root endpoint
  wait_for_service "frontend" \
    "curl -sf http://localhost:${FRONTEND_PORT} -o /dev/null" \
    60 || failed=true

  if [[ "$failed" == true ]]; then
    echo ""
    error "Some services failed health checks."
    info "Checking logs..."
    cd "$INSTALL_DIR"
    $COMPOSE_CMD --env-file .env logs --tail=50
    echo ""
    warn "You can check logs manually: cd ${INSTALL_DIR} && ${COMPOSE_CMD} --env-file .env logs -f"
    return 1
  fi

  return 0
}

# ── Pull & Start ─────────────────────────────────────────────────────────────

pull_images() {
  step "Pulling Docker images..."
  cd "$INSTALL_DIR"
  if ! $COMPOSE_CMD --env-file .env pull; then
    error "Failed to pull images."
    if [[ "$CHINA_MIRRORS_FLAG" != true ]]; then
      warn "If you are in China, try re-running with --china-mirrors flag."
    fi
    die "Image pull failed. Please check your network and Docker configuration."
  fi
}

start_services() {
  step "Starting services..."
  cd "$INSTALL_DIR"
  $COMPOSE_CMD --env-file .env up -d
  info "Services started."
}

# ── Success Banner ───────────────────────────────────────────────────────────

print_success() {
  source "${INSTALL_DIR}/.env" 2>/dev/null || true

  echo ""
  echo -e "${GREEN}╔═══════════════════════════════════════════════════════╗${NC}"
  echo -e "${GREEN}║                                                       ║${NC}"
  echo -e "${GREEN}║       🎉  TrailSnap (行影集) is now running!  🎉      ║${NC}"
  echo -e "${GREEN}║                                                       ║${NC}"
  echo -e "${GREEN}╚═══════════════════════════════════════════════════════╝${NC}"
  echo ""
  echo -e "  ${BOLD}Frontend:${NC}     http://localhost:${FRONTEND_PORT}"
  echo -e "  ${BOLD}Backend API:${NC}  http://localhost:${SERVER_PORT}/docs"
  echo -e "  ${BOLD}AI Service:${NC}   http://localhost:${AI_PORT}/docs"
  echo ""
  echo -e "  ${CYAN}Next steps:${NC}"
  echo "  1. Open the frontend URL in your browser"
  echo "  2. Go to More → Settings → External Library"
  echo "  3. Add /app/Photos/ to scan your photos"
  echo ""
  echo -e "  ${CYAN}Management commands (run in ${INSTALL_DIR}):${NC}"
  echo "    Stop:      ${COMPOSE_CMD} --env-file .env down"
  echo "    Restart:   ${COMPOSE_CMD} --env-file .env restart"
  echo "    Logs:      ${COMPOSE_CMD} --env-file .env logs -f"
  echo "    Upgrade:   ./install.sh --upgrade"
  echo ""
}

# ── Upgrade ──────────────────────────────────────────────────────────────────

do_upgrade() {
  step "Upgrading TrailSnap..."

  if [[ ! -f "${INSTALL_DIR}/.env" ]]; then
    die "No existing installation found at ${INSTALL_DIR}. Run without --upgrade to install."
  fi

  # Source existing config
  source "${INSTALL_DIR}/.env" 2>/dev/null || true

  # Regenerate compose (in case template changed)
  generate_compose

  # Pull new images
  pull_images

  # Recreate containers
  cd "$INSTALL_DIR"
  $COMPOSE_CMD --env-file .env up -d --remove-orphans

  # Health check
  health_check

  print_success
  info "Upgrade complete. Your .env configuration was preserved."
}

# ── Uninstall ────────────────────────────────────────────────────────────────

do_uninstall() {
  step "Uninstalling TrailSnap..."

  if [[ ! -f "${INSTALL_DIR}/docker-compose.yml" ]]; then
    die "No installation found at ${INSTALL_DIR}."
  fi

  cd "$INSTALL_DIR"

  # Stop and remove containers
  $COMPOSE_CMD --env-file .env down 2>/dev/null || true
  info "Containers stopped and removed."

  if [[ "$PURGE_FLAG" == true ]]; then
    local answer
    answer="$(prompt_yes_no "This will DELETE all data (database, models, uploads). Are you sure?" "n")"
    if [[ "$answer" == "y" ]]; then
      rm -rf "${INSTALL_DIR}/pg_data"
      rm -rf "${INSTALL_DIR}/data"
      rm -f "${INSTALL_DIR}/.env"
      rm -f "${INSTALL_DIR}/docker-compose.yml"
      info "All data deleted."
    fi
  else
    info "Data directories preserved at ${INSTALL_DIR}/"
    info "To delete data too, run: ./install.sh --uninstall --purge"
  fi

  info "Uninstall complete."
}

# ── CLI Argument Parsing ─────────────────────────────────────────────────────

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --photo-dir)       PHOTO_DIR="$2"; shift 2 ;;
      --install-dir)     INSTALL_DIR="$2"; shift 2 ;;
      --frontend-port)   FRONTEND_PORT="$2"; shift 2 ;;
      --server-port)     SERVER_PORT="$2"; shift 2 ;;
      --ai-port)         AI_PORT="$2"; shift 2 ;;
      --postgres-port)   POSTGRES_PORT="$2"; shift 2 ;;
      --timezone)        TZ="$2"; shift 2 ;;
      --ai-mode)         AI_MODE="$2"; shift 2 ;;
      --tag)             IMAGE_TAG="$2"; shift 2 ;;
      --china-mirrors)   CHINA_MIRRORS_FLAG=true; shift ;;
      --yes|-y)          YES_FLAG=true; shift ;;
      --upgrade)         UPGRADE_FLAG=true; shift ;;
      --uninstall)       UNINSTALL_FLAG=true; shift ;;
      --purge)           PURGE_FLAG=true; shift ;;
      --help|-h)         usage; exit 0 ;;
      --version|-v)      echo "install.sh v${SCRIPT_VERSION}"; exit 0 ;;
      *)                 die "Unknown option: $1. Use --help for usage." ;;
    esac
  done

  # Set defaults for unset values
  INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"
  FRONTEND_PORT="${FRONTEND_PORT:-$DEFAULT_FRONTEND_PORT}"
  SERVER_PORT="${SERVER_PORT:-$DEFAULT_SERVER_PORT}"
  AI_PORT="${AI_PORT:-$DEFAULT_AI_PORT}"
  POSTGRES_PORT="${POSTGRES_PORT:-$DEFAULT_POSTGRES_PORT}"
  TZ="${TZ:-$DEFAULT_TZ}"
  IMAGE_TAG="${IMAGE_TAG:-$DEFAULT_IMAGE_TAG}"
  AI_MODE="${AI_MODE:-$DEFAULT_AI_MODE}"
}

usage() {
  cat << 'USAGE'
TrailSnap (行影集) — One-Click Installation Script

Usage:
  ./install.sh [OPTIONS]

Options:
  --photo-dir PATH       Photo directory (comma-separated for multiple)
  --install-dir PATH     Installation directory (default: ~/trailsnap)
  --frontend-port PORT   Frontend port (default: 8082)
  --server-port PORT     Backend API port (default: 8800)
  --ai-port PORT         AI service port (default: 8801)
  --postgres-port PORT   PostgreSQL port (default: 5532)
  --timezone TZ          Timezone (default: Asia/Shanghai)
  --ai-mode cpu|gpu      AI mode (default: cpu)
  --tag latest|master    Docker image tag (default: latest)
  --china-mirrors        Configure China Docker registry mirrors
  --yes, -y              Non-interactive: accept all defaults
  --upgrade              Upgrade existing installation
  --uninstall            Uninstall TrailSnap
  --purge                Delete all data (use with --uninstall)
  --help, -h             Show this help message
  --version, -v          Show version

Examples:
  # Interactive install
  ./install.sh

  # Non-interactive install with all options
  ./install.sh --photo-dir /home/user/photos --china-mirrors --yes

  # GPU mode
  ./install.sh --photo-dir /home/user/photos --ai-mode gpu

  # Upgrade
  ./install.sh --upgrade

  # Uninstall (keep data)
  ./install.sh --uninstall

  # Uninstall (delete everything)
  ./install.sh --uninstall --purge
USAGE
}

# ── Main ─────────────────────────────────────────────────────────────────────

main() {
  parse_args "$@"
  print_banner

  # Handle uninstall first
  if [[ "$UNINSTALL_FLAG" == true ]]; then
    do_uninstall
    exit 0
  fi

  # Detect OS
  detect_os

  # Ensure Docker is available
  ensure_docker

  # Handle upgrade
  if [[ "$UPGRADE_FLAG" == true ]]; then
    do_upgrade
    exit 0
  fi

  # Configure mirrors (for China)
  configure_mirrors

  # Check for existing installation
  if [[ -f "${INSTALL_DIR}/docker-compose.yml" ]]; then
    warn "Existing installation found at ${INSTALL_DIR}."
    local answer
    answer="$(prompt_yes_no "Do you want to upgrade the existing installation?" "y")"
    if [[ "$answer" == "y" ]]; then
      do_upgrade
      exit 0
    else
      answer="$(prompt_yes_no "Reconfigure and reinstall? (Data will be preserved)" "n")"
      [[ "$answer" != "y" ]] && die "Aborted."
    fi
  fi

  # Collect configuration
  collect_config

  # Create install directory
  mkdir -p "$INSTALL_DIR"
  mkdir -p "${INSTALL_DIR}/pg_data"
  mkdir -p "${INSTALL_DIR}/data"

  # Generate configuration files
  generate_env
  generate_compose

  # Pull and start
  pull_images
  start_services

  # Health check
  if health_check; then
    print_success
  else
    echo ""
    warn "Some services may need more time to start."
    info "You can check status with: cd ${INSTALL_DIR} && ${COMPOSE_CMD} --env-file .env ps"
    info "Or view logs with: cd ${INSTALL_DIR} && ${COMPOSE_CMD} --env-file .env logs -f"
    echo ""
    echo -e "  Frontend:     http://localhost:${FRONTEND_PORT}"
    echo -e "  Backend API:  http://localhost:${SERVER_PORT}/docs"
  fi
}

main "$@"
