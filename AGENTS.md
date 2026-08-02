# CLAUDE.md

本文件为 Claude Code（claude.ai/code）在本仓库下工作时提供指引。

## 项目概览

TrailSnap（行影集）是一个由 AI 驱动、可自托管的相册应用。`package/` 目录下共包含五个子包：

- **`website/`** —— 前端单页应用（Vue 3 + TypeScript + Vite + Element Plus + Pinia），开发端口 **5176**。
- **`server/`** —— 主后端（FastAPI + SQLAlchemy + Alembic），端口 **8000**。负责数据库、业务逻辑和异步任务流水线。
- **`ai/`** —— GPU 可选的 AI 微服务（FastAPI + PaddleOCR / InsightFace / RapidOCR / CLIP），端口 **8001**。主后端通过 `AI_API_URL` 以 HTTP 方式调用。
- **`official-site/`** —— VitePress 文档站（中文 + 英文，分别在 `docs/` 和 `en/`）。
- **`trailsnap-cli/`** —— 发布到 npm 的 Node CLI，包名为 `trailsnap-cli`。供 AI 代理查询照片 / 相册 / 标签 / 位置 / 人物数据。

仓库根目录下的其他顶层目录与文件：`skills/`、`doc/`（架构与开发文档，中文）、`docker-compose.yml`（全栈部署）、`.github/workflows/`（各组件的 Docker 构建与推送）。

## 开发命令

### 前端（`package/website`）
```bash
pnpm install
pnpm dev        # http://localhost:5176（将 /api 代理到 127.0.0.1:8000）
pnpm build      # 产物输出到 dist/
pnpm preview
pnpm test:e2e           # Playwright 无头模式
pnpm test:e2e:ui        # Playwright UI 模式
pnpm test:e2e:headed    # Playwright 有头模式（带浏览器界面）
```
E2E 测试位于 `package/website/tests/e2e/`。开发服务器会把 `/api/*` 代理到后端（见 `vite.config.js`），因此前端可以直接对接本地运行的后端进行开发。

### 后端（`package/server`）
```bash
python start.py                  # 自动初始化数据库 + 执行迁移 + 在 :8000 启动
uvicorn main:app --host 0.0.0.0 --port 8000 --reload   # 带热重载的开发模式
```
`start.py` 的执行流程为：连接 Postgres → 如不存在则创建数据库 → 启用 `vector` 扩展 → 执行 `alembic upgrade head` → 导入 5A 景区 CSV → 通过 `os.execvp` 切换到 uvicorn。

**运行单个测试：**
```bash
cd package/server
python -m pytest tests/test_api_integration.py -v
# 或针对 unittest 风格的文件：
python -m unittest tests.test_api_integration -v
```

### AI 服务（`package/ai`）
```bash
uv sync --extra cpu        # 仅 CPU
uv sync --extra gpu        # GPU（CUDA 12.8）
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```
在非 Windows 平台上，AI 服务会运行一个空闲检测任务，在 `IDLE_TIMEOUT`（默认 600 秒）后调用 `sys.exit(0)`，由容器编排器重启并释放内存。LLM 通过 `app/services/llm_manager.py` 以子进程方式管理（端口 8002，默认 5 分钟空闲）。

### 测试

CI 与本地共用**同一个入口** `tests/scripts/run-tests.ps1`（PowerShell）。完整约定见 [`tests/README.md`](tests/README.md)。

```powershell
.\tests\scripts\run-tests.ps1 -Layer unit -Level smoke            # 后端 + AI 单元（秒级，无需启动服务）
.\tests\scripts\run-tests.ps1 -Layer e2e -Level p0                # 前端 e2e p0（本地 dev 进程）
.\tests\scripts\run-tests.ps1 -Layer e2e -Level p0 -Mode docker   # 启动 compose 栈跑（与 CI 路径一致）
.\tests\scripts\run-tests.ps1 -StopServices                       # 按端口清理服务
```

- `-Layer` 取 unit/integration/e2e/all；`-Level` 取 dev/scan/smoke/p0/p1/all/light/full（既是 e2e 套件名，也是 unit 的 `-m` 映射）；`-Mode` 取 dev/docker。
- 服务生命周期由 `services-up.ps1` / `services-down.ps1` 负责（dev 模式起本地 uv/pnpm 进程，docker 模式起 `tests/docker/docker-compose.yml`）；`run-tests.ps1` 在 e2e/integration 层会自动调用它们。
- 环境变量的唯一来源是 `tests/.env.test`（模板为 `tests/.env.test.example`，CI 用 `tests/.env.test.ci`）。
- CI 配置在 `.github/workflows/tests.yml`：cli/server/ai 单元 + server 集成 + e2e（`-Mode docker`）。

