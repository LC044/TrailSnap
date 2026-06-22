#!/usr/bin/env bash
# =============================================================================
# TrailSnap (行影集) — 一键安装脚本
# https://github.com/LC044/TrailSnap
#
# 用法：
#   交互式安装:    ./install.sh
#   非交互式安装:  ./install.sh --photo-dir /path/to/photos --china-mirrors --yes
#   一键安装:      curl -fsSL https://trailsnap.cn/install.sh | bash
#   升级:          ./install.sh --upgrade
#   卸载:          ./install.sh --uninstall [--purge]
# =============================================================================

set -euo pipefail

# ── 常量 ──────────────────────────────────────────────────────────────────────
SCRIPT_VERSION="1.2.0"
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

CHINA_MIRRORS=(
  "https://docker.1ms.run"
  "https://docker.xuanyuan.me"
  "https://dockerproxy.net"
)

# ── 颜色 ─────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
GRAY='\033[0;37m'
BOLD='\033[1m'
NC='\033[0m'

# ── 全局变量 ──────────────────────────────────────────────────────────────────
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
PG_PASSWORD=""
CHINA_MIRRORS_FLAG=false
YES_FLAG=false
UPGRADE_FLAG=false
UNINSTALL_FLAG=false
PURGE_FLAG=false
LOG_FILE=""

# ── 自动检测非交互模式 ────────────────────────────────────────────────────────
# 通过 curl | bash 运行时 stdin 不是终端，自动启用非交互模式
if [[ ! -t 0 ]]; then
  YES_FLAG=true
fi

# ── 工具函数 ──────────────────────────────────────────────────────────────────

print_banner() {
  echo -e "${CYAN}"
  echo "  +===============================================+"
  echo "  |                                               |"
  echo "  |       TrailSnap (行影集) — 一键安装           |"
  echo "  |       AI 驱动的自托管相册                     |"
  echo "  |                                               |"
  echo "  +===============================================+"
  echo -e "${NC}"
}

info()    { echo -e "${GREEN}[信息]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[警告]${NC}  $*"; }
error()   { echo -e "${RED}[错误]${NC} $*"; }
step()    { echo -e "${BLUE}==>${NC} ${BOLD}$*${NC}"; }

die() {
  error "$@"
  log "FATAL: $*"
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
  read -r answer || true
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
  read -r answer || true
  answer="${answer:-$default_val}"
  [[ "${answer,,}" == "y" || "${answer,,}" == "yes" ]] && echo "y" || echo "n"
}

# ── 随机密码生成 ──────────────────────────────────────────────────────────────
# 生成安全的随机数据库密码，避免硬编码默认密码
generate_random_password() {
  local length="${1:-16}"
  tr -dc 'A-Za-z0-9' </dev/urandom 2>/dev/null | head -c "$length" || \
    openssl rand -base64 18 2>/dev/null | tr -dc 'A-Za-z0-9' | head -c "$length" || \
    echo "Trailsnap$(date +%s)"
}

# ── 日志记录 ──────────────────────────────────────────────────────────────────
# 同时写入控制台和日志文件，方便安装失败后排查
log() {
  local msg="[$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo '???')] $*"
  if [[ -n "$LOG_FILE" ]] && [[ -d "$(dirname "$LOG_FILE")" ]]; then
    echo "$msg" >> "$LOG_FILE"
  fi
}

# ── 获取局域网 IP ────────────────────────────────────────────────────────────

get_lan_ip() {
  local ip=""
  # 尝试通过默认路由获取
  if command -v ip &>/dev/null; then
    local iface
    iface="$(ip route show default 2>/dev/null | awk '{print $5}' | head -1)"
    if [[ -n "$iface" ]]; then
      ip="$(ip -4 addr show "$iface" 2>/dev/null | grep -oP '(?<=inet )\S+' | cut -d/ -f1 | head -1)"
    fi
  fi
  # macOS 回退
  if [[ -z "$ip" ]] && command -v ifconfig &>/dev/null; then
    ip="$(ifconfig 2>/dev/null | grep 'inet ' | grep -v '127.0.0.1' | awk '{print $2}' | head -1)"
  fi
  # 通用回退
  if [[ -z "$ip" ]]; then
    ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  fi
  echo "$ip"
}

# ── 硬件预检 ──────────────────────────────────────────────────────────────────

