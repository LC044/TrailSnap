# TrailSnap 需求管理平台

这是与 TrailSnap 主应用同仓库、独立部署的需求管理子系统。当前版本覆盖用户提交与查看、规格闭环、管理员或受信任 Agent 审核、版本批次，以及 Agent 编码交付协议。已启动的 Agent 可通过 MCP 完成从提交需求到上报实现结果的全流程；平台不负责启动 Agent 进程、自动合并代码或发布版本。

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

### 代码分层

后端以传输适配器、领域用例和外部集成为边界：

- `api/` 只处理 HTTP 协议和统一响应；认证、AI 设置、需求、GitHub、版本、管理员和用量接口各自注册 Router，`main.py` 负责应用装配与尚在迁移的交付路由。
- `domain/` 保存 REST 与 MCP 共用的需求、版本和交付规则。领域函数不提交事务，由 REST、MCP 或 worker 在用例完成后统一提交。
- `integrations/` 保存 GitHub 等外部系统的映射与协议规则。
- `presenters.py` 负责读模型组装；列表查询通过批量上下文预取公共关联数据。
- `usage.py` 是独立的 FastAPI Router，同时封装用量导入和统计查询。

前端使用 Vue Router 管理 URL、Pinia 管理登录态，并按 `views/`、`layouts/`、`stores/`、`composables/`、`api/` 分层。`App.vue` 只保留仍在逐步迁移的提交表单与跨页面弹窗协调；`TokenUsage.vue` 只协调筛选、总览和数据加载，趋势/分布图与导入管理位于 `components/usage/`。新增页面不得再直接堆入 `App.vue`。

## 本地开发

### AI 反馈后的持续跟进

- 匿名提交成功后显示结果卡，提供查看进度、保存修改入口和继续交给 AI 的操作。
- “本机提交记录”保存在当前浏览器。换设备或清除浏览器数据前应私下保存修改入口；持有链接的人具有对应需求的修改权限。
- 详情中的“补充信息”保存为独立记录。正文进入开发后仍可补充，补充不会自动改动已批准正文、规格或交付授权。
- `GET /api/requirements/{id}/supplements` 读取补充；`POST` 接受 `{ "body": "4–4000 字说明" }`，仅提交者、管理员或对应编辑凭证可追加。公开需求的补充公开，私有需求沿用原读取权限；每条需求每小时最多 10 条、累计最多 100 条。
- “复制给 AI 继续处理”仅包含公开需求链接和操作说明，不携带编辑凭证、联系方式或私密日志。
- 本次新增表与匿名编辑字段合并在尚未发布的 `c8d4a7e2f610` 迁移中，部署时需要升级数据库。

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

GitHub App 模式设置 `RP_GITHUB_APP_ID`、`RP_GITHUB_INSTALLATION_ID` 和 `RP_GITHUB_PRIVATE_KEY`。Webhook 地址为 `/api/hooks/github`，签名密钥使用 `RP_GITHUB_WEBHOOK_SECRET`，并订阅 Issues 与 Pull requests 事件。PR 描述使用 `Closes #<Issue 编号>`（也支持 Fixes/Resolves）后，需求详情会展示该 PR。Issue 的关闭、重开或唯一状态标签会通过手动同步或 Webhook 映射回平台状态并写入时间线；交付任务关联的 PR 合并后仍只显示“已合并待发布”，不会冒充已发布。未配置凭据时，规格批准无法自动冻结基线；Owner 可填写完整 SHA 作为受审计兜底。

GitHub 登录需要另外创建 GitHub OAuth App，并将 Authorization callback URL 配置为
`https://feedback.trailsnap.cn/api/auth/github/callback`，然后设置 `RP_GITHUB_OAUTH_CLIENT_ID`、
`RP_GITHUB_OAUTH_CLIENT_SECRET`、`RP_GITHUB_OAUTH_REDIRECT_URI` 和 `RP_WEB_URL`。OAuth 仅申请
`read:user user:email`，平台取回身份后立即丢弃 GitHub Access Token。

## Codex / MCP 接入

### 普通用户 AI 反馈

普通用户无需登录或配置 MCP。AI 可读取公开 `/api/agent-guide`，通过 HTTP 搜索和匿名提交需求。
提交返回独立 `edit_token`，只允许修改对应需求的内容，不授予审核、状态或任务管理权限。
网页自动保存本机回执，AI 提供的 `#edit_token=...` 私有管理链接打开后也会自动导入；
公开分享只使用不含凭证的详情链接。丢失回执不能仅凭昵称或 IP 恢复。

创建可携带 CSPRNG 生成的 32 字节 base64url `client_edit_token`，相同凭证和相同请求重试不会重复创建。
后续 `PATCH /api/requirements/{id}` 使用 `X-Requirement-Edit-Token` 请求头和
`expected_state_version`；版本冲突返回 409，编辑仅限提交、待补充与待审核阶段。
旧 `upload_token` 不升级为编辑权限。部署前由维护者执行新增 SQLite 迁移，
应用的 `create_all` 不会为已有数据库补齐字段。

