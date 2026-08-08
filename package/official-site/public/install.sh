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
SCRIPT_VERSION="1.5.4"
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
ALIYUN_REGISTRY="crpi-d7wuvvdylhqugyu2.cn-hangzhou.personal.cr.aliyuncs.com"

CHINA_MIRRORS=(
  "https://docker.1ms.run"
  "https://docker.xuanyuan.me"
  "https://dockerproxy.net"
  "https://docker.1panel.live"
  "https://dockerproxy.cn"
  "https://docker.nastool.de"
  "https://docker.agsv.top"
  "https://docker.agsvpt.work"
  "https://docker.m.daocloud.io"
  "https://dockerhub.anzu.vip"
  "https://docker.chenby.cn"
  "https://docker.jijiai.cn"
)

# ── 颜色 ─────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
GRAY='\033[0;37m'
WHITE='\033[0;97m'
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
ADD_PHOTO_DIR=""
LOG_FILE=""
IMAGE_REGISTRY=""
IMAGE_REGISTRY_RESOLVED=false

# ── 输入读取 ──────────────────────────────────────────────────────────────────
# 通过 curl | bash 运行时 stdin 是管道而非终端，直接 read 会读到 EOF。
# 此时改从 /dev/tty 读取，让一键安装仍可交互式提问。
# 仅当显式传入 --yes/-y 时才真正进入非交互模式。
read_line() {
  if [[ ! -t 0 && -r /dev/tty ]]; then
    read "$@" < /dev/tty
  else
    read "$@"
  fi
}

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
  printf "\033[0;36m%s\033[0m [%s]: " "$prompt_text" "$default_val" >&2
  read_line -r answer || true
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
  printf "\033[0;36m%s\033[0m [%s]: " "$prompt_text" "$indicator" >&2
  read_line -r answer || true
  answer="${answer:-$default_val}"
  [[ "${answer,,}" == "y" || "${answer,,}" == "yes" ]] && echo "y" || echo "n"
}

# ── 随机密码生成 ──────────────────────────────────────────────────────────────
# 生成安全的随机数据库密码，避免硬编码默认密码
generate_random_password() {
  local length="${1:-16}"
  local pw=""
  # head -c 读够字节后会关闭管道，上游 tr/openssl 收到 SIGPIPE 退出码 141，
  # 在 set -o pipefail 下会被判为失败从而触发 || 回退，导致两次输出拼接成 32 位。
  # 这里临时关闭 pipefail，并用显式判空回退。
  set +o pipefail
  pw="$(tr -dc 'A-Za-z0-9' </dev/urandom 2>/dev/null | head -c "$length")"
  if [[ -z "$pw" ]]; then
    pw="$(openssl rand -base64 18 2>/dev/null | tr -dc 'A-Za-z0-9' | head -c "$length")"
  fi
  set -o pipefail
  if [[ -z "$pw" ]]; then
    pw="Trailsnap$(date +%s)"
  fi
  echo "$pw"
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
  echo ""
  error "WSL2 中未找到 Docker。"
  info "请按以下任一方式准备 Docker："
  info "  方式一（推荐，搭配 Docker Desktop）："
  info "    1. 在 Windows 安装 Docker Desktop：https://docs.docker.com/desktop/install/windows-install/"
  info "    2. 启动 Docker Desktop → Settings → Resources → WSL Integration"
  info "    3. 勾选「Enable integration with my default WSL distro」，并开启当前发行版开关"
  info "    4. 在 WSL 内运行 'docker info'，应能输出 Server 信息"
  info "  方式二（WSL 内原生 Docker Engine，不依赖 Docker Desktop）："
  info "    sudo apt-get update && sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin"
  info "    sudo service docker start"
  info "    sudo usermod -aG docker \$USER && newgrp docker"
  die "准备好 Docker 后重新运行本脚本。"
}