## 架构

### 多进程后端（`package/server`）

FastAPI 服务**并不是**单进程。`app/main.py` 的 lifespan 会通过 `app/service/task_manager.py` → `app/worker.py` → `app/service/task_worker.py` 启动（并在退出时停止）一个独立的 worker 进程。这种拆分非常关键：

- **API 进程**（`main:app`，端口 :8000）—— 处理 HTTP 请求，创建 `Task` 记录，暴露 `/tasks/*` 状态接口，并通过 `SystemState` 暂停/恢复。
- **Worker 进程**（`app.worker.run_worker`）—— 领取待处理任务并执行，更新记录。拥有独立的事件循环；崩溃时由 API 进程负责重启。

任务按 `TaskType` 分类组织，注册到 `app/service/tasks/` 下的处理函数（每个任务类别对应一个模块：`face.py`、`ocr.py`、`tickets.py`、`metadata.py`、`classification.py`、`image_embedding.py`、`thumbnail.py`、`scan.py`、`organize.py`、`rename.py`、`time_from_filename.py`、`similar.py`、`duplicate.py`、`album.py`）。

### 后端分层（`package/server/app/`）

- **`api/`** —— 轻量级的 FastAPI 路由，每个领域一个文件（`photo`、`album`、`face`、`ocr`、`agent`、`auth`、`toolbox`、`search`、`train_ticket`、`flight_ticket`、`annual_report`、`tasks`、`system`、`media`、`metadata`、`index`、`deps`、`login`、`classification`、`stats`、`settings`、`user`、`agent_token`）。所有路由都在 `main.py` 中以显式的 prefix/tag 挂载。
- **`schemas/`** —— Pydantic 的请求/响应模型。**所有 API 响应统一用 `BaseResponse` 包装**（见 `app/schemas/response.py`）；处理函数返回 `BaseResponse.success(data=...)` 或 `BaseResponse.fail(...)`。
- **`crud/`** —— SQLAlchemy 的 CRUD 辅助，每个聚合根一个模块。
- **`db/models/`** —— ORM 模型。每次修改后都需要用 Alembic 生成迁移。
- **`service/`** —— 跨领域业务逻辑：`storage.py`（文件 IO）、`indexer.py`、`similar_photo.py`、`face_cluster.py`，以及上文提到的任务子系统。
- **`service/agent/`** —— 基于 LangChain + LangGraph 的 Agent（详见下文 “AI Agent”）。
- **`service/live_photo/`** —— 各厂商的实况照片解析器（`apple.py`、`android.py`、`vivo.py`）。
- **`core/`** —— 配置、按天滚动的 JSON 队列日志、系统配置。
- **`railway/`** —— 独立的子应用，自带 `api.py`、`crud.py`、`schemas.py`、`db/` 和 `build_database.py`。在 `main.py` 中挂载到 `/railway`，负责火车时刻表/票务数据，与主应用在功能上相互独立。
- **`utils/`** —— EXIF 解析、文件名工具。

要求：后端所有新增 API 都统一采用 `BaseResponse` 格式。

```json
{
  code: 0,
  msg: "success",
  data: {}
}
```

### AI 微服务（`package/ai/app/`）

- **`routers/`** —— `face`、`ocr`、`object_detection`、`tickets`、`image_classification`、`embedding`、`llm`（OpenAI 兼容的 `/v1/...`）、`ai_config`、`system`。
- **`services/`** —— 懒加载的模型包装器（`face_service.py`、`ocr_service.py`、`image_classification_service.py`、`embedding_service.py`、`ticket_service.py`、`fly_ticket_parser.py`、`ticket_parser.py`）。`model_manager.py` 负责资源释放；`model_downloader.py` 在启动时预下载权重；`llm_manager.py` 运行 LLM 服务子进程并在空闲时销毁。
- **`core/logger.py`** —— 与后端相同的 JSON 队列日志。

### AI Agent（LangChain / LangGraph）

`package/server/app/service/agent/service.py` 是基于 LangGraph 的 LangChain Agent。Agent 通过 `app/api/agent.py`（挂载在 `/agent`）对外暴露，并通过 `app/api/agent_token.py`（挂载在 `/tokens`）鉴权——**Agent Token 与用户 JWT 是分离的**，因此可以为 AI 客户端授予受限范围访问，而无需用户账号。

