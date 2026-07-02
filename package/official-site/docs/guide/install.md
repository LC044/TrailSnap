::: info 安装指南
TrailSnap 目前仅支持docker部署，推荐使用 Docker Compose 进行快速部署。
:::

## Docker 部署 (推荐)

使用 Docker Compose 可以一键启动所有服务，包括前端、后端、数据库和 AI 服务。

如果你是在 NAS（如绿联、极空间、飞牛OS）上部署，建议阅读：

- [Docker 部署（通用）](/docs/guide/docker/)
- [绿联 NAS 部署](/docs/guide/docker/ugreen)
- [极空间部署](/docs/guide/docker/zspace)
- [飞牛OS 部署](/docs/guide/docker/fnos)

如果你没用过docker，并且用的是Windows系统，建议阅读：

- [Docker 部署（Windows）](/docs/guide/docker/windows)

### 一键安装脚本 (推荐)

TrailSnap 提供了一键安装脚本，自动完成 Docker 安装、镜像加速配置和服务部署，无需手动编写配置文件。

#### Windows PowerShell

如果首次使用可能需要重启计算机，才能完成安装，重启后请重新运行脚本。

```powershell
irm https://trailsnap.cn/install.ps1 -O install.ps1; powershell -ExecutionPolicy Bypass -File .\install.ps1
```

或下载后运行：

```powershell
# 交互式安装（按提示操作）
.\install.ps1

# 非交互式安装（指定照片目录，使用国内镜像加速）
.\install.ps1 -PhotoDir "D:\Photos" -ChinaMirrors -Yes

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

# 非交互式安装（指定照片目录，使用国内镜像加速）
./install.sh --photo-dir /home/user/photos --china-mirrors --yes

# 启用 GPU 加速
./install.sh --photo-dir /home/user/photos --ai-mode gpu

# 指定自定义端口
./install.sh --photo-dir /home/user/photos --frontend-port 8082 --server-port 8800
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

安装完成后，在安装目录（默认 `~/trailsnap`）下执行：

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

---

### 手动部署

如果你更倾向于手动配置，或是在 NAS 等特殊环境下部署，可以按照以下步骤操作。

#### 前置要求

- 安装 [Docker](https://docs.docker.com/get-docker/) 和 [Docker Compose](https://docs.docker.com/compose/install/)。
- 确保本地 5532, 8800, 8801, 8082 端口未被占用。

#### 部署步骤

1. **获取 `docker-compose.yml`**

   在项目根目录下创建一个 `docker-compose.yml` 文件，内容如下：

   ```yaml
   version: '3.8'

   services:
     postgres:
       image: pgvector/pgvector:pg18-trixie
       container_name: postgres_container
       restart: always
       environment:
         TZ: Asia/Shanghai
         POSTGRES_DB: trailsnap
         POSTGRES_USER: trailsnap
         POSTGRES_PASSWORD: trailsnap
         POSTGRES_INITDB_ARGS: "--encoding=UTF8 --lc-collate=C --lc-ctype=C"
         PGDATA: /var/lib/postgresql/data/pgdata
       networks: [ app-network ]
       volumes:
         - ./pg_data:/var/lib/postgresql/data
       healthcheck:
         test: ["CMD-SHELL", "pg_isready -U trailsnap -d trailsnap -p 5432"]
         interval: 5s
         timeout: 5s
         retries: 5
         start_period: 10s

     server:
       image: siyuan044/trailsnap-server:latest
       restart: always
       expose: [ "8000" ]
       ports: [ "8800:8000" ]
       networks: [ app-network ]
       volumes:
         - ./data:/app/data
         - /path/to/your/photos:/app/Photos  # 请修改为你的照片目录路径
       environment:
         - TZ=Asia/Shanghai
         - DB_URL=postgresql://trailsnap:trailsnap@postgres:5432/trailsnap
         - RAILWAY_DB_URL=postgresql://trailsnap:trailsnap@postgres:5432/railway
         - AI_API_URL=http://ai:8001
       depends_on:
         postgres:
           condition: service_healthy

     ai:
       image: siyuan044/trailsnap-ai:latest
       restart: always
       expose: [ "8001" ]
       ports: [ "8801:8001" ]
       networks: [ app-network ]
       volumes:
         - ./data:/app/data
       environment:
         - TZ=Asia/Shanghai
       
     frontend:
       image: siyuan044/trailsnap-frontend:latest
       restart: always
       ports: [ "8082:80" ]
       depends_on: [ server ]
       networks: [ app-network ]
       environment:
         - TZ=Asia/Shanghai

   networks:
     app-network:
       driver: bridge
   ```

2. **配置照片目录**

   修改 `server` 服务下的 `volumes` 配置，将 `/path/to/your/photos` 替换为你实际存放照片的本地目录路径。
   
   Windows 用户示例：
   ```yaml
   - F:\Photos:/app/Photos
   ```
   
   Linux/macOS 用户示例：
   ```yaml
   - /home/user/photos:/app/Photos
   ```

3. **启动服务**

   在 `docker-compose.yml` 所在目录下执行：

   ```bash
   docker-compose up -d
   ```

4. **访问应用**
   服务启动后，通过浏览器访问: `http://localhost:8082`

5. **访问后端 API**
   - 后端 API: `http://localhost:8800/docs`
   - AI 服务文档: `http://localhost:8801/docs`

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