# 尝试从 WSL2 内拉起 Windows 侧的 Docker Desktop
# 找到 exe 则后台启动并返回 0；找不到返回 1（调用方自行提示手动启动）
try_start_docker_desktop() {
  local dd_paths=(
    "/mnt/c/Program Files/Docker/Docker/Docker Desktop.exe"
    "/mnt/d/Program Files/Docker/Docker/Docker Desktop.exe"
  )
  local dd
  for dd in "${dd_paths[@]}"; do
    if [[ -f "$dd" ]]; then
      info "尝试启动 Docker Desktop：$dd"
      # cmd.exe start 以非阻塞方式拉起；wslpath 转 Windows 路径，转换失败则原样传
      local win_path
      win_path="$(wslpath -w "$dd" 2>/dev/null || echo "$dd")"
      cmd.exe /c start "" "$win_path" >/dev/null 2>&1 || true
      return 0
    fi
  done
  # 路径未命中时，尝试通过 powershell 拉起默认安装位置
  if command -v powershell.exe &>/dev/null; then
    if powershell.exe -NoProfile -Command \
      "Start-Process -FilePath 'C:\Program Files\Docker\Docker\Docker Desktop.exe'" >/dev/null 2>&1; then
      info "已通过 PowerShell 启动 Docker Desktop。"
      return 0
    fi
  fi
  return 1
}

# 等待 Docker 守护进程就绪，超时则打印明确排查指引并退出
wait_for_docker_desktop() {
  local max_retries="${1:-60}"   # 默认 60 次 × 3s ≈ 3 分钟
  local interval="${2:-3}"
  info "等待 Docker Desktop 启动（最多约 $((max_retries * interval)) 秒）..."
  local retries=0
  while ! docker info &>/dev/null && [[ $retries -lt $max_retries ]]; do
    sleep "$interval"
    retries=$((retries + 1))
    echo -n "."
  done
  echo ""
  if docker info &>/dev/null; then
    return 0
  fi
  return 1
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
    elif [[ "$OS" == "wsl2" ]]; then
      # WSL2：尝试自动拉起 Windows 侧的 Docker Desktop，再等待就绪
      if ! try_start_docker_desktop; then
        warn "未自动找到 Docker Desktop，请手动启动后继续。"
      fi
      if ! wait_for_docker_desktop 60 3; then
        echo ""
        error "Docker Desktop 仍未就绪。请按以下步骤排查："
        info "  1. 在 Windows 上手动启动 Docker Desktop，等待托盘图标变绿"
        info "  2. 确认 Docker Desktop → Settings → Resources → WSL Integration 中已勾选当前发行版"
        info "  3. 在 WSL 内运行 'docker info'，应能输出 Server 信息"
        info "  4. 若尚未安装：https://docs.docker.com/desktop/install/windows-install/"
        die "Docker Desktop 未响应。请启动后重新运行本脚本。"
      fi
    elif [[ "$OS" == "macos" ]]; then
      if ! wait_for_docker_desktop 60 3; then
        echo ""
        error "Docker Desktop 仍未就绪。"
        info "  1. 从「应用程序」中启动 Docker Desktop，等待托盘图标变绿"
        info "  2. 运行 'docker info' 确认 Server 信息可正常输出"
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

# ── 镜像仓库地区判断 ──────────────────────────────────────────────────────────

test_mirror() {
  local mirror="$1"
  # Docker Registry 的 /v2/ 端点正常情况下也可能返回 401/403（拉取才需鉴权，
  # 端点可达即可）。不能用 curl -f，否则会把可用镜像源误判为不可达。
  # 判定标准：能连上且 HTTP code ∈ {200, 401, 403}。
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 --max-time 10 "${mirror}/v2/" 2>/dev/null || true)"
  [[ "$code" == "200" || "$code" == "401" || "$code" == "403" ]]
}

