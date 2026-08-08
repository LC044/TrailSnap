# TrailSnap 开发者文档

本文档旨在为开发者提供 TrailSnap 项目的开发指南，涵盖环境搭建、项目结构、开发流程等内容。

## 目录

1. [项目简介与技术栈](#1-项目简介与技术栈)
2. [开发环境准备](#2-开发环境准备)
3. [项目结构详解](#3-项目结构详解)
4. [后端开发指南](#4-后端开发指南)
5. [前端开发指南](#5-前端开发指南)
6. [AI 服务开发指南](#6-ai-服务开发指南)
7. [数据库迁移](#7-数据库迁移)

---

## 1. 项目简介与技术栈

TrailSnap 是一个前后端分离的项目，集成了 AI 能力。

- **前端**: Vue 3, TypeScript, Vite, Element Plus, TailwindCSS
- **后端**: Python (FastAPI), SQLAlchemy, Alembic
- **数据库**: PostgreSQL (需开启 pgvector 插件以支持向量搜索)
- **AI 服务**: 独立微服务，基于 FastAPI，集成 PaddleOCR, InsightFace, YOLO 等模型。

## 2. 开发环境准备

在开始开发之前，请确保您的机器上安装了以下工具：

- **Git**: 版本控制
- **Python**: 3.10+ (推荐 3.12)
- **Node.js**: v18+ (推荐 v20 或 v22)
- **pnpm**: 前端包管理器 (`npm install -g pnpm`)
- **Docker & Docker Compose**: 用于快速启动数据库

## 3. 项目结构详解

```
TrailSnap/
├── doc/                 # 项目文档
├── package/
│   ├── ai/              # AI 微服务
│   │   ├── app/         # AI 核心逻辑
│   │   └── ...
│   ├── server/          # 后端主服务
│   │   ├── app/         # FastAPI 应用
│   │   │   ├── api/     # 接口路由
│   │   │   ├── core/    # 配置与日志
│   │   │   ├── crud/    # 数据库操作
│   │   │   ├── db/      # 模型定义
│   │   │   ├── schemas/ # Pydantic 模型
│   │   │   └── service/ # 业务逻辑
│   │   └── ...
│   └── website/         # 前端应用
│       ├── src/         # 源代码
│       └── ...
└── ...
```

## 4. 后端开发指南

后端位于 `package/server`。

### 4.1 启动数据库
项目依赖 PostgreSQL 和 pgvector 插件。推荐使用 Docker 启动：由于文档部署限制，请直接查看项目源码中 `package/server/README.md` 文件。

### 4.2 安装依赖
推荐使用 `uv` 进行包管理。

```bash
cd package/server
# 安装 uv
pip install uv
# 使用 uv
uv sync
```

### 4.3 配置文件
在 `package/server/data` 目录下创建 `.env` 文件（参考 README 或直接配置）：
```env
DB_URL=postgresql://user:password@localhost:5432/trailsnap
RAILWAY_DB_URL=postgresql://user:password@localhost:5432/railway
AI_URL=http://localhost:8001
```

### 4.4 运行服务
```bash
# 第一次运行、或数据库结构发生变化时需要初始化数据库
uv run python start.py

# 数据库结构初始化完成后，启动服务
uv run uvicorn main:app --reload --port 8000
```
API 文档地址：`http://localhost:8000/docs`

## 5. 前端开发指南

前端位于 `package/website`。

### 5.1 安装依赖
```bash
cd package/website
pnpm install
```

### 5.2 运行开发服务器
```bash
pnpm dev
```
访问地址：`http://localhost:5176`

### 5.3 构建
```bash
pnpm build
```

## 6. AI 服务开发指南

AI 服务位于 `package/ai`，为后端提供 OCR 和人脸识别能力。

### 6.1 安装依赖
```bash
cd package/ai

pip install uv

# 安装依赖（CPU版本）
uv sync --extra cpu

# 安装依赖（GPU版本）
uv sync --extra gpu
```

### 6.2 运行服务
```bash
uv run uvicorn app.main:app --reload --port 8001
```

## 7. 数据库迁移

后端使用 Alembic 管理数据库迁移。

**注意**：修改 `db/models` 下的模型后，必须执行迁移才能生效。

1. **生成迁移脚本**
   ```bash
   cd package/server
   alembic revision --autogenerate -m "描述修改内容"
   ```

2. **执行迁移**
   ```bash
   alembic upgrade head
   ```

3. **常用命令**
   - `alembic current`: 查看当前版本
   - `alembic history`: 查看历史版本
   - `alembic downgrade -1`: 回滚上一个版本

## 8. 打包docker镜像

```bash
cd TrailSnap
# 一键打包docker镜像
docker-compose up -d --build
```

```bash
# 打包前端镜像
docker build -t crpi-d7wuvvdylhqugyu2.cn-hangzhou.personal.cr.aliyuncs.com/siyuan044/trailsnap-frontend:master -f package/website/Dockerfile .

# 打包后端镜像
docker build -t crpi-d7wuvvdylhqugyu2.cn-hangzhou.personal.cr.aliyuncs.com/siyuan044/trailsnap-backend:master -f package/server/Dockerfile .

# 打包AI镜像
docker build -t crpi-d7wuvvdylhqugyu2.cn-hangzhou.personal.cr.aliyuncs.com/siyuan044/trailsnap-ai:master -f package/ai/Dockerfile .
```
