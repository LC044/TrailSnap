# TrailSnap 需求管理平台

这是与 TrailSnap 主应用同仓库、独立部署的需求管理子系统。当前版本覆盖用户提交与查看、规格闭环、人工审核、版本批次，以及手动 Agent 交付协议。平台不会启动 Agent、自动合并代码或发布版本。

## 已实现范围

- 角色：所有者、管理员、查看者。首个注册账号自动成为所有者；只有所有者可以调整管理员角色。
- 需求：公开或私密提交、搜索、筛选、关注、编辑留痕、撤回、提交频率与未关闭数量限制。
- 分析与审核：严格的 Triage V2、结构化追问、用户摘要纠正、修订守卫、规则兜底和可选 OpenAI 兼容模型。
- 规格：不可变规格修订、编号化验收标准、GitHub `master` 基线冻结和 Context Bundle。
- 版本批次：创建批次、选择候选需求、锁定范围快照、人工维护版本与单项交付状态。
- GitHub：支持 OAuth 登录/账号绑定（不保存用户 OAuth Token）；管理员可新建、关联、解除关联和关闭 Issue；后台写操作支持 PAT 或 GitHub App。
- Agent：手动启动的 Codex/Claude 可通过 REST 或 Streamable HTTP MCP 原子领取任务、续租、提交实现计划、提问、登记证据、上报结果并关联 PR。
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

SQLite 文件保存在 Docker 卷 `requirement-data`。备份时先暂停 API、worker 和 MCP，或使用 SQLite 在线备份命令生成一致性副本；不要在写入期间直接复制数据库文件。当前实现只支持 SQLite；任务领取使用条件更新保证单实例内不会被重复领取。

## AI 模型设置

管理员登录后可在“AI 设置”中添加多个 OpenAI-Compatible 连接和模型，并分别为“提交前分析”“需求分诊”等任务保存有序模型路由。路由中的第一个模型为主模型，其余模型在连接失败、超时、响应解析失败或结构校验失败时按顺序尝试；全部失败后使用确定性规则分诊。连接测试不会把 API Key 返回给浏览器。

API Key 使用由 `RP_JWT_SECRET` 派生的 Fernet 密钥加密后存入 SQLite，接口只显示末四位提示。因此生产环境必须使用稳定且妥善备份的 `RP_JWT_SECRET`；更换该值后需要重新录入已有连接的 API Key。连接地址应包含 API 版本前缀，例如 `https://api.example.com/v1`。

原有的 `RP_AI_API_URL`、`RP_AI_API_KEY`、`RP_AI_MODEL` 仍作为兼容配置：当“提交前分析”或“需求分诊”尚未保存页面路由时使用；一旦保存路由，即以数据库配置为准。禁用某个任务路由会明确关闭该任务的 AI，不会回退到环境变量。

## GitHub 集成

PAT 模式只需设置：

```dotenv
RP_GITHUB_REPO=LC044/TrailSnap
RP_GITHUB_TOKEN=github_pat_xxx
```

GitHub App 模式设置 `RP_GITHUB_APP_ID`、`RP_GITHUB_INSTALLATION_ID` 和 `RP_GITHUB_PRIVATE_KEY`。Webhook 地址为 `/api/hooks/github`，签名密钥使用 `RP_GITHUB_WEBHOOK_SECRET`，并订阅 Issues 与 Pull requests 事件。PR 描述使用 `Closes #<Issue 编号>`（也支持 Fixes/Resolves）后，需求详情会展示该 PR。Issue 的关闭、重开或标签变化只记录为外部事实，不直接改变平台审核状态；交付任务关联的 PR 合并后显示“已合并待发布”，不会冒充已发布。未配置凭据时，规格批准无法自动冻结基线；Owner 可填写完整 SHA 作为受审计兜底。

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
- `requirements:review`：审核、维护兼容需求状态、标记重复、行政关闭、软删除和恢复；存在新交付任务时不能绕过规格和执行门禁推进交付状态。
- `versions:read`：查询版本批次、范围快照、单项交付状态和 GitHub Milestone。
- `versions:write`：创建版本、增删范围条目、锁定范围、流转版本状态及更新交付状态。
- `github:write`：创建、关联、解除关联和关闭 Issue，导入/同步 Issue，以及同步版本 Milestone。
- `specs:read`：读取批准规格。
- `tasks:write`：受信任管理客户端创建交付任务、取消执行。
- `tasks:claim`：编码 Agent 原子领取任务。
- `runs:write`：心跳续租、提交 ImplementationPlan、申请澄清、上报结果和关联 PR。
- `artifacts:write`：登记日志、截图、测试报告等产物元数据与 SHA-256。

### 手动 Agent 工作流

1. 管理员在需求详情创建规格草稿，补齐 AC 和阻塞问题后批准；平台从 `LC044/TrailSnap` 的 `master` 自动解析并冻结 SHA。
2. 管理员创建交付任务，并创建限制为 `coding`（建议再限制到具体 task ID）的 Agent Token。
3. 本地 Codex/Claude 调用 `claim_delivery_task`，保存返回的 `run_id`、`attempt_id`、`lease_token` 和 `state_version`。
4. Agent 复用同一个 `idempotency_key` 重试同一次写入，并通过 `heartbeat_run` 维持默认 90 秒租约。
5. 编码前调用 `submit_implementation_plan`，其中 `acceptance_plan` 必须覆盖全部必需 AC；发现产品歧义时调用 `request_clarification`。
6. 完成后登记必要证据并调用 `submit_run_result`；创建 PR 后调用 `link_pull_request`，平台会回查仓库、目标分支以及 head/base SHA。

新的逻辑动作必须使用新的幂等键；过期 attempt 或 lease 的写入会被拒绝。产物内容应存放在受 ACL 保护的位置，平台数据库只保存元数据和 hash。

面向公网时，内置 nginx 会限制单 IP 的登录、注册和 API 访问频率，并限制请求体大小；应用层还会限制每个账号每天的提交数和未关闭需求数。API 与 SQLite 均不暴露宿主机端口，公网只应开放 HTTPS 反向代理入口。

## 验证

```powershell
cd package/requirement-platform/server
uv run pytest

cd ../web
npm run build
```

独立工作流位于 `.github/workflows/requirement-platform.yml`。它仅监听此子系统及工作流自身的改动；`requirement-v*` 标签用于发布需求平台镜像，与 TrailSnap 的 `v*` 发布链路分离。
