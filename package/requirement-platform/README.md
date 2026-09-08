# TrailSnap 需求管理平台

这是与 TrailSnap 主应用同仓库、独立部署的需求管理子系统。当前版本覆盖前三阶段：用户提交与查看、人工审核与候选池、版本批次与交付状态管理。AI 仅提供辅助分析，不会自动合并代码或发布版本。

## 已实现范围

- 角色：所有者、管理员、查看者。首个注册账号自动成为所有者；只有所有者可以调整管理员角色。
- 需求：公开或私密提交、搜索、筛选、关注、编辑留痕、撤回、提交频率与未关闭数量限制。
- 分析与审核：持久化后台任务、规则兜底分析、可选 OpenAI 兼容模型分析、人工审核结论和审计日志。
- 版本批次：创建批次、选择候选需求、锁定范围快照、人工维护版本与单项交付状态。
- GitHub：审核进入候选池后异步同步 Issue，锁定版本后异步同步 Milestone；支持 PAT 或 GitHub App。
- 独立交付：自己的 Docker Compose 和 GitHub Actions，不触发 TrailSnap 主应用镜像发布。

## 目录

```text
requirement-platform/
├── server/              FastAPI、SQLAlchemy、Alembic、SQLite、后台 worker
├── web/                 Vue 3、TypeScript、Vite、Element Plus
├── docker-compose.yml   API、worker 和 web 独立编排
└── .env.example         生产环境变量模板
```

## 本地开发

后端：

```powershell
cd package/requirement-platform/server
uv sync
uv run alembic upgrade head
uv run uvicorn requirement_platform.main:app --reload --port 8010
```

另开终端启动任务 worker：

```powershell
cd package/requirement-platform/server
uv run python -m requirement_platform.worker
```

前端：

```powershell
cd package/requirement-platform/web
npm install
npm run dev
```

浏览器访问 `http://localhost:5177`。前端开发服务器会把 `/api` 代理到 `http://127.0.0.1:8010`。

## 服务器部署

1. 将 `.env.example` 复制为 `.env`，修改 `RP_JWT_SECRET` 和 `RP_OWNER_EMAIL`。
2. 如果需要 GitHub 同步，优先配置 GitHub App；小规模部署也可设置 `RP_GITHUB_TOKEN`。
3. 执行 `docker compose up -d --build`。
4. 在宿主机反向代理中把 `feedback.trailsnap.cn` 转发到 `127.0.0.1:8011`，并启用 HTTPS。
5. 使用 `RP_OWNER_EMAIL` 对应邮箱注册首个账号，该账号会成为唯一所有者；随后再开放域名供其他用户注册。
6. 在主 TrailSnap 前端构建时设置 `VITE_REQUIREMENT_PLATFORM_URL=https://feedback.trailsnap.cn`。

SQLite 文件保存在 Docker 卷 `requirement-data`。备份时先暂停 API 和 worker，或使用 SQLite 在线备份命令生成一致性副本；不要只在高并发写入时直接复制数据库文件。

## GitHub 集成

PAT 模式只需设置：

```dotenv
RP_GITHUB_REPO=LC044/TrailSnap
RP_GITHUB_TOKEN=github_pat_xxx
```

GitHub App 模式设置 `RP_GITHUB_APP_ID`、`RP_GITHUB_INSTALLATION_ID` 和 `RP_GITHUB_PRIVATE_KEY`。Webhook 地址为 `/api/hooks/github`，签名密钥使用 `RP_GITHUB_WEBHOOK_SECRET`。未配置凭据时，需求与版本管理仍可正常使用；同步任务会保留失败信息供管理员排查。

面向公网时，内置 nginx 会限制单 IP 的登录、注册和 API 访问频率，并限制请求体大小；应用层还会限制每个账号每天的提交数和未关闭需求数。API 与 SQLite 均不暴露宿主机端口，公网只应开放 HTTPS 反向代理入口。

## 验证

```powershell
cd package/requirement-platform/server
uv run pytest

cd ../web
npm run build
```

独立工作流位于 `.github/workflows/requirement-platform.yml`。它仅监听此子系统及工作流自身的改动；`requirement-v*` 标签用于发布需求平台镜像，与 TrailSnap 的 `v*` 发布链路分离。