check_hardware() {
  step "检查硬件资源..."

  # 检查磁盘空间
  local target_dir="${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"
  local free_kb
  free_kb="$(df -k "$target_dir" 2>/dev/null | tail -1 | awk '{print $4}')"
  if [[ -n "$free_kb" ]]; then
    local free_gb=$((free_kb / 1024 / 1024))
    if [[ $free_gb -lt 10 ]]; then
      die "磁盘剩余空间仅 ${free_gb} GB，不足以安装 TrailSnap（至少需要 10 GB）。请清理磁盘空间后重试。"
    elif [[ $free_gb -lt 15 ]]; then
      warn "磁盘剩余空间 ${free_gb} GB，安装 TrailSnap（含 AI 镜像）可能需要 10-15 GB。"
      warn "如果空间不足，可能导致下载失败。建议先清理磁盘。"
      local answer
      answer="$(prompt_yes_no "是否继续安装？" "n")"
      [[ "$answer" != "y" ]] && die "已取消。"
    else
      info "磁盘剩余空间 ${free_gb} GB，满足安装要求。"
    fi
    log "硬件检查: 磁盘 ${free_gb} GB 可用"
  else
    warn "无法检测磁盘空间，跳过检查。"
  fi

  # 检查内存
  local total_ram_mb
  if [[ -f /proc/meminfo ]]; then
    total_ram_mb="$(awk '/MemTotal/ {printf "%.0f", $2/1024}' /proc/meminfo 2>/dev/null)"
  elif command -v sysctl &>/dev/null; then
    total_ram_mb="$(sysctl -n hw.memsize 2>/dev/null | awk '{printf "%.0f", $1/1024/1024}')"
  fi
  if [[ -n "$total_ram_mb" ]]; then
    local total_ram_gb=$((total_ram_mb / 1024))
    if [[ $total_ram_gb -lt 4 ]]; then
      warn "系统内存 ${total_ram_gb} GB，运行 AI 服务可能会卡顿。"
      warn "建议至少 4 GB 内存。可以选择 CPU 模式（不启用 GPU 加速）。"
    else
      info "系统内存 ${total_ram_gb} GB，满足运行要求。"
    fi
    log "硬件检查: 内存 ${total_ram_gb} GB"
  else
    warn "无法检测系统内存，跳过检查。"
  fi
}

# ── 操作系统检测 ─────────────────────────────────────────────────────────────

detect_os() {
  step "检测操作系统..."
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
    die "不支持的操作系统：$uname_s。本脚本支持 Linux、macOS 和 WSL2。"
  fi

  ARCH="$(uname -m)"
  [[ "$ARCH" == "x86_64" ]] && ARCH="amd64"
  [[ "$ARCH" == "aarch64" ]] && ARCH="arm64"

  info "检测到：OS=${OS}, 架构=${ARCH}"
}

# ── Docker 检测与安装 ─────────────────────────────────────────────────────────

detect_docker() {
  if command -v docker &>/dev/null; then
    return 0
  fi
  return 1
}

detect_compose_cmd() {
  if docker compose version &>/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
    return 0
  fi
  if command -v docker-compose &>/dev/null; then
    COMPOSE_CMD="docker-compose"
    return 0
  fi
  return 1
}

install_docker_linux() {
  step "在 Linux 上安装 Docker..."

  if [[ "$(id -u)" -ne 0 ]]; then
    warn "Docker 安装需要 sudo 权限。"
  fi

  if [[ -f /etc/debian_version ]] || grep -qi "debian\|ubuntu" /etc/os-release 2>/dev/null; then
    install_docker_debian
  elif [[ -f /etc/redhat-release ]] || grep -qi "rhel\|centos\|fedora" /etc/os-release 2>/dev/null; then
    install_docker_rhel
  elif command -v apt-get &>/dev/null; then
    install_docker_debian
  else
    die "无法在此发行版上自动安装 Docker。请手动安装：https://docs.docker.com/get-docker/"
  fi
}

install_docker_debian() {
  step "通过 apt 安装 Docker（Debian/Ubuntu）..."
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
  info "Docker 安装成功。"
}

install_docker_rhel() {
  step "通过 dnf/yum 安装 Docker（RHEL/CentOS/Fedora）..."
  sudo dnf install -y dnf-utils || sudo yum install -y yum-utils
  sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo || \
    sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo

  sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin || \
    sudo yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

  sudo systemctl enable --now docker
  info "Docker 安装成功。"
}

install_docker_macos() {
  step "在 macOS 上安装 Docker..."
  if command -v brew &>/dev/null; then
    brew install --cask docker
    info "已通过 Homebrew 安装 Docker Desktop。请从应用程序中启动。"
  else
    warn "未检测到 Homebrew。"
    info "正在打开 Docker Desktop 下载页面..."
    # 检测芯片架构选择下载链接
    local docker_url
    if [[ "$(uname -m)" == "arm64" ]]; then
      docker_url="https://desktop.docker.com/mac/main/arm64/Docker.dmg"
    else
      docker_url="https://desktop.docker.com/mac/main/amd64/Docker.dmg"
    fi
    open "$docker_url" 2>/dev/null || \
      info "请手动下载 Docker Desktop：$docker_url"
    die "请安装 Docker Desktop 后重新运行本脚本。"
  fi
}

install_docker_wsl2() {
  step "为 WSL2 设置 Docker..."
  if command -v docker.exe &>/dev/null || command -v docker &>/dev/null; then
    info "检测到 Docker。如果是 Docker Desktop，请确保它正在运行。"
    return
  fi
  die "WSL2 中未找到 Docker。请安装 Docker Desktop for Windows：https://docs.docker.com/desktop/install/windows-install/"
}