`service/agent/tools.py` 定义了 Agent 可调用的工具（photo/album/search/stats/face 等）。流式响应以 SSE 返回；客户端 UI 位于 `package/website/src/views/agent/AgentChat.vue`。

### 前端结构（`package/website/src/`）

- **`api/`** —— Axios 客户端，每个后端领域一个。`config.ts` 定义多套 API 配置（主应用使用 Vite 的 `/api` 代理，但 `railway` / `user` / `payment` 等 key 可以指向其他服务）。
- **`router/index.ts`** —— 集中式路由表。路由通过 `meta.layout`（`'main' | 'blank'`）声明布局，`App.vue` 据此在 `MainLayout.vue` 与空白布局间切换。年度报告页与登录页使用空白布局。
- **`stores/`** —— Pinia store（`photoStore`、`albumStore`、`ticketStore`、`locationStore`、`user`、`selectionStore`）。
- **`components/`** —— 体量较大的功能组件：`PhotoGallery`、`PhotoLightbox`、`FlatPhotoGallery`、`UnifiedPhotoPage`、`TrainTicket`、`TicketFormModal`、`OnThisDay`、`MultiFileUpload`、`AlbumTimeline`、`PersonAvatar`、`FolderSelectionDialog`。多数组件都是有状态的，并与具体视图绑定。
- **`views/`** —— 页面级组件，按特性目录组织（`album/`、`ticket/`、`toolbox/`、`search/`、`agent/`、`annual-report/`、`login/`、`settings/`）。Toolbox 页面是完整的照片管理工具（重命名、整理、去重、相似照片、按文件名推断时间、清理等）。
- **`layouts/`** —— `MainLayout.vue`（侧边栏 + 内容区）。
- **`composables/`**、**`utils/`**、**`types/`** —— 共享的 TypeScript 工具。
- **`assets/`** —— `main.css` 中的 Tailwind 基础样式；全局 `style.css` 注册 Mingcute 图标。

开发服务器（`vite.config.js`）监听 `0.0.0.0:5176`，并将 `/api` 代理到 `http://127.0.0.1:8000/`。`@` 别名指向 `src/`。

### CLI 与 Skills

- **`package/trailsnap-cli/`** —— Node CLI（`bin/`）。通过 `pnpm build` 构建；GitHub workflow `build-publish-cli.yml` 会发布到 npm。允许外部 AI 代理在无浏览器的场景下查询 TrailSnap 数据。
- **`skills/trailsnap-cli/`** —— 为 Claude Code / OpenClaw 打包的 skill，使代理可以直接在提示词中调用 CLI。

### Docker 部署

仓库根目录的 `docker-compose.yml` 启动 `postgres`（带 pgvector）、`server`、`ai` 和 `frontend`（nginx 提供 Vite 打包产物）。需要将宿主机上的照片目录挂载到 `server` 容器（见 `README.md` 中的 `F:\Photos:/app/Photos/`）。每个组件在自己的子目录里都有独立的 `Dockerfile`；AI 服务同时提供 `Dockerfile`（CPU）、`Dockerfile.gpu` 和 `Dockerfile.openvino`。`.github/workflows/` 下的 GitHub workflow 会在 tag 推送或提交信息包含 `-latest` / “构建后端” 时构建并推送镜像到 Docker Hub。

## 约定