# 判断当前是否位于中国大陆：依次看时区、系统语言、公网 IP 归属地
detect_in_china() {
  # 显式指定 --china-mirrors 时直接认定
  if [[ "$CHINA_MIRRORS_FLAG" == true ]]; then
    return 0
  fi

  # 1) 时区
  local tz=""
  if [[ -f /etc/timezone ]]; then
    tz="$(cat /etc/timezone 2>/dev/null | tr -d '[:space:]')"
  fi
  if [[ -z "$tz" ]] && command -v timedatectl &>/dev/null; then
    tz="$(timedatectl show -p Timezone --value 2>/dev/null | tr -d '[:space:]')"
    if [[ -z "$tz" ]]; then
      tz="$(timedatectl 2>/dev/null | awk -F': ' '/Time zone/ {print $2}' | awk '{print $1}')"
    fi
  fi
  # macOS：/etc/localtime 是指向 zoneinfo 的软链接
  if [[ -z "$tz" ]] && [[ -L /etc/localtime ]]; then
    tz="$(readlink /etc/localtime 2>/dev/null)"
    tz="${tz##*zoneinfo/}"
  fi
  case "$tz" in
    Asia/Shanghai|Asia/Chongqing|Asia/Urumqi|Asia/Harbin|Asia/Chungking|PRC)
      return 0
      ;;
  esac

  # 2) 系统语言/区域
  if [[ "${LANG:-}${LC_ALL:-}" == *zh_CN* ]]; then
    return 0
  fi

  # 3) 公网 IP 归属地兜底
  local country=""
  if command -v curl &>/dev/null; then
    country="$(curl -s --connect-timeout 3 --max-time 5 https://ipinfo.io/country 2>/dev/null | tr -d '[:space:]')"
    if [[ -z "$country" ]]; then
      country="$(curl -s --connect-timeout 3 --max-time 5 https://ipapi.co/country/ 2>/dev/null | tr -d '[:space:]')"
    fi
  fi
  if [[ "$country" == "CN" ]]; then
    return 0
  fi
  return 1
}

# 将可用镜像源合并写入 /etc/docker/daemon.json 并重启 Docker（Linux / WSL 原生）
configure_mirrors_linux() {
  local available_mirrors=("$@")

  local daemon_json="/etc/docker/daemon.json"

  # 使用 python3 安全地合并 JSON 配置（通过命令行参数传递路径，避免代码注入）
  if command -v python3 &>/dev/null; then
    local mirrors_json
    mirrors_json="$(printf '%s\n' "${available_mirrors[@]}" | python3 -c '
import json, sys
mirrors = [line.strip() for line in sys.stdin if line.strip()]
print(json.dumps(mirrors))
')"
    # daemon.json 是 root 所有，python3 以当前用户运行无法直接写。
    # 做法：python3 读取（通常 644 可读）并合并后输出到 stdout，再 sudo tee 写回。
    # 文件不存在或内容非法时从空对象 {} 开始。
    local merged
    merged="$(python3 -c '
import json, sys
daemon_json = sys.argv[1]
mirrors_json = sys.argv[2]
try:
    with open(daemon_json) as f:
        cfg = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    cfg = {}
cfg["registry-mirrors"] = json.loads(mirrors_json)
print(json.dumps(cfg, indent=2))
' "$daemon_json" "$mirrors_json")"
    echo "$merged" | sudo tee "$daemon_json" >/dev/null
  else
    # 回退：直接覆盖（无 python3 时）
    local mirrors_line
    mirrors_line="$(printf '"%s",' "${available_mirrors[@]}")"
    mirrors_line="${mirrors_line%,}"  # 去掉末尾逗号
    echo "{\"registry-mirrors\": [${mirrors_line}]}" | sudo tee "$daemon_json" >/dev/null
  fi

  sudo systemctl restart docker 2>/dev/null || sudo service docker restart 2>/dev/null || true
  info "Docker 镜像源已写入 ${daemon_json}，Docker 已重启。"
}