ensure_docker() {
  step "检查 Docker..."

  if ! detect_docker; then
    warn "Docker 未安装。"
    local answer
    answer="$(prompt_yes_no "是否自动安装 Docker？" "y")"
    if [[ "$answer" == "y" ]]; then
      case "$OS" in
        linux)  install_docker_linux ;;
        macos)  install_docker_macos ;;
        wsl2)   install_docker_wsl2 ;;
        *)      die "无法在 $OS 上自动安装 Docker" ;;
      esac
    else
      die "Docker 是必需的。请手动安装：https://docs.docker.com/get-docker/"
    fi
  fi

  # Linux 上将用户加入 docker 组
  if [[ "$OS" == "linux" ]] && [[ "$(id -u)" -ne 0 ]] && ! groups "$(whoami)" | grep -q docker; then
    info "正在将当前用户加入 docker 组..."
    sudo usermod -aG docker "$(whoami)" 2>/dev/null || true
    warn "您可能需要注销并重新登录才能使 docker 组生效。"
    warn "或者运行：newgrp docker"
  fi

  # 检查 Docker 守护进程
  if ! docker info &>/dev/null; then
    warn "Docker 守护进程未运行。"
    if [[ "$OS" == "linux" ]]; then
      info "正在启动 Docker 守护进程..."
      sudo systemctl start docker || die "启动 Docker 失败。请手动启动。"
    elif [[ "$OS" == "macos" || "$OS" == "wsl2" ]]; then
      info "等待 Docker Desktop 启动..."
      local retries=0
      while ! docker info &>/dev/null && [[ $retries -lt 30 ]]; do
        sleep 2
        retries=$((retries + 1))
        echo -n "."
      done
      echo ""
      if ! docker info &>/dev/null; then
        die "Docker Desktop 未响应。请启动后重新运行本脚本。"
      fi
    fi
  fi

  info "Docker 已运行。"
  log "Docker 检查通过"

  if ! detect_compose_cmd; then
    if [[ "$OS" == "linux" ]]; then
      warn "未找到 Docker Compose。正在安装 docker-compose-plugin..."
      sudo apt-get install -y -qq docker-compose-plugin 2>/dev/null || \
        sudo dnf install -y -q docker-compose-plugin 2>/dev/null || \
        die "安装 Docker Compose 失败。请手动安装。"
      COMPOSE_CMD="docker compose"
    else
      die "未找到 Docker Compose。请安装：https://docs.docker.com/compose/install/"
    fi
  fi

  info "Compose 命令：${COMPOSE_CMD}"
}

# ── 国内镜像源 ────────────────────────────────────────────────────────────────

test_mirror() {
  local mirror="$1"
  curl -sfSL --connect-timeout 5 "${mirror}/v2/" &>/dev/null
}