- **API 响应**：每个接口都返回 `BaseResponse[T]`（`{code, message, data, ...}`）。新增接口必须遵循该模式。
- **前端**：组件使用 `<script setup lang="ts">`；状态放到 Pinia store；HTTP 请求统一走 `src/api/*` 模块。
  - **主题色**：凡是希望跟随用户所选主题色的元素，都应使用 `src/style.css` 中定义的 `primary-*` 工具类（`bg-primary-{500,600}`、`text-primary-{500,600}`、`border-primary-500`、`hover:bg-primary-{500,600,700}`、`shadow-primary-500{,\/20,\/30,\/40}`、`ring-primary-500` 等）——它们映射到 `var(--theme-primary)` / `var(--theme-rgb)`，`src/composables/useTheme.ts` 中的 5 套主题（sky / emerald / violet / rose / amber）会自动切换。**绝不要**为强调元素硬编码 Tailwind 的品牌色（`blue-500/600/700`、`purple-500`、`emerald-500` 等），那不会跟随主题。在无法使用工具类的场景（天地图、ECharts、动态样式）中，调用 `@/composables/useTheme` 暴露的 `injectTheme()` 并读取 `currentTheme.value.primary`（十六进制字符串）/ `currentTheme.value.rgb`（用于 `rgba()`）。主题切换后，需要重新执行命令式的绘制代码（例如 `map.drawTrajectory()`）——工具类会自动响应，但 JS 驱动的可视化不会。
  - **暗色模式**：每一个 `text-gray-*` 和 `bg-white` 都必须搭配对应的 `dark:` 变体。常用的 `text-gray-500 dark:text-gray-400` 和 `text-gray-400 dark:text-gray-500` 已经覆盖了大多数情况，直接复用即可。Element Plus 组件（`el-dialog`、`el-select`、`el-slider`、`el-dropdown`、`el-message-box` 等）通过 `html.dark` + `--el-bg-color: #111827`（在 `src/style.css` 第 18 行设置）继承暗色模式，不要在每个实例里覆盖其内部颜色。
  - **焦点环**：交互元素（按钮、链接、可点击的卡片、自定义下拉项）必须包含 `focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none` 以保证键盘可访问性。焦点环颜色已经在 `style.css` 中映射到 `var(--theme-primary)`，无需额外工作即可跟随主题。
  - 所有组件都应考虑PC和移动端两种布局，确保在两种环境下都能正常显示。
  - **同一组件只用一个灰色族**：统一使用 `gray-*`（或 `slate-*`）——不要在同一个界面里混用。`MainLayout.vue` 把外层 `bg-slate-50 dark:bg-slate-900` 与内部内容 `dark:bg-gray-900` 混用，导致暗色模式下出现可见的接缝。请在同一个布局的根容器、主内容区、弹窗中选定一族并保持一致。
- **迁移**：在 `app/db/models/` 修改 ORM 模型后，执行 `alembic revision --autogenerate` 并提交生成的文件。删除模型字段时一定要配套迁移步骤。
- **提交信息**：遵循 Conventional Commits 规范（`feat(scope):`、`fix(scope):`、`refactor(scope):`）。提交信息中包含特定关键字会触发 GitHub Actions CI 流水线——**只有在确实希望构建并推送 Docker 镜像或发布包时才包含这些关键字**，因为它们会消耗 CI 资源并向 Docker Hub / npm / GitHub Releases 推送：
  - `构建后端` —— 触发 **Server** Docker 构建与推送（`.github/workflows/docker-build-push-server.yml`），仅当 `package/server/` 下的文件发生变化时生效。
  - `构建前端` —— 触发 **Frontend** Docker 构建与推送（`.github/workflows/docker-build-push-frontend.yml`），仅当 `package/website/` 下的文件发生变化时生效。
  - `构建ai` —— 触发 **AI 服务** Docker 构建与推送（`.github/workflows/docker-build-push-ai.yml`），仅当 `package/ai/` 下的文件发生变化时生效。
  - `构建cli` —— 触发 **CLI** 二进制构建并将产物保留在 Actions Artifacts（`.github/workflows/build-publish-cli.yml`），仅当 `package/trailsnap-cli/` 下的文件发生变化时生效；只有推送 `v*.*.*` 标签才会创建 Release 并发布 npm/PyPI。
  - **原则**：只有用户明确要求时才加上。
- **PR 模板**：见 `.github/pull_request_template.md`。在 PR 评论中需要确认 CLA（“I have read and agree to the CLA”，基于 AGPLv3）。
- **push规则**：
  - **必须**：提交之前必须在本地运行测试（.\tests\scripts\run-tests.ps1 -Layer e2e -Level full），确保所有测试通过。
  - **建议**：推荐新开一个分支推送的时候通过 PR 合并到主分支，确保PR通过了所有 CI 流水线测试（大概二十分钟），等到 PR 合并后再删除分支。

## 关键文件

- `package/server/main.py` —— 后端入口；lifespan、中间件、路由挂载。
- `package/server/start.py` —— 数据库初始化 + 迁移 + uvicorn exec。
- `package/server/app/worker.py` + `app/service/task_manager.py` + `app/service/task_worker.py` —— 异步任务流水线。
- `package/server/app/service/agent/service.py` —— LangChain Agent 入口。
- `package/ai/main.py` —— AI 服务入口，空闲重启，LLM 子进程生命周期。
- `package/website/vite.config.js` —— 端口与 `/api` 代理。
- `package/website/src/router/index.ts` —— 所有路由与布局提示。
- `docker-compose.yml` —— 全栈部署。
- `CONTRIBUTING.md` —— 开发环境、提交规范、PR 模板、CLA。
- `doc/architecture_design.md` —— 架构概览（中文，含架构图）。
