::: info 安装指南
TrailSnap 目前仅支持docker部署，推荐使用 Docker Compose 进行快速部署。
:::

在开始前，请先完成[部署前检查](/docs/guide/preflight)，特别是照片目录权限、可用存储空间和局域网访问方式。

## Docker 部署 (推荐)

使用 Docker Compose 可以一键启动所有服务，包括前端、后端、数据库和 AI 服务。

如果你是在 NAS（如绿联、极空间、飞牛OS）上部署，建议阅读：

- [Docker 部署（通用）](/docs/guide/docker/)
- [绿联 NAS 部署](/docs/guide/docker/ugreen)
- [极空间部署](/docs/guide/docker/zspace)
- [飞牛OS 部署](/docs/guide/docker/fnos)

如果你没用过docker或者没有NAS，建议继续往下阅读！

### 一键安装脚本 (推荐)

TrailSnap 提供了一键安装脚本，自动完成 Docker 安装、镜像加速配置和服务部署，无需手动编写配置文件。

#### Windows PowerShell（不是CMD）

打开方式：win + R -> 输入cmd -> 点击弹窗左上角的加号 -> 输入下面的命令

如果首次使用可能需要重启计算机，才能完成安装，重启后请重新运行脚本。

```powershell
irm https://trailsnap.cn/install.ps1 -O install.ps1; powershell -ExecutionPolicy Bypass -File .\install.ps1
```

或下载后运行：

```powershell
# 交互式安装（按提示操作）
.\install.ps1

# 启用 GPU 加速
.\install.ps1 -PhotoDir "D:\Photos" -AiMode gpu
```

#### Linux / macOS / WSL2

```bash
curl -fsSL https://trailsnap.cn/install.sh | bash
```

或下载后运行：

```bash
# 交互式安装（按提示操作）
./install.sh

# 启用 GPU 加速
./install.sh --photo-dir /home/user/photos --ai-mode gpu
```

#### 脚本功能

- ✅ 自动检测操作系统，安装 Docker 和 Docker Compose
- ✅ 自动配置国内 Docker 镜像加速源（解决国内拉取镜像慢的问题）
- ✅ 交互式收集配置（安装目录、照片目录、端口、时区、CPU/GPU 模式）
- ✅ 自动生成 `.env` 和 `docker-compose.yml`
- ✅ 拉取镜像并启动服务
- ✅ 部署后自动健康检查
- ✅ 支持升级和卸载

#### 管理命令

安装完成后，在安装目录（默认 `~/trailsnap`，Windows一般是`C:\Users\用户名\trailsnap`）下执行：

```bash
# 查看服务状态
docker compose --env-file .env ps

# 查看日志
docker compose --env-file .env logs -f

# 停止服务
docker compose --env-file .env down

# 重启服务
docker compose --env-file .env restart

# 升级到最新版本
./install.sh --upgrade

# 卸载（保留数据）
./install.sh --uninstall

# 卸载（删除所有数据）
./install.sh --uninstall --purge
```

#### 完整参数列表

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--photo-dir` | 照片目录（逗号分隔支持多个） | 必填 |
| `--install-dir` | 安装目录 | `~/trailsnap` |
| `--frontend-port` | 前端端口 | `8082` |
| `--server-port` | 后端 API 端口 | `8800` |
| `--ai-port` | AI 服务端口 | `8801` |
| `--postgres-port` | PostgreSQL 端口 | `5532` |
| `--timezone` | 时区 | `Asia/Shanghai` |
| `--ai-mode` | AI 模式（`cpu` 或 `gpu`） | `cpu` |
| `--tag` | 镜像标签（`latest` 或 `master`） | `latest` |
| `--china-mirrors` | 配置国内 Docker 镜像加速源 | - |
| `--yes` / `-y` | 非交互模式，接受所有默认值 | - |
| `--upgrade` | 升级现有安装 | - |
| `--uninstall` | 卸载 | - |
| `--purge` | 删除所有数据（配合 `--uninstall`） | - |

服务部署完成后，也可以在手机上使用 TrailSnap。安装方法和服务器地址配置参见
[移动 App 使用指南](/docs/guide/mobile-app)。

### 手动部署

如果你更倾向于手动配置，或是在 NAS 等特殊环境下部署，可以阅读[Docker部署](/docs/guide/docker)。

#### 注意事项

::: warning
- **数据持久化**: 数据库数据会保存在当前目录下的 `pg_data` 文件夹中，应用数据保存在 `data` 文件夹中。请勿随意删除这些目录，以免丢失数据。
- **端口冲突**: 如果默认端口被占用，请在 `docker-compose.yml` 中修改 `ports` 映射（例如 `8083:80`）。
- **照片权限**: 确保 Docker 容器有权限读取挂载的照片目录。
- **使用 GPU 加速**：如果你的系统支持 GPU 加速，建议在 `docker-compose.yml` 中添加 GPU 支持。详细步骤请参考 [Docker 部署（GPU 支持）](./docker/index.md)。
- **体验新特性**：如果你想体验最新功能，可以把 `latest` 标签替换为 `master` 版本。
:::

### 开始使用

[如何使用?](./user.md)

## 源码部署

如果你希望参与开发或进行二次开发，可以选择源码部署。详细步骤请参考 [开发者指南 - 快速开始](../dev/guide.md)。