configure_mirrors_linux() {
  step "配置国内 Docker 镜像加速源..."

  local available_mirrors=()
  for mirror in "${CHINA_MIRRORS[@]}"; do
    info "测试镜像源：${mirror}..."
    if test_mirror "$mirror"; then
      available_mirrors+=("$mirror")
      info "  ✓ 可用"
    else
      warn "  ✗ 不可达"
    fi
  done

  if [[ ${#available_mirrors[@]} -eq 0 ]]; then
    warn "没有可用的镜像源，跳过配置。"
    return
  fi

  local daemon_json="/etc/docker/daemon.json"

  # 使用 python3 安全地合并 JSON 配置（通过命令行参数传递路径，避免代码注入）
  if command -v python3 &>/dev/null; then
    local mirrors_json
    mirrors_json="$(printf '%s\n' "${available_mirrors[@]}" | python3 -c '
import json, sys
mirrors = [line.strip() for line in sys.stdin if line.strip()]
print(json.dumps(mirrors))
')"
    python3 -c '
import json, sys
daemon_json = sys.argv[1]
mirrors_json = sys.argv[2]
with open(daemon_json) as f:
    cfg = json.load(f)
cfg["registry-mirrors"] = json.loads(mirrors_json)
with open(daemon_json, "w") as f:
    json.dump(cfg, f, indent=2)
' "$daemon_json" "$mirrors_json"
  else
    # 回退：直接覆盖（无 python3 时）
    local mirrors_line
    mirrors_line="$(printf '"%s",' "${available_mirrors[@]}")"
    mirrors_line="${mirrors_line%,}"  # 去掉末尾逗号
    echo "{\"registry-mirrors\": [${mirrors_line}]}" | sudo tee "$daemon_json" >/dev/null
  fi

  sudo systemctl restart docker
  info "Docker 镜像源已配置，Docker 已重启。"
}

configure_mirrors() {
  if [[ "$CHINA_MIRRORS_FLAG" != true ]]; then
    local answer
    answer="$(prompt_yes_no "是否配置国内 Docker 镜像加速源？" "y")"
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
      info "  2. 在 JSON 配置中添加以下内容："
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
      cont="$(prompt_yes_no "配置完成后是否继续？" "y")"
      [[ "$cont" != "y" ]] && die "请配置镜像源后重新运行脚本。"
      ;;
  esac
  log "镜像源配置完成"
}

# ── 端口检查（自动分配） ─────────────────────────────────────────────────────

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

# ── GPU 检查 ──────────────────────────────────────────────────────────────────

check_gpu_support() {
  if ! command -v nvidia-smi &>/dev/null; then
    warn "未检测到 nvidia-smi，GPU 不可用。"
    return 1
  fi

  info "检测到 NVIDIA GPU："
  nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | while read -r line; do
    info "  - $line"
  done

  if ! docker info 2>/dev/null | grep -q "nvidia"; then
    warn "Docker 中未检测到 NVIDIA Container Toolkit。"
    warn "GPU 模式可能无法使用。安装方法：https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html"
    local answer
    answer="$(prompt_yes_no "仍使用 GPU 模式？" "n")"
    [[ "$answer" != "y" ]] && return 1
  fi

  return 0
}

# ── 配置收集 ──────────────────────────────────────────────────────────────────

collect_config() {
  step "收集配置信息..."

  # 安装目录
  if [[ -z "$INSTALL_DIR" || "$INSTALL_DIR" == "$DEFAULT_INSTALL_DIR" ]]; then
    INSTALL_DIR="$(prompt_default "安装目录" "$DEFAULT_INSTALL_DIR")"
  fi
  while true; do
    if [[ -d "$INSTALL_DIR" ]]; then
      break
    fi
    local install_parent
    install_parent="$(dirname "$INSTALL_DIR")"
    if [[ -d "$install_parent" ]]; then
      local answer
      answer="$(prompt_yes_no "安装目录不存在：${INSTALL_DIR}。是否创建？" "y")"
      if [[ "$answer" == "y" ]]; then
        if mkdir -p "$INSTALL_DIR" 2>/dev/null; then
          info "已创建目录：${INSTALL_DIR}"
          break
        else
          error "创建目录失败：${INSTALL_DIR}"
          if [[ "$YES_FLAG" == true ]]; then
            die "无法创建安装目录，请检查权限。"
          fi
        fi
      fi
    else
      warn "父目录不存在：${install_parent}"
    fi
    if [[ "$YES_FLAG" == true ]]; then
      die "安装目录不存在且无法创建：${INSTALL_DIR}"
    fi
    INSTALL_DIR="$(prompt_default "安装目录" "$DEFAULT_INSTALL_DIR")"
  done

  # 照片目录（向导式循环输入）
  local validated_photo_dirs=()

  if [[ -z "$PHOTO_DIR" ]]; then
    # 交互式逐个输入
    echo ""
    info "请输入您的照片文件夹路径（一次一个，之后可以继续添加）。"
    while true; do
      local input_dir
      input_dir="$(prompt_default "照片文件夹路径" "")"
      if [[ -z "$input_dir" ]]; then
        if [[ ${#validated_photo_dirs[@]} -eq 0 ]]; then
          warn "照片文件夹是必需的。"
          if [[ "$YES_FLAG" == true ]]; then
            die "非交互模式下必须通过 --photo-dir 指定照片目录。"
          fi
          continue
        fi
        break
      fi

      # 去除引号和空格
      local current_dir
      current_dir="$(echo "$input_dir" | xargs)"
      current_dir="${current_dir#\"}"
      current_dir="${current_dir%\"}"
      current_dir="${current_dir#\'}"
      current_dir="${current_dir%\'}"

      # 验证目录
      while true; do
        if [[ -d "$current_dir" ]]; then
          validated_photo_dirs+=("$current_dir")
          info "已添加：$current_dir"
          break
        fi
        if [[ "$YES_FLAG" == true ]]; then
          warn "照片目录不存在：$current_dir"
          die "照片目录必须存在。请创建后或通过 --photo-dir 指定有效路径。"
        fi
        echo ""
        warn "目录不存在：${current_dir}"
        echo "  1) 创建此目录"
        echo "  2) 输入其他路径"
        echo "  3) 取消"
        local choice
        read -rp "$(printf '\033[0;36m请选择 [1/2/3]: \033[0m')" choice || true
        case "${choice}" in
          1)
            if mkdir -p "$current_dir" 2>/dev/null; then
              info "已创建目录：${current_dir}"
              validated_photo_dirs+=("$current_dir")
              break
            else
              error "创建目录失败：${current_dir}，请检查权限。"
              continue
            fi
            ;;
          2)
            local new_dir
            new_dir="$(prompt_default "照片文件夹路径" "")"
            if [[ -n "$new_dir" ]]; then
              new_dir="$(echo "$new_dir" | xargs)"
              new_dir="${new_dir#\"}"
              new_dir="${new_dir%\"}"
              new_dir="${new_dir#\'}"
              new_dir="${new_dir%\'}"
              current_dir="$new_dir"
              continue  # 重新验证
            fi
            ;;
          3|*)
            die "已取消。"
            ;;
        esac
      done

      # 询问是否继续添加
      local more
      more="$(prompt_yes_no "是否继续添加其他照片文件夹？" "n")"
      [[ "$more" != "y" ]] && break
    done
  else
    # 命令行传入 --photo-dir（逗号分隔兼容）
    IFS=',' read -ra PHOTO_DIRS <<< "$PHOTO_DIR"
    for dir in "${PHOTO_DIRS[@]}"; do
      dir="$(echo "$dir" | xargs)"
      dir="${dir#\"}"
      dir="${dir%\"}"
      dir="${dir#\'}"
      dir="${dir%\'}"

      while true; do
        if [[ -d "$dir" ]]; then
          validated_photo_dirs+=("$dir")
          break
        fi
        if [[ "$YES_FLAG" == true ]]; then
          warn "照片目录不存在：$dir"
          die "照片目录必须存在。请创建后或通过 --photo-dir 指定有效路径。"
        fi
        echo ""
        warn "目录不存在：${dir}"
        echo "  1) 创建此目录"
        echo "  2) 输入其他路径"
        echo "  3) 取消"
        local choice
        read -rp "$(printf '\033[0;36m请选择 [1/2/3]: \033[0m')" choice || true
        case "${choice}" in
          1)
            if mkdir -p "$dir" 2>/dev/null; then
              info "已创建目录：${dir}"
              validated_photo_dirs+=("$dir")
              break
            else
              error "创建目录失败：${dir}，请检查权限。"
              continue
            fi
            ;;
          2)
            local new_dir
            new_dir="$(prompt_default "照片文件夹路径" "")"
            if [[ -n "$new_dir" ]]; then
              new_dir="$(echo "$new_dir" | xargs)"
              new_dir="${new_dir#\"}"
              new_dir="${new_dir%\"}"
              new_dir="${new_dir#\'}"
              new_dir="${new_dir%\'}"
              dir="$new_dir"
              continue
            fi
            ;;
          3|*)
            die "已取消。"
            ;;
        esac
      done
    done
  fi

  # 重建 PHOTO_DIR
  PHOTO_DIR=""
  for dir in "${validated_photo_dirs[@]}"; do
    [[ -n "$PHOTO_DIR" ]] && PHOTO_DIR+=","
    PHOTO_DIR+="$dir"
  done

  # 端口（自动分配，无需用户确认）
  FRONTEND_PORT="${FRONTEND_PORT:-$DEFAULT_FRONTEND_PORT}"
  SERVER_PORT="${SERVER_PORT:-$DEFAULT_SERVER_PORT}"
  AI_PORT="${AI_PORT:-$DEFAULT_AI_PORT}"
  POSTGRES_PORT="${POSTGRES_PORT:-$DEFAULT_POSTGRES_PORT}"

  for port_var in FRONTEND_PORT SERVER_PORT AI_PORT POSTGRES_PORT; do
    local port="${!port_var}"
    if ! check_port_available "$port"; then
      local suggested
      suggested="$(suggest_port "$port")"
      info "端口 ${port} 已被占用，已自动分配新端口 ${suggested}。"
      eval "${port_var}=\"${suggested}\""
    fi
  done

  # TZ、AI 模式、镜像标签：使用默认值，不主动询问（高级选项可通过命令行参数指定）
  TZ="${TZ:-$DEFAULT_TZ}"
  AI_MODE="${AI_MODE:-$DEFAULT_AI_MODE}"
  IMAGE_TAG="${IMAGE_TAG:-$DEFAULT_IMAGE_TAG}"

  # GPU 检查
  if [[ "$AI_MODE" == "gpu" ]]; then
    if ! check_gpu_support; then
      warn "将回退到 CPU 模式。"
      AI_MODE="cpu"
    fi
  fi

  # 设置日志文件路径
  LOG_FILE="${INSTALL_DIR}/install.log"
}

