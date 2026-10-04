# TrailSnap Backend Service

TrailSnap 的后端核心服务，基于 FastAPI 构建，负责业务逻辑处理、数据存储与检索、以及与 AI 服务的交互。

## 目录
1. [前置条件](#前置条件)
2. [快速开始](#快速开始)
3. [数据库配置](#数据库配置)
4. [配置说明](#配置说明)
5. [开发指南](#开发指南)

## 前置条件

生产部署推荐 PostgreSQL + `pgvector`。本地网页调试也可使用 SQLite；SQLite
只改变 Server 的持久化方式，Vue 网页仍通过 HTTP API 访问 Server。

### 数据库启动 (Docker Compose)

推荐使用 Docker Compose 启动数据库，已配置好 `pgvector` 环境。

1. **配置文件**: 参考[`docker-compose-pg.yml`](../../docker-compose/docker-compose-pg.yml)。

3. **启动命令**:
   ```bash
   docker-compose -f docker-compose-pg.yml up -d
   ```

## 快速开始

### 1. 安装依赖

Python 版本要求: >=3.10 (推荐使用 3.12)

推荐使用 `uv` 包管理器：
```bash
pip install uv
uv sync
```

### 2. 环境变量配置

在 `package/server/data` 目录下创建 `.env` 文件，写入以下配置：

```env
# 主数据库 (根据实际情况修改 host, user, password)
DB_URL=postgresql://msi:msi4090@localhost:5532/trailsnap

# 铁路数据库
RAILWAY_DB_URL=postgresql://msi:msi4090@localhost:5532/railway

# AI 服务地址
AI_API_URL=http://localhost:8001
```

本地无 PostgreSQL 调试时可改为：

```env
# TS_DB_URL 优先于兼容变量 DB_URL
TS_DB_URL=sqlite:///./data/trailsnap.sqlite
# Railway 仍有独立数据库配置
RAILWAY_DB_URL=sqlite:///./data/railway.sqlite
AI_API_URL=http://localhost:8001
```

`start.py` 会根据 URL 方言自动选择迁移：PostgreSQL 使用 `alembic/`，SQLite
使用 `alembic_sqlite/`。更换 URL 后必须重启 Server；这不是运行中热切换。

### 3. 运行服务

建议使用 `start.py` 脚本启动服务，它会自动执行以下操作：
1. 检查数据库连接
2. 自动创建数据库（如果不存在）
3. 启用 pgvector 扩展
4. 执行 Alembic 数据库迁移
5. 初始化 Railway 模块数据库
6. 启动 Uvicorn 服务

```bash
# 启动服务（包含自动初始化和迁移），需要在任务管理器手动关闭进程
python -m uv run start.py
```

如果你是在开发环境中需要热重载，可以手动运行：

```bash
# 确保先运行一次 start.py 完成数据库初始化
python -m uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

启动后访问 Swagger 文档: http://localhost:8000/docs

## 数据库迁移

本项目使用 **Alembic** 进行数据库版本控制。

- **初始化/生成迁移脚本**:
  ```bash
  alembic revision --autogenerate -m "描述"
  ```
- **执行迁移**:
  ```bash
  alembic upgrade head
  ```

SQLite 的迁移说明和命令见 [`alembic_sqlite/README.md`](alembic_sqlite/README.md)。

## 一日一帧影片生成

选帧和日历功能不依赖编码器。生成预览及 MP4 需要 FFmpeg、同目录或 PATH 中的 FFprobe、libx264 编码器和中文字体；Docker 镜像已包含软件编解码版 FFmpeg 与 Noto 简体中文常规字体。

Docker 中的视频尺寸、时长和缩略图由 FFprobe/FFmpeg 读取，不重复安装 OpenCV；原生及桌面环境继续支持 OpenCV。镜像保留常用视频解码器和所需滤镜，省去设备采集、图形播放和 GPU 加速依赖。离线定位种子在镜像中压缩保存，首次启动解压到持久数据目录；用户删除后的行为保持不变。镜像精简的测量口径和验证结果见[优化记录](../../doc/server_image_optimization.md)。

原生部署可以设置 `TS_FFMPEG_PATH` 为 FFmpeg 可执行文件完整路径，设置 `TS_VIDEO_FONT` 为中文 TTF/TTC/OTF 字体文件路径，配置后重启服务。未配置字体时会尝试 Windows 微软雅黑、macOS 苹方和 Linux Noto CJK。缺少依赖时，制作页会显示原因并禁用生成。

生成任务使用持久任务队列；预览和作品文件写入应用数据目录的 `users/<user-id>/daily-frame/`。输出为静音 H.264 MP4、30 fps，每个有效日期一秒；源素材在生成前及发布前都进行权限和可用性检查。

## 目录结构

- `app/`: 应用代码
  - `api/`: 路由接口
  - `core/`: 核心配置
  - `crud/`: 数据库操作
  - `db/`: 数据库模型
  - `schemas/`: Pydantic 验证模型
  - `service/`: 业务服务
- `alembic/`: Alembic 数据库迁移配置
- `railway/`: 铁路数据相关逻辑
- `data/`: 配置文件与数据存储
- `reverse_geocode/`: 逆地理编码服务