下述 MCP 接入与交付协议仅适用于受信任管理员 Agent，不适用于普通匿名贡献者。

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
- `requirements:review`：审核、批准规格、答复执行澄清、维护兼容需求状态、标记重复、行政关闭、软删除和恢复；存在新交付任务时不能绕过规格和执行门禁推进交付状态。
- `versions:read`：查询版本批次、范围快照、单项交付状态和 GitHub Milestone。
- `versions:write`：创建版本、增删范围条目、锁定范围、流转版本状态及更新交付状态。
- `github:write`：创建、关联、解除关联和关闭 Issue，导入/同步 Issue，以及同步版本 Milestone。
- `specs:read`：读取批准规格。
- `tasks:write` / `tasks:claim`：保留的 scope 名称；当前创建、领取和取消任务仅检查有效管理员所属令牌，领取仍检查角色与任务绑定，不要求这些 scope。
- `runs:write`：心跳续租、提交 ImplementationPlan、申请澄清、上报结果和关联 PR。
- `artifacts:write`：登记日志、截图、测试报告等产物元数据与 SHA-256。

### Agent 自动化工作流

1. Agent 使用现有令牌调用 `get_agent_capabilities` 检查权限，再查询/创建需求。无需新增 scope 或调整已有令牌。完整流程使用已有 `requirements:read`、`requirements:write`、`requirements:review` 和 `runs:write` 权限；权限不足会明确返回缺失项，不自动提权。
2. 调用 `list_requirement_specs` 查询修订，由 Agent 根据需求编写结构化规格和编号 AC，通过 `create_requirement_spec` / `update_requirement_spec` 保存。创建使用需求的 `expected_requirement_state_version`；编辑使用规格的 `expected_state_version`。两者沿用 `requirements:write`。
3. 有 `requirements:review` 的 Agent 调用 `approve_requirement_spec`，不需要人工打开页面；平台从 `LC044/TrailSnap` 的 `master` 解析并冻结 SHA。阻塞问题必须先解决；手工 SHA 兜底仍仅允许 Owner。
4. 调用 `start_requirement_delivery`，传入需求编号、runner/provider 和实现计划。该工具要求 `runs:write`，在一个事务中创建/复用任务、指定领取并提交计划，失败全部回滚。`acceptance_plan` 形如 `{"AC-01": "实现筛选切换清理，并验证选择归零"}`，必须覆盖全部必需 AC，不允许空白内容和未知编号。
5. 保存返回的 `id`（run_id）、`attempt_id`、`lease_token` 和 `state_version` 后编码。默认租约为 30 分钟，每次调用 `heartbeat_run` 将到期时间延长到当前时间之后 30 分钟；自动续租助手仍每约 20 秒发送心跳。心跳仅更新租约时间，不改变状态版本；计划、结果等业务写入仍推进版本。可以用 `request_clarification` 提问，并由具备审核权限的 Agent 按已确认答案调用 `answer_run_clarification`；范围变化必须修订规格。
6. 完成后登记必要证据并调用 `submit_run_result`，如实上报每项 AC 的验证结果；成功结果绑定完整 head SHA。创建 PR 后通过 `list_delivery_tasks` 获取最新任务版本，再调用 `link_pull_request`，平台回查仓库、目标分支及 head/base SHA。

公开需求批准规格后会异步创建或同步 GitHub Issue，私密需求不会自动创建公开 Issue。PR 应通过交付任务显式关联，或在正文使用 `Closes #Issue编号`；仅写 `REQ-*` 或需求链接不会触发自动关闭。

目标仓库 `master` 的关联 PR 合并后，需求自动变为 `closed`，交付任务保留 `merged`；已发布、已拒绝、重复、已撤回等终态不会被覆盖。合并后才绑定 PR 也会立即补齐状态。后台 worker 在配置 GitHub 凭证时每小时对全部已关闭 PR 分页对账，补偿漏收的合并事件；Web/MCP 的“同步 GitHub Issues”也会排队触发对账。对账失败使用普通后台任务的重试机制，可通过后台任务记录查看错误。历史上没有 Issue 或交付任务关联的需求需人工核验合并证据后关闭，不凭标题或模糊提及自动关闭。

仍支持逐步执行 `create_delivery_task` → `claim_delivery_task(task_id=... 或 requirement_id="REQ-123")` → `submit_implementation_plan`；不传筛选时才从队列领取最早满足依赖的任务。任务绑定令牌不能跨任务领取。平台提供完整工具和仓库技能，但不在后台自动启动编码模型；由当前 Codex/Claude 会话执行上述流程。

长时间命令可使用自动续租助手（在 `server` 目录执行）：

```powershell
# RP_AGENT_API_URL 为平台根 URL；RP_AGENT_TOKEN 从已有安全环境配置注入。
# run.json 为领取/启动返回的 JSON，包含租约凭证，保存在仓库外。
uv run python -m requirement_platform.agent_runner --run-file C:/private/run.json -- <编码或测试命令及参数>
```

助手运行命令期间自动续租并读取最新版本；租约失效、取消或阻塞时停止命令。它不会自动宣称编码成功，结果与 AC 证据仍由 Agent 上报。

新的逻辑动作必须使用新的幂等键；过期 attempt 或 lease 的写入会被拒绝。产物内容应存放在受 ACL 保护的位置，平台数据库只保存元数据和 hash。

面向公网时，内置 nginx 会限制单 IP 的登录、注册和 API 访问频率，并限制请求体大小；应用层还会限制每个账号每天的提交数和未关闭需求数。API 与 SQLite 均不暴露宿主机端口，公网只应开放 HTTPS 反向代理入口。

## 验证

```powershell
pwsh ./tests/scripts/run-tests.ps1 -Layer unit -Component requirement-platform -Level all

cd package/requirement-platform/web
npm run build
```

独立工作流位于 `.github/workflows/requirement-platform.yml`。它仅监听此子系统及工作流自身的改动；`requirement-v*` 标签用于发布需求平台镜像，与 TrailSnap 的 `v*` 发布链路分离。