# ── 安装前确认摘要 ────────────────────────────────────────────────────────────

show_confirm_summary() {
  local photo_display
  photo_display="${PHOTO_DIR//,/, }"

  echo ""
  echo -e "  ${CYAN}┌─────────────────────────────────────────────┐${NC}"
  echo -e "  ${CYAN}│          安装配置确认                        │${NC}"
  echo -e "  ${CYAN}├─────────────────────────────────────────────┤${NC}"
  echo -e "  ${WHITE}│  安装目录:  ${INSTALL_DIR}${NC}"
  echo -e "  ${WHITE}│  照片目录:  ${photo_display}${NC}"
  echo -e "  ${WHITE}│  前端端口:  ${FRONTEND_PORT}${NC}"
  echo -e "  ${WHITE}│  AI 模式:   ${AI_MODE}${NC}"
  echo -e "  ${WHITE}│  数据库密码: ${PG_PASSWORD}${NC}"
  echo -e "  ${GRAY}│              （请妥善保管，升级时自动保留）  ${NC}"
  echo -e "  ${CYAN}└─────────────────────────────────────────────┘${NC}"
  echo ""

  local answer
  answer="$(prompt_yes_no "确认以上配置无误，开始安装？" "y")"
  [[ "$answer" != "y" ]] && die "已取消。"
  log "用户确认安装配置"
}

# ── 文件生成 ──────────────────────────────────────────────────────────────────

