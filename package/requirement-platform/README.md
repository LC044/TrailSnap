# TrailSnap 需求管理平台

这是与 TrailSnap 主应用同仓库、独立部署的需求管理子系统。当前版本覆盖前三阶段：用户提交与查看、人工审核与候选池、版本批次与交付状态管理。AI 仅提供辅助分析，不会自动合并代码或发布版本。

## 已实现范围

- 角色：所有者、管理员、查看者。首个注册账号自动成为所有者；只有所有者可以调整管理员角色。
- 需求：公开或私密提交、搜索、筛选、关注、编辑留痕、撤回、提交频率与未关闭数量限制。
- 分析与审核：持久化后台任务、规则兜底分析、可选 OpenAI 兼容模型分析、人工审核结论和审计日志。
- 版本批次：创建批次、选择候选需求、锁定范围快照、人工维护版本与单项交付状态。
- GitHub：支持 OAuth 登录/账号绑定（不保存用户 OAuth Token）；管理员可新建、关联、解除关联和关闭 Issue；后台写操作支持 PAT 或 GitHub App。
- Agent：提供带独立作用域令牌的 Streamable HTTP MCP 服务，可供 Codex 等 Agent 查询、创建、审核、关闭和软删除需求。
- 独立交付：自己的 Docker Compose 和 GitHub Actions，不触发 TrailSnap 主应用镜像发布。

## 目录

```text
requirement-platform/
├── server/              FastAPI、SQLAlchemy、Alembic、SQLite、后台 worker
├── web/                 Vue 3、TypeScript、Vite、Element Plus
├── docker-compose.yml   API、worker、MCP 和 web 独立编排
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

再启动 MCP 服务：

```powershell
uv run uvicorn requirement_platform.mcp_server:mcp_http_app --port 8012
```

前端：

```powershell
cd package/requirement-platform/web
npm install
npm run dev
```

浏览器访问 `http://localhost:5177`。前端开发服务器会把 `/api` 代理到 `http://127.0.0.1:8010`。

如需本地演示数据（8 个用户、12 条不同状态的需求、1 个版本批次），在启动服务前执行：

```powershell
cd package/requirement-platform/server
uv run python -m requirement_platform.seed_demo
```

该脚本会清空并重写本地 SQLite 中的用户 / 需求 / 版本数据，仅用于开发演示，请勿在生产环境运行。演示账号：`owner@trailsnap.cn`（所有者）、`admin@trailsnap.cn`（管理员），密码均为 `password123`。

## 服务器部署

1. 将 `.env.example` 复制为 `.env`，修改 `RP_JWT_SECRET` 和 `RP_OWNER_EMAIL`。
2. 如果需要 GitHub 同步，优先配置 GitHub App；小规模部署也可设置 `RP_GITHUB_TOKEN`。
3. 执行 `docker compose -f docker-compose.prod.yml up -d`（生产推荐：直接拉取 CI 发布的 GHCR 镜像，无需在服务器上构建；通过 `.env` 中的 `RP_IMAGE_TAG` 固定版本，如 `requirement-v0.1.0`，升级用 `docker compose -f docker-compose.prod.yml pull && docker compose -f docker-compose.prod.yml up -d`）。
   若需要在服务器上从源码构建（本地调试或不便访问 GHCR 时），改用 `docker compose up -d --build`。
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

GitHub App 模式设置 `RP_GITHUB_APP_ID`、`RP_GITHUB_INSTALLATION_ID` 和 `RP_GITHUB_PRIVATE_KEY`。Webhook 地址为 `/api/hooks/github`，签名密钥使用 `RP_GITHUB_WEBHOOK_SECRET`，并订阅 Issues 与 Pull requests 事件。PR 描述使用 `Closes #<Issue 编号>`（也支持 Fixes/Resolves）后，需求详情会展示该 PR，PR 合并时自动关闭对应需求。未配置凭据时，需求与版本管理仍可正常使用；同步任务会保留失败信息供管理员排查。

GitHub 登录需要另外创建 GitHub OAuth App，并将 Authorization callback URL 配置为
`https://feedback.trailsnap.cn/api/auth/github/callback`，然后设置 `RP_GITHUB_OAUTH_CLIENT_ID`、
`RP_GITHUB_OAUTH_CLIENT_SECRET`、`RP_GITHUB_OAUTH_REDIRECT_URI` 和 `RP_WEB_URL`。OAuth 仅申请
`read:user user:email`，平台取回身份后立即丢弃 GitHub Access Token。

## Codex / MCP 接入

管理员在“集成设置”中创建 Agent 令牌并选择最小必要作用域。服务地址默认为
`https://feedback.trailsnap.cn/mcp/`，使用 Streamable HTTP 与 Bearer Token。Codex 配置示例：

```toml
[mcp_servers.trailsnap_requirements]
url = "https://feedback.trailsnap.cn/mcp/"
bearer_token_env_var = "TRAILSNAP_REQUIREMENTS_TOKEN"
```

令牌明文只返回一次，数据库仅保存 SHA-256 摘要；可设置有效期并随时撤销。`requirements:review`
允许关闭和软删除需求，`github:write` 允许变更 GitHub Issue，应只授予受信任的 Agent。

MCP 作用域与能力：

- `requirements:read`：查询需求、附件、历史/编辑/审核记录、分诊报告和后台任务。
- `requirements:write`：创建和完整编辑需求、通过 Base64 上传附件、关注/取消关注及撤回需求。
- `requirements:review`：审核、修改为任一平台已定义状态、标记重复、关闭、软删除和恢复需求。
- `versions:read`：查询版本批次、范围快照、单项交付状态和 GitHub Milestone。
- `versions:write`：创建版本、增删范围条目、锁定范围、流转版本状态及更新交付状态。
- `github:write`：创建、关联、解除关联和关闭 Issue，导入/同步 Issue，以及同步版本 Milestone。

面向公网时，内置 nginx 会限制单 IP 的登录、注册和 API 访问频率，并限制请求体大小；应用层还会限制每个账号每天的提交数和未关闭需求数。API 与 SQLite 均不暴露宿主机端口，公网只应开放 HTTPS 反向代理入口。

## 验证

```powershell
cd package/requirement-platform/server
uv run pytest

cd ../web
npm run build
```

独立工作流位于 `.github/workflows/requirement-platform.yml`。它仅监听此子系统及工作流自身的改动；`requirement-v*` 标签用于发布需求平台镜像，与 TrailSnap 的 `v*` 发布链路分离。