# 将可用镜像源写入 Docker Desktop 的 daemon.json 并重启（macOS / WSL2 Docker Desktop）
configure_mirrors_desktop() {
  local available_mirrors=("$@")

  # 确定 daemon.json 路径与重启方式
  local daemon_json=""
  local restart_kind=""
  case "$OS" in
    macos)
      daemon_json="$HOME/.docker/daemon.json"
      restart_kind="macos"
      ;;
    wsl2)
      # Docker Desktop 集成：写 Windows 侧 %USERPROFILE%\.docker\daemon.json
      local win_profile=""
      if command -v cmd.exe &>/dev/null; then
        win_profile="$(cmd.exe /c 'echo %USERPROFILE%' 2>/dev/null | tr -d '\r')"
      fi
      if [[ -n "$win_profile" ]] && command -v wslpath &>/dev/null; then
        local wsl_profile
        wsl_profile="$(wslpath -u "$win_profile" 2>/dev/null || true)"
        if [[ -n "$wsl_profile" ]]; then
          daemon_json="${wsl_profile}/.docker/daemon.json"
          restart_kind="wsl2-desktop"
        fi
      fi
      # 回退：WSL 内原生 Docker Engine
      if [[ -z "$daemon_json" ]]; then
        daemon_json="/etc/docker/daemon.json"
        restart_kind="linux"
      fi
      ;;
  esac

  # 是否需要 sudo（root 拥有的系统路径）
  local need_sudo=false
  if [[ "$daemon_json" == /etc/* ]] && [[ "$(id -u)" -ne 0 ]]; then
    need_sudo=true
  fi

  # 确保目录存在
  if $need_sudo; then
    sudo mkdir -p "$(dirname "$daemon_json")"
  else
    mkdir -p "$(dirname "$daemon_json")"
  fi

  # 合并 JSON 内容
  local content=""
  if command -v python3 &>/dev/null; then
    local mirrors_json
    mirrors_json="$(printf '%s\n' "${available_mirrors[@]}" | python3 -c '
import json, sys
mirrors = [line.strip() for line in sys.stdin if line.strip()]
print(json.dumps(mirrors))
')"
    content="$(python3 -c '
import json, sys
p = sys.argv[1]; m = sys.argv[2]
try:
    with open(p) as f:
        cfg = json.load(f)
except Exception:
    cfg = {}
cfg["registry-mirrors"] = json.loads(m)
print(json.dumps(cfg, indent=2))
' "$daemon_json" "$mirrors_json")"
  else
    local mirrors_line
    mirrors_line="$(printf '"%s",' "${available_mirrors[@]}")"
    mirrors_line="${mirrors_line%,}"
    content="{\"registry-mirrors\": [${mirrors_line}]}"
  fi

  if $need_sudo; then
    echo "$content" | sudo tee "$daemon_json" >/dev/null
  else
    echo "$content" > "$daemon_json"
  fi
  info "Docker 镜像源已写入 ${daemon_json}。"

  # 重启使配置生效
  case "$restart_kind" in
    macos)
      osascript -e 'quit app "Docker"' 2>/dev/null || pkill -f "Docker Desktop" 2>/dev/null || true
      sleep 5
      open -a Docker 2>/dev/null || open -a "Docker Desktop" 2>/dev/null || true
      info "等待 Docker Desktop 重启..."
      wait_for_docker_desktop 60 3 || warn "Docker Desktop 未能及时重启，请手动重启。"
      ;;
    wsl2-desktop)
      taskkill.exe /F /IM "Docker Desktop.exe" >/dev/null 2>&1 || true
      sleep 5
      try_start_docker_desktop || warn "未能自动启动 Docker Desktop，请手动重启。"
      wait_for_docker_desktop 60 3 || warn "Docker Desktop 未能及时重启，请手动重启。"
      ;;
    linux)
      sudo systemctl restart docker 2>/dev/null || sudo service docker restart 2>/dev/null || true
      ;;
  esac
  info "Docker 镜像源已配置。"
}

configure_mirrors() {
  if [[ "$IMAGE_REGISTRY_RESOLVED" == true ]]; then
    return
  fi
  IMAGE_REGISTRY_RESOLVED=true

  if detect_in_china; then
    IMAGE_REGISTRY="${ALIYUN_REGISTRY}/"
    CHINA_MIRRORS_FLAG=true
    info "检测到当前位于中国大陆，将从阿里云镜像仓库拉取镜像。"
    log "镜像仓库: ${ALIYUN_REGISTRY}"
  else
    IMAGE_REGISTRY=""
    info "未检测到位于中国大陆，将从 Docker Hub 拉取镜像。"
    log "镜像仓库: Docker Hub"
  fi
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
        read_line -rp "$(printf '\033[0;36m请选择 [1/2/3]: \033[0m')" choice || true
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
        read_line -rp "$(printf '\033[0;36m请选择 [1/2/3]: \033[0m')" choice || true
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
  DETECTED_AI_MODE="${AI_MODE}"
  if [[ "$AI_MODE" == "gpu" ]]; then
    if ! check_gpu_support; then
      warn "将回退到 CPU 模式。"
      DETECTED_AI_MODE="cpu"
    fi
  else
    local cpu_name=""
    if [[ "$OS" == "macos" ]]; then
      cpu_name="$(sysctl -n machdep.cpu.brand_string 2>/dev/null || true)"
    else
      cpu_name="$(grep -m 1 'model name' /proc/cpuinfo 2>/dev/null || true)"
    fi
    if echo "$cpu_name" | grep -qi "Intel"; then
      DETECTED_AI_MODE="openvino"
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
  echo -e "  ${WHITE}│  AI 模式:   ${DETECTED_AI_MODE}${NC}"
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

resolve_pg_password() {
  # 重新安装到同一目录时，pg_data 仍是用旧密码初始化的。若此时生成新密码写入
  # .env，server 会因密码不匹配连不上 postgres。故目录下已有 .env 且含密码时复用之。
  local env_path="${INSTALL_DIR}/.env"
  if [[ -f "$env_path" ]]; then
    local existing
    existing="$(grep -E '^POSTGRES_PASSWORD=' "$env_path" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' || true)"
    if [[ -n "$existing" ]]; then
      PG_PASSWORD="$existing"
      info "复用已有数据库密码（避免与现存 pg_data 不匹配）"
      return
    fi
  fi
  [[ -z "$PG_PASSWORD" ]] && PG_PASSWORD="$(generate_random_password)"
}

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

# Docker 镜像版本标签（默认 latest，可修改为指定版本号，如 v1.0.0 等）
IMAGE_TAG="${IMAGE_TAG}"

# AI 模式。可选：cpu、gpu、openvino
# GPU 需要用户手动指定，CPU 和 openvino 会自动检测。修改此环境变量可动态调整 AI 镜像。
AI_MODE="${DETECTED_AI_MODE}"

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
  configure_mirrors

  step "生成 docker-compose.yml..."

  # 升级 / 追加兼容：若已存在 docker-compose.yml 且含 /app/Photos 挂载行，则原样
  # 保留旧挂载目标（如 /app/Photos/ 或 /app/Photos1/ 或 /app/Photos/<name>），否则
  # 升级后容器内路径变化会让数据库里已索引的 file_path 全部失效。仅超出已有数量
  # 的新增目录才按 /app/Photos/<源目录名> 约定生成新挂载。同时去掉 :ro，保证照片
  # 删除等功能可用。
  local compose_path="${INSTALL_DIR}/docker-compose.yml"
  local preserved_lines=()
  local preserved_targets=()
  if [[ -f "$compose_path" ]]; then
    while IFS= read -r line; do
      if [[ "$line" == *":/app/Photos"* ]]; then
        local trimmed="${line#"${line%%[![:space:]]*}"}"  # 去前导空白
        preserved_lines+=("$trimmed")
        # 提取目标路径用于去重
        local target
        target="$(echo "$trimmed" | grep -oE '/app/Photos[^":]*' | head -1)"
        [[ -n "$target" ]] && preserved_targets+=("$target")
      fi
    done < "$compose_path"
  fi

  local photo_volumes=""
  local used_names=""
  local used_targets=""
  # 已有挂载目标名 / 目标路径加入占用集合（换行分隔，便于 grep -qxF 精确匹配）
  for t in "${preserved_targets[@]:-}"; do
    local seg="${t##*/}"
    [[ -n "$seg" ]] && used_names+="${seg}"$'\n'
    used_targets+="${t}"$'\n'
  done

  # 先过滤出非空目录，保证与已保留挂载行的下标对齐
  local dirs=()
  if [[ -n "$PHOTO_DIR" ]]; then
    IFS=',' read -ra raw_dirs <<< "$PHOTO_DIR"
    for d in "${raw_dirs[@]}"; do
      d="$(echo "$d" | xargs)"
      [[ -n "$d" ]] && dirs+=("$d")
    done
  fi

  local i=0
  for dir in "${dirs[@]:-}"; do
    # `${dirs[@]:-}` 在空数组下会展开为一个空串，跳过以免生成 `- ":/app/Photos/gallery"` 之类空挂载
    [[ -z "$dir" ]] && continue
    if [[ $i -lt ${#preserved_lines[@]} ]]; then
      # 复用已有挂载行，并去掉 :ro（转为可写，支持删除照片）：:ro 可能出现在结尾引号之前
      local pl="${preserved_lines[$i]}"
      pl="$(echo "$pl" | sed -E 's/:ro("?)$/\1/')"
      photo_volumes+="      ${pl}"$'\n'
    else
      # 新增目录：取源目录名作为图库标识（保留中文等 UTF-8 名称），清理非法字符
      local base_name
      base_name="$(basename "$dir")"
      base_name="$(echo "$base_name" | sed 's#[/\\]#_#g; s/^[[:space:]]*//;s/[[:space:]]*$//')"
      [[ -z "$base_name" ]] && base_name="gallery"
      local final_name="$base_name"
      local n=2
      while echo "$used_names" | grep -qxF "$final_name" \
            || echo "$used_targets" | grep -qxF "/app/Photos/$final_name"; do
        final_name="${base_name}_${n}"
        n=$((n + 1))
      done
      used_names+="${final_name}"$'\n'
      used_targets+="/app/Photos/${final_name}"$'\n'
      photo_volumes+="      - \"${dir}:/app/Photos/${final_name}\""$'\n'
    fi
    i=$((i + 1))
  done

  local gpu_block=""
  if [[ "$DETECTED_AI_MODE" == "gpu" ]]; then
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
    image: ${IMAGE_REGISTRY}pgvector/pgvector:pg18-trixie
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
    volumes:
      - ./pg_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U \${POSTGRES_USER} -d \${POSTGRES_DB} -p 5432"]
      interval: 5s
      timeout: 5s
      retries: 5
      start_period: 10s

  server:
    image: ${IMAGE_REGISTRY}siyuan044/trailsnap-server:\${IMAGE_TAG}
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

  ai:
    image: ${IMAGE_REGISTRY}siyuan044/trailsnap-ai:\${IMAGE_TAG}-\${AI_MODE}
    container_name: trailsnap-ai
    restart: always
    stop_grace_period: 15s
    expose: ["8001"]
    ports:
      - "\${AI_PORT}:8001"
    networks: [app-network]
    volumes:
      - ./data:/app/data
    environment:
      - TZ=\${TZ}${gpu_block}
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health-check', timeout=3)"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 30s

  frontend:
    image: ${IMAGE_REGISTRY}siyuan044/trailsnap-frontend:\${IMAGE_TAG}
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
  info "首次启动需初始化数据库并加载 AI 模型，可能需要几分钟，请耐心等待..."

  source "${INSTALL_DIR}/.env" 2>/dev/null || true

  local failed=false

  wait_for_service "PostgreSQL" \
    "docker inspect --format='{{.State.Health.Status}}' trailsnap-postgres 2>/dev/null | grep -q healthy" \
    90 || failed=true

  # AI 首次启动需加载 OCR/人脸/CLIP 等模型（openvino 尤慢），给到 5 分钟
  # 用 127.0.0.1 而非 localhost：WSL2 走 Windows Docker Desktop 时，IPv6 ::1 多不真正监听
  wait_for_service "AI 服务" \
    "curl -sf http://127.0.0.1:${AI_PORT}/health-check" \
    300 || failed=true

  # 后端首次启动需跑 alembic 迁移 + 导入 5A 景点 CSV，给到 4 分钟
  wait_for_service "后端" \
    "curl -sf http://127.0.0.1:${SERVER_PORT}/health-check -o /dev/null" \
    240 || failed=true

  wait_for_service "前端" \
    "curl -sf http://127.0.0.1:${FRONTEND_PORT} -o /dev/null" \
    90 || failed=true

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
  echo "  3. 页面会自动检测到挂载的照片目录，勾选后点击「添加选中的图库并扫描」即可"
  echo ""
  echo -e "  ${CYAN}管理命令（在 ${INSTALL_DIR} 目录下运行）：${NC}"
  echo "    停止:    ${COMPOSE_CMD} --env-file .env down"
  echo "    重启:    ${COMPOSE_CMD} --env-file .env restart"
  echo "    日志:    ${COMPOSE_CMD} --env-file .env logs -f"
  echo "    升级:    ./install.sh --upgrade"
  echo "    加目录:  ./install.sh --add-photo-dir /path/to/new-photos"
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
      AI_MODE)         DETECTED_AI_MODE="$value" ;;
      PHOTO_DIR)       PHOTO_DIR="$value" ;;
      POSTGRES_PASSWORD) PG_PASSWORD="$value" ;;
    esac
  done < <(grep -v '^#' "${INSTALL_DIR}/.env" 2>/dev/null || true)

  log "开始升级，保留现有配置"

  # 重新生成 .env：已读取的旧值会原样写回，同时补齐新版本可能新增的字段。
  # 升级前备份旧 .env，避免用户手改的额外字段被覆盖后无法找回。
  if [[ -f "${INSTALL_DIR}/.env" ]]; then
    cp -p "${INSTALL_DIR}/.env" "${INSTALL_DIR}/.env.bak.$(date +%Y%m%d%H%M%S 2>/dev/null || echo bak)" 2>/dev/null || true
  fi
  generate_env
  generate_compose
  configure_mirrors
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