generate_env() {
  step "生成 .env 配置文件..."
  cat > "${INSTALL_DIR}/.env" << EOF
# TrailSnap 配置 — 由 install.sh v${SCRIPT_VERSION} 生成
# https://github.com/LC044/TrailSnap

# 照片目录（逗号分隔，支持多个挂载点）
PHOTO_DIR="${PHOTO_DIR}"

# 端口
FRONTEND_PORT=${FRONTEND_PORT}
SERVER_PORT=${SERVER_PORT}
AI_PORT=${AI_PORT}
POSTGRES_PORT=${POSTGRES_PORT}

# 时区
TZ="${TZ}"

# Docker 镜像标签（latest 或 master）
IMAGE_TAG="${IMAGE_TAG}"

# AI 模式：cpu 或 gpu
AI_MODE="${AI_MODE}"

# 数据库
POSTGRES_DB="${DEFAULT_PG_DB}"
POSTGRES_USER="${DEFAULT_PG_USER}"
POSTGRES_PASSWORD="${PG_PASSWORD}"
EOF

  chmod 600 "${INSTALL_DIR}/.env"
  info "已创建 ${INSTALL_DIR}/.env"
  log "已生成 .env 配置文件"
}

generate_compose() {
  step "生成 docker-compose.yml..."

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

  info "已创建 ${INSTALL_DIR}/docker-compose.yml"
  log "已生成 docker-compose.yml"
}

# ── 健康检查 ──────────────────────────────────────────────────────────────────

wait_for_service() {
  local name="$1"
  local test_cmd="$2"
  local timeout="${3:-60}"
  local interval=5
  local elapsed=0

  echo -n "  等待 ${name} 启动..."
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
  step "运行健康检查..."

  source "${INSTALL_DIR}/.env" 2>/dev/null || true

  local failed=false

  wait_for_service "PostgreSQL" \
    "docker inspect --format='{{.State.Health.Status}}' trailsnap-postgres 2>/dev/null | grep -q healthy" \
    60 || failed=true

  wait_for_service "AI 服务" \
    "curl -sf http://localhost:${AI_PORT}/health-check" \
    90 || failed=true

  wait_for_service "后端" \
    "curl -sf http://localhost:${SERVER_PORT}/health-check -o /dev/null" \
    90 || failed=true

  wait_for_service "前端" \
    "curl -sf http://localhost:${FRONTEND_PORT} -o /dev/null" \
    60 || failed=true

  if [[ "$failed" == true ]]; then
    echo ""
    error "部分服务健康检查失败。"
    info "正在查看日志..."
    cd "$INSTALL_DIR"
    $COMPOSE_CMD --env-file .env logs --tail=50
    echo ""
    warn "手动查看日志：cd ${INSTALL_DIR} && ${COMPOSE_CMD} --env-file .env logs -f"
    log "健康检查: 部分服务失败"
    return 1
  fi

  log "健康检查: 全部通过"
  return 0
}

# ── 拉取与启动 ────────────────────────────────────────────────────────────────

pull_images() {
  step "拉取 Docker 镜像（可能需要几分钟，如果拉取失败，请检查网络和 Docker 配置。）..."
  if [[ "$CHINA_MIRRORS_FLAG" != true ]]; then
    info "提示：如果您在中国大陆地区，镜像拉取慢，可取消安装并添加 --china-mirrors 参数重新运行"
  fi
  cd "$INSTALL_DIR"
  if ! $COMPOSE_CMD --env-file .env pull; then
    error "拉取镜像失败。"
    if [[ "$CHINA_MIRRORS_FLAG" != true ]]; then
      warn "如果您在国内，请尝试添加 --china-mirrors 参数重新运行。"
    fi
    die "镜像拉取失败，请检查网络和 Docker 配置。"
  fi
  log "Docker 镜像拉取完成"
}

start_services() {
  step "启动服务..."
  cd "$INSTALL_DIR"
  $COMPOSE_CMD --env-file .env up -d
  info "服务已启动。"
  log "Docker 服务已启动"
}

# ── 成功横幅 ──────────────────────────────────────────────────────────────────

print_service_urls() {
  local lan_ip
  lan_ip="$(get_lan_ip)"
  echo ""
  echo -e "  ${CYAN}访问地址：${NC}"
  echo -e "  💻 本机访问:  http://localhost:${FRONTEND_PORT}"
  if [[ -n "$lan_ip" ]]; then
    echo -e "  📱 手机访问:  http://${lan_ip}:${FRONTEND_PORT}  (需连接同一 Wi-Fi)"
  fi
  echo ""
  echo -e "  ${GRAY}后端 API:  http://localhost:${SERVER_PORT}/docs${NC}"
  echo -e "  ${GRAY}AI 服务:   http://localhost:${AI_PORT}/docs${NC}"
  echo ""
}

print_success() {
  source "${INSTALL_DIR}/.env" 2>/dev/null || true

  echo ""
  echo -e "${GREEN}+===========================================================+${NC}"
  echo -e "${GREEN}|                                                           |${NC}"
  echo -e "${GREEN}|       🎉  TrailSnap (行影集) 安装成功！ 🎉              |${NC}"
  echo -e "${GREEN}|                                                           |${NC}"
  echo -e "${GREEN}+===========================================================+${NC}"
  
  print_service_urls
  
  echo -e "  ${CYAN}下一步：${NC}"
  echo "  1. 在浏览器中打开上面的访问地址"
  echo "  2. 进入 更多 → 设置 → 外部图库"
  echo "  3. 添加 /app/Photos/ 以扫描照片"
  echo ""
  echo -e "  ${CYAN}管理命令（在 ${INSTALL_DIR} 目录下运行）：${NC}"
  echo "    停止:    ${COMPOSE_CMD} --env-file .env down"
  echo "    重启:    ${COMPOSE_CMD} --env-file .env restart"
  echo "    日志:    ${COMPOSE_CMD} --env-file .env logs -f"
  echo "    升级:    ./install.sh --upgrade"
  echo ""

  # 自动打开浏览器
  info "正在打开浏览器..."
  if [[ "$OS" == "macos" ]]; then
    open "http://localhost:${FRONTEND_PORT}" 2>/dev/null || true
  elif [[ "$OS" == "linux" ]]; then
    xdg-open "http://localhost:${FRONTEND_PORT}" 2>/dev/null || true
  fi

  log "安装成功完成"
}

# ── 升级 ──────────────────────────────────────────────────────────────────────

do_upgrade() {
  step "正在升级 TrailSnap..."

  if [[ ! -f "${INSTALL_DIR}/.env" ]]; then
    die "未在 ${INSTALL_DIR} 找到已安装的实例。请直接运行（不带 --upgrade）来安装。"
  fi

  # 设置日志文件
  LOG_FILE="${INSTALL_DIR}/install.log"

  # 读取现有配置，保留密码等关键信息
  while IFS='=' read -r key value; do
    key="$(echo "$key" | xargs)"
    # 去除值两端的引号
    value="${value#\"}"
    value="${value%\"}"
    case "$key" in
      FRONTEND_PORT)   FRONTEND_PORT="$value" ;;
      SERVER_PORT)     SERVER_PORT="$value" ;;
      AI_PORT)         AI_PORT="$value" ;;
      POSTGRES_PORT)   POSTGRES_PORT="$value" ;;
      TZ)              TZ="$value" ;;
      IMAGE_TAG)       IMAGE_TAG="$value" ;;
      AI_MODE)         AI_MODE="$value" ;;
      PHOTO_DIR)       PHOTO_DIR="$value" ;;
      POSTGRES_PASSWORD) PG_PASSWORD="$value" ;;
    esac
  done < <(grep -v '^#' "${INSTALL_DIR}/.env" 2>/dev/null || true)

  log "开始升级，保留现有配置"

  generate_compose
  pull_images

  cd "$INSTALL_DIR"
  $COMPOSE_CMD --env-file .env up -d --remove-orphans

  health_check

  print_success
  info "升级完成。您的 .env 配置已保留。"
}

# ── 卸载 ──────────────────────────────────────────────────────────────────────

do_uninstall() {
  step "正在卸载 TrailSnap..."

  if [[ ! -f "${INSTALL_DIR}/docker-compose.yml" ]]; then
    die "未在 ${INSTALL_DIR} 找到已安装的实例。"
  fi

  cd "$INSTALL_DIR"

  $COMPOSE_CMD --env-file .env down 2>/dev/null || true
  info "容器已停止并移除。"

  if [[ "$PURGE_FLAG" == true ]]; then
    local answer
    answer="$(prompt_yes_no "这将删除所有数据（数据库、模型、上传文件）。确定吗？" "n")"
    if [[ "$answer" == "y" ]]; then
      rm -rf "${INSTALL_DIR}/pg_data"
      rm -rf "${INSTALL_DIR}/data"
      rm -f "${INSTALL_DIR}/.env"
      rm -f "${INSTALL_DIR}/docker-compose.yml"
      info "所有数据已删除。"
    fi
  else
    info "数据目录已保留在 ${INSTALL_DIR}/"
    info "如需删除数据，请运行：./install.sh --uninstall --purge"
  fi

  info "卸载完成。"
  log "卸载完成"
}

# ── 命令行参数解析 ────────────────────────────────────────────────────────────

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
      *)                 die "未知选项：$1。使用 --help 查看帮助。" ;;
    esac
  done

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
TrailSnap (行影集) — 一键安装脚本

用法：
  ./install.sh [选项]

选项：
  --photo-dir 路径       照片目录（逗号分隔支持多个）
  --install-dir 路径     安装目录（默认：~/trailsnap）
  --frontend-port 端口   前端端口（默认：8082）
  --server-port 端口     后端 API 端口（默认：8800）
  --ai-port 端口         AI 服务端口（默认：8801）
  --postgres-port 端口   PostgreSQL 端口（默认：5532）
  --timezone 时区        时区（默认：Asia/Shanghai）
  --ai-mode cpu|gpu      AI 模式（默认：cpu）
  --tag latest|master    Docker 镜像标签（默认：latest）
  --china-mirrors        配置国内 Docker 镜像加速源
  --yes, -y              非交互模式：接受所有默认值
  --upgrade              升级已安装的实例
  --uninstall            卸载 TrailSnap
  --purge                删除所有数据（与 --uninstall 配合使用）
  --help, -h             显示此帮助信息
  --version, -v          显示版本号