# ── 添加新照片文件夹 ──────────────────────────────────────────────────────────

add_photo_dir() {
  local new_dir="$1"

  if [[ ! -f "${INSTALL_DIR}/docker-compose.yml" ]] || [[ ! -f "${INSTALL_DIR}/.env" ]]; then
    die "未在 ${INSTALL_DIR} 找到已安装的实例。请先安装 TrailSnap。"
  fi
  LOG_FILE="${INSTALL_DIR}/install.log"

  if [[ -z "$new_dir" ]]; then
    new_dir="$(prompt_default "请输入要添加的照片文件夹路径" "")"
    [[ -z "$new_dir" ]] && die "未输入路径。"
  fi
  # 去引号与空格
  new_dir="$(echo "$new_dir" | xargs)"
  new_dir="${new_dir#\"}"; new_dir="${new_dir%\"}"
  new_dir="${new_dir#\'}"; new_dir="${new_dir%\'}"

  # 校验目录存在；不存在时询问是否创建
  while [[ ! -d "$new_dir" ]]; do
    if [[ "$YES_FLAG" == true ]]; then
      die "照片目录不存在：$new_dir"
    fi
    warn "目录不存在：${new_dir}"
    echo "  1) 创建此目录"
    echo "  2) 输入其他路径"
    echo "  3) 取消"
    local choice
    read_line -rp "$(printf '\033[0;36m请选择 [1/2/3]: \033[0m')" choice || true
    case "$choice" in
      1)
        if mkdir -p "$new_dir" 2>/dev/null; then
          info "已创建目录：$new_dir"
        else
          error "创建目录失败：$new_dir，请检查权限。"
          continue
        fi
        ;;
      2)
        local alt
        alt="$(prompt_default "照片文件夹路径" "")"
        [[ -z "$alt" ]] && die "已取消。"
        alt="$(echo "$alt" | xargs)"
        alt="${alt#\"}"; alt="${alt%\"}"
        alt="${alt#\'}"; alt="${alt%\'}"
        new_dir="$alt"
        continue
        ;;
      3|*)
        die "已取消。"
        ;;
    esac
  done

  # 读取现有 .env，保留全部配置
  while IFS='=' read -r key value; do
    key="$(echo "$key" | xargs)"
    value="${value#\"}"; value="${value%\"}"
    case "$key" in
      FRONTEND_PORT)   FRONTEND_PORT="$value" ;;
      SERVER_PORT)     SERVER_PORT="$value" ;;
      AI_PORT)         AI_PORT="$value" ;;
      POSTGRES_PORT)   POSTGRES_PORT="$value" ;;
      TZ)              TZ="$value" ;;
      IMAGE_TAG)       IMAGE_TAG="$value" ;;
      AI_MODE)         DETECTED_AI_MODE="$value" ;;
      PHOTO_DIR)       PHOTO_DIR="$value" ;;
      POSTGRES_PASSWORD) PG_PASSWORD="$value" ;;
    esac
  done < <(grep -v '^#' "${INSTALL_DIR}/.env" 2>/dev/null || true)

  # 去重：若已登记则直接提示
  new_dir="$(cd "$new_dir" && pwd)"
  local existing
  if [[ -n "$PHOTO_DIR" ]]; then
    IFS=',' read -ra existing_dirs <<< "$PHOTO_DIR"
    for d in "${existing_dirs[@]}"; do
      d="$(echo "$d" | xargs)"
      [[ -z "$d" ]] && continue
      local resolved=""
      [[ -d "$d" ]] && resolved="$(cd "$d" && pwd)"
      [[ "$resolved" == "$new_dir" ]] && {
        info "该照片文件夹已挂载，无需重复添加：$new_dir"
        return
      }
    done
  fi

  # 追加到 PHOTO_DIR
  if [[ -n "$PHOTO_DIR" ]]; then
    PHOTO_DIR="${PHOTO_DIR},${new_dir}"
  else
    PHOTO_DIR="$new_dir"
  fi

  log "添加新照片文件夹：$new_dir"
  generate_env
  generate_compose

  # 重建容器使新挂载生效
  step "应用新挂载并重启服务..."
  cd "$INSTALL_DIR"
  $COMPOSE_CMD --env-file .env up -d --remove-orphans

  info "已添加照片文件夹：$new_dir"
  info "请在「更多 → 设置 → 外部图库」中点击「重新检测」，勾选新目录并添加扫描。"
  echo ""
  echo -e "  ${CYAN}管理命令（在 ${INSTALL_DIR} 目录下运行）：${NC}"
  echo "    日志:    ${COMPOSE_CMD} --env-file .env logs -f"
  echo ""
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
      --add-photo-dir)   ADD_PHOTO_DIR="$2"; shift 2 ;;
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
  --tag 版本号           Docker 镜像版本标签（默认：latest）
  --china-mirrors        强制使用国内阿里云镜像仓库
  --yes, -y              非交互模式：接受所有默认值
  --upgrade              升级已安装的实例
  --uninstall            卸载 TrailSnap
  --purge                删除所有数据（与 --uninstall 配合使用）
  --add-photo-dir 路径   向已安装实例追加一个新的照片文件夹
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

  # 添加新的照片文件夹
  ./install.sh --add-photo-dir /home/user/new-photos

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

  # 处理添加新照片文件夹
  if [[ -n "$ADD_PHOTO_DIR" ]]; then
    detect_os
    ensure_docker
    add_photo_dir "$ADD_PHOTO_DIR"
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
    echo "  7) 添加新的照片文件夹"
    echo "  0) 退出"

    local choice
    read_line -rp "$(printf '\033[0;36m请选择 [0-7]: \033[0m')" choice || true
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
      7)
        detect_os
        ensure_docker
        add_photo_dir ""
        exit 0
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

  # 确认镜像仓库（中国大陆使用阿里云，其他地区使用 Docker Hub）
  configure_mirrors

  # 收集配置
  collect_config

  # 硬件预检（在收集配置后执行，确保检查正确的磁盘）
  check_hardware

  # 复用已有 .env 中的数据库密码（重新安装到同一目录时避免与 pg_data 不匹配）
  resolve_pg_password

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