示例：
  # 交互式安装
  ./install.sh

  # 非交互式安装
  ./install.sh --photo-dir /home/user/photos --china-mirrors --yes

  # GPU 模式
  ./install.sh --photo-dir /home/user/photos --ai-mode gpu

  # 升级
  ./install.sh --upgrade

  # 卸载（保留数据）
  ./install.sh --uninstall

  # 卸载（删除所有数据）
  ./install.sh --uninstall --purge
USAGE
}

# ── 主流程 ────────────────────────────────────────────────────────────────────

main() {
  parse_args "$@"
  print_banner

  # 生成随机数据库密码
  PG_PASSWORD="$(generate_random_password)"

  log "TrailSnap 安装脚本 v${SCRIPT_VERSION} 启动"

  # 处理卸载
  if [[ "$UNINSTALL_FLAG" == true ]]; then
    LOG_FILE="${INSTALL_DIR}/install.log"
    do_uninstall
    exit 0
  fi

  # 检查是否已有安装
  if [[ -f "${INSTALL_DIR}/docker-compose.yml" ]]; then
    local is_service_running=false
    cd "$INSTALL_DIR"
    if command -v docker &>/dev/null; then
      if [[ -n "$(docker compose --env-file .env ps -q 2>/dev/null)" ]]; then
        is_service_running=true
      fi
    fi

    warn "在 ${INSTALL_DIR} 检测到已有安装。"
    echo "请选择操作："
    echo "  1) 升级到最新版本"
    echo "  2) 重新安装"
    echo "  3) 卸载（保留照片和数据）"
    echo "  4) 卸载（保留照片，删除其他数据）"
    if [[ "$is_service_running" == true ]]; then
      echo "  5) 关闭服务"
      echo "  6) 重启服务"
    else
      echo "  5) 启动服务"
    fi
    echo "  0) 退出"

    local choice
    read -rp "$(printf '\033[0;36m请选择 [0-6]: \033[0m')" choice || true
    case "$choice" in
      1)
        detect_os
        ensure_docker
        do_upgrade
        exit 0
        ;;
      2)
        # 继续执行重新安装流程
        ;;
      3)
        detect_os
        ensure_docker
        UNINSTALL_FLAG=true
        PURGE_FLAG=false
        do_uninstall
        exit 0
        ;;
      4)
        detect_os
        ensure_docker
        UNINSTALL_FLAG=true
        PURGE_FLAG=true
        do_uninstall
        exit 0
        ;;
      5)
        detect_os
        ensure_docker
        if [[ "$is_service_running" == true ]]; then
          cd "$INSTALL_DIR"
          $COMPOSE_CMD --env-file .env down
          info "服务已关闭。"
        else
          cd "$INSTALL_DIR"
          $COMPOSE_CMD --env-file .env up -d
          info "服务已启动。"
          source "${INSTALL_DIR}/.env" 2>/dev/null || true
          print_service_urls
        fi
        exit 0
        ;;
      6)
        detect_os
        ensure_docker
        if [[ "$is_service_running" == true ]]; then
          cd "$INSTALL_DIR"
          $COMPOSE_CMD --env-file .env restart
          info "服务已重启。"
          source "${INSTALL_DIR}/.env" 2>/dev/null || true
          print_service_urls
          exit 0
        else
          die "无效选择。"
        fi
        ;;
      0)
        die "已退出。"
        ;;
      *)
        die "无效选择。"
        ;;
    esac
  fi

  # 检测操作系统
  detect_os

  # 确保 Docker 可用
  ensure_docker

  # 处理升级
  if [[ "$UPGRADE_FLAG" == true ]]; then
    do_upgrade
    exit 0
  fi

  # 配置镜像源（国内用户）
  configure_mirrors

  # 收集配置
  collect_config

  # 硬件预检（在收集配置后执行，确保检查正确的磁盘）
  check_hardware

  # 安装前确认摘要
  show_confirm_summary

  # 创建安装目录
  mkdir -p "$INSTALL_DIR"
  mkdir -p "${INSTALL_DIR}/pg_data"
  mkdir -p "${INSTALL_DIR}/data"

  # 生成配置文件
  generate_env
  generate_compose

  # 拉取并启动
  pull_images
  start_services

  # 健康检查
  if health_check; then
    print_success
  else
    local lan_ip
    lan_ip="$(get_lan_ip)"
    echo ""
    warn "部分服务可能需要更多时间启动。"
    info "查看状态：cd ${INSTALL_DIR} && ${COMPOSE_CMD} --env-file .env ps"
    info "查看日志：cd ${INSTALL_DIR} && ${COMPOSE_CMD} --env-file .env logs -f"
    echo ""
    echo -e "  ${CYAN}访问地址：${NC}"
    echo -e "  💻 本机访问:  http://localhost:${FRONTEND_PORT}"
    if [[ -n "$lan_ip" ]]; then
      echo -e "  📱 手机访问:  http://${lan_ip}:${FRONTEND_PORT}  (需连接同一 Wi-Fi)"
    fi
    echo -e "  ${GRAY}后端 API:  http://localhost:${SERVER_PORT}/docs${NC}"
    log "安装完成，但部分服务健康检查未通过"
  fi
}

main "$@"
