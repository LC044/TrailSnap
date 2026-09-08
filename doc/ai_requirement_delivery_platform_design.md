# TrailSnap 需求管理平台开发设计

> 文档状态：首期实施方案
> 版本：1.1
> 更新日期：2026-09-08
> 适用范围：TrailSnap 用户需求收集、AI 辅助分析、人工审核和版本批次管理

## 1. 背景

TrailSnap 已具备 GitHub Actions 自动测试、构建和发布能力，也具备 `release-publisher` Skill，可完成 TrailSnap 产品的版本号同步、完整测试、GitHub Release 创建、标签 CI 监控和附件验收。

当前用户反馈入口主要跳转到 GitHub Issues。普通用户需要 GitHub 账号，无法直接在行影集内提交需求并持续查看状态；维护者也缺少统一的需求审核、开发候选和版本批次管理界面。

本方案在 TrailSnap 主仓库中新增独立的需求管理平台子包。首期只实现人工需求管理所需的前三阶段：

1. 需求提交、查看、审核和审计。
2. AI 辅助分析、查重和 GitHub Issue 同步。
3. 开发候选池和版本批次管理。

AI 自动开发、自动测试编排和自动发布暂不实施，仅作为后续扩展方向保留数据和接口边界。

## 2. 首期目标

```text
用户在行影集内提交需求
→ 平台校验并保存
→ AI 辅助分析和查重
→ 所有者或管理员审核
→ 进入开发候选池
→ 人工选择版本批次
→ 同步 GitHub Issue / Milestone
→ 人工维护开发与发布状态
→ 用户查看最终状态
```

首期需要实现：

- 用户直接在行影集内报告 Bug、提出改进或新功能。
- 用户查看公开需求、自己的需求及版本计划。
- AI 生成需求摘要、分类、重复候选、必要性、可行性和风险建议。
- 所有者或管理员决定需求是否进入开发候选池。
- 所有者或管理员决定哪些候选需求进入具体版本批次。
- 已接受需求按需同步到 GitHub Issue。
- 版本批次按需同步到 GitHub Milestone。
- 开发、测试和发布状态首期由管理员人工维护或从 GitHub 读取。
- 需求平台拥有独立的构建发布流程，不触发 TrailSnap 产品构建发布。

## 3. 首期非目标

- 不自动启动代码开发 Agent。
- 不自动修改 TrailSnap 代码。
- 不自动创建开发分支和 Pull Request。
- 不自动合并主分支。
- 不调用 `release-publisher` 自动发布 TrailSnap。
- 不为每位用户维护独立的 TrailSnap 代码分支。
- 不建设通用项目管理、客服、财务或工时系统。
- 不允许未经人工审核的反馈直接进入公开 GitHub Issue。

## 4. 产品原则

### 4.1 人工决策

AI 只提供分析和建议，不能自行决定需求进入候选池或版本批次。所有关键状态转换由所有者或管理员人工确认。

### 4.2 需求分层

个性化需求优先按以下顺序处理：

1. 用户偏好和规则通过配置实现。
2. 可插拔能力通过 Skill、插件或扩展实现。
3. 对多数用户有价值的能力进入 TrailSnap 主版本。
4. 单个用户专属代码仅在必要时使用独立扩展或客户分支。

### 4.3 代码同仓、运行隔离

需求平台代码放在 TrailSnap 主仓库中统一管理，但运行时必须使用独立服务、独立数据库文件、独立容器、独立域名和独立发布流程。

### 4.4 轻量优先

首期用户量和需求量较小，使用 SQLite 单机数据库，不引入 PostgreSQL、Redis、Celery、Kafka 等额外基础设施。数据访问层保留未来迁移到 PostgreSQL 的能力。

## 5. 角色与权限

所有注册用户默认拥有查看者权限。管理员和所有者自动拥有查看者的全部权限。

| 能力 | 查看者 | 管理员 | 所有者 |
| --- | ---: | ---: | ---: |
| 提交需求 | ✓ | ✓ | ✓ |
| 查看公开需求和版本计划 | ✓ | ✓ | ✓ |
| 查看自己提交的完整信息 | ✓ | ✓ | ✓ |
| 补充、撤回自己的需求 | ✓ | ✓ | ✓ |
| 关注需求并接收通知 | ✓ | ✓ | ✓ |
| 查看 AI 分析公开摘要 | ✓ | ✓ | ✓ |
| 查看完整 AI 分析和内部风险 |  | ✓ | ✓ |
| 审核、退回、拒绝和合并需求 |  | ✓ | ✓ |
| 将需求加入开发候选池 |  | ✓ | ✓ |
| 创建和维护版本批次 |  | ✓ | ✓ |
| 人工更新开发、测试和发布状态 |  | ✓ | ✓ |
| 管理用户角色和平台规则 |  |  | ✓ |
| 确认正式版本批次关闭 |  |  | ✓ |
| 导出完整审计记录 |  |  | ✓ |

### 5.1 所有者

- 平台最高权限角色，原则上只有一个主所有者。
- 任命或移除管理员。
- 调整审核、版本和权限规则。
- 确认版本批次最终完成或取消。
- 转移所有者身份时需要双方确认并记录审计事件。

### 5.2 管理员

- 负责日常需求审核、候选池和版本规划。
- 可以维护需求和版本状态。
- 可以同步 GitHub Issue 和 Milestone。
- 不能变更所有者或删除审计记录。

### 5.3 查看者

- 提交和管理自己的需求。
- 查看公开需求、版本计划和处理状态。
- 不能改变审核结论、优先级或版本归属。

## 6. 核心业务对象

### 6.1 需求

需求类型包括 Bug、改进和新功能，主要字段包括：

- 标题、类型和问题描述。
- 当前行为、期望行为和使用场景。
- Bug 复现步骤、发生频率和影响程度。
- TrailSnap 版本、部署方式、操作系统和浏览器环境。
- 截图或受限日志附件。
- 提交人、公开身份选项和联系方式。
- AI 分析结果、人工审核结论和内部备注。
- 关联需求、GitHub Issue、版本批次和最终发布版本。
- 当前状态和完整状态历史。

### 6.2 开发候选

进入候选池前应具备明确的用户价值、相对清晰的范围、可验证的验收标准、AI 初步分析、人工审核结论、优先级和风险等级。

### 6.3 版本批次

版本批次是一组计划在同一 TrailSnap 版本交付的需求，包含：

- 版本名称、建议版本号和版本类型。
- 版本目标和计划发布时间。
- 已选需求、优先级、依赖和开发顺序。
- 冻结的需求快照和验收标准。
- 人工维护的开发、测试和发布状态。
- GitHub Milestone 和关联 Issue。
- 发布说明和最终结果。

## 7. 功能清单与交互

### 7.1 行影集内需求入口

TrailSnap 设置页和帮助菜单提供提交 Bug、提出改进、提出新功能、查看我的需求、查看公开需求和查看版本计划入口。

提交流程：

1. 用户选择需求类型。
2. 页面展示对应表单并预填产品版本和环境信息。
3. 用户确认自动采集的信息并填写问题与期望。
4. 平台展示可能重复的需求。
5. 用户可以关注已有需求或继续提交。
6. 用户预览公开信息与隐私信息。
7. 用户完成验证并提交。
8. 平台生成需求编号，状态进入“待分析”。

### 7.2 我的需求与公开列表

用户可以筛选自己的需求、查看处理阶段、补充信息、在开发前撤回需求、关注需求并查看最终版本。公开列表支持搜索以及按类型、状态、版本和优先级筛选。包含隐私、安全漏洞或敏感数据的需求不公开。

### 7.3 AI 辅助分析

AI 输出需求摘要、类型、影响范围、重复候选、用户价值、必要性、可行性、复杂度、风险、验收标准、待补充问题、推荐处理方式和置信度。AI 不能直接改变审核结论。

### 7.4 审核工作台

工作台展示待分析、待审核、待补充、高影响、疑似重复、长期未处理和 AI 分析异常需求。

所有者或管理员可以修改分类、添加内部备注、要求补充、合并重复需求、接受为候选、暂缓、拒绝以及调整优先级、风险和公开范围。审核结论必须填写理由并记录审核人和时间。

### 7.5 重复需求合并

- 主需求保留完整流程。
- 被合并需求进入“已合并”。
- 原提交人自动关注主需求。
- 关注数量计入主需求。
- 私密信息不得自动复制到公开区域。

### 7.6 开发候选池

候选池支持按用户影响、关注人数、Bug 严重程度、人工与 AI 优先级、复杂度、风险、等待时间和产品方向匹配度筛选和排序。

### 7.7 版本批次管理

创建版本批次时填写版本名称、建议版本号、版本类型、目标、计划时间、最大风险等级和说明。

选择需求流程：

1. 从候选池选择需求。
2. 平台展示依赖、冲突和风险。
3. 管理员调整优先级与开发顺序。
4. 平台生成版本范围摘要。
5. 所有者或管理员确认候选名单。
6. 版本范围锁定，需求变为“已排期”。
7. 创建或关联 GitHub Milestone，并同步对应 Issue。

范围锁定后新增需求必须重新确认。移出需求需要填写原因，需求返回候选池。

### 7.8 人工交付状态维护

首期不自动驱动开发 Agent。管理员可以为版本需求维护未开始、开发中、PR 已创建、测试中、已完成、已阻塞和已移出版本等状态。平台可以读取 GitHub Issue、PR 和检查状态辅助展示，但是否完成由管理员确认。

## 8. 状态机

### 8.1 需求状态

```text
草稿 → 待分析 → 分析中 → 待补充 / 待审核
→ 开发候选 / 已拒绝 / 已暂缓 / 已合并
→ 已排期 → 开发中 → 测试中 → 待发布 → 已发布
```

辅助终态包括已撤回和已关闭。拒绝、暂缓和合并必须提供用户可理解的原因。

### 8.2 版本批次状态

```text
规划中 → 候选确认中 → 范围已锁定
→ 开发中 → 测试中 → 待发布 → 已发布 → 已完成
```

异常状态包括已阻塞、已暂停和已取消。首期由所有者或管理员维护。

### 8.3 AI 分析任务状态

```text
排队中 → 分析中 → 已完成
```

异常状态包括需要补充、失败、超时和已取消。

## 9. 仓库结构

需求平台代码放在 TrailSnap 主仓库的独立子包：

```text
TrailSnap/
├─ package/
│  ├─ website/
│  ├─ server/
│  ├─ ai/
│  ├─ official-site/
│  ├─ trailsnap-cli/
│  └─ requirement-platform/
│     ├─ web/
│     ├─ server/
│     ├─ worker/
│     ├─ migrations/
│     ├─ tests/
│     ├─ Dockerfile
│     └─ docker-compose.yml
├─ doc/
└─ .github/workflows/
```

同仓管理便于在一个 PR 中审查平台与 TrailSnap 接入代码，并统一贡献规范和代码风格。但需求平台不得导入 TrailSnap Server 内部模块、连接照片数据库或访问用户照片目录。

## 10. 技术选型

### 10.1 前端

| 类别 | 选型 |
| --- | --- |
| 框架 | Vue 3 + TypeScript |
| 构建 | Vite |
| UI | Element Plus |
| 状态管理 | Pinia |
| HTTP | Axios |
| 实时进度 | SSE |
| E2E | Playwright |

### 10.2 后端

| 类别 | 选型 |
| --- | --- |
| Web 框架 | FastAPI |
| 模型 | Pydantic |
| ORM | SQLAlchemy 2 |
| 迁移 | Alembic |
| 实时事件 | SSE / sse-starlette |
| 后台调度 | APScheduler |
| 异步任务 | SQLite 持久化任务表 + 独立 Worker |
| 测试 | pytest |

所有 API 延续 TrailSnap 的 `BaseResponse` 响应格式。

### 10.3 SQLite

数据库文件建议位于 `/app/data/requirements.db`。运行时：

- 开启 WAL 模式、外键约束和 busy timeout。
- API 事务保持短小，AI 和 GitHub 网络调用不得占用数据库事务。
- 单机只运行一个写任务 Worker。
- 数据目录使用 Docker Volume 或明确的宿主机挂载。
- 定期执行一致性检查和在线备份。

出现多机写入、持续锁等待、数据量显著增长、复杂向量检索或高可用要求时再迁移 PostgreSQL。ORM 和迁移避免依赖 SQLite 专属行为。

### 10.4 搜索与查重

首期采用 SQLite FTS5 全文搜索、标题和关键词归一化、内容哈希完全查重，以及 AI 对少量候选的相似性解释，不引入 pgvector。

### 10.5 异步任务

首期不引入 Redis 和 Celery。SQLite 持久化任务表和独立 Worker 处理 AI 分析、查重、GitHub 同步、状态刷新、通知和过期数据清理。

任务记录任务类型、业务对象、状态、尝试次数、下次执行时间、错误信息、租约和幂等键。Worker 重启后继续处理未完成任务。

### 10.6 附件

附件优先使用 Cloudflare R2；简化部署时可使用服务器独立数据目录。只允许 JPEG、PNG 和 WebP，每条最多 3 张、单张不超过 2 MB，使用随机文件名。日志只接受受限长度纯文本，不接受 ZIP、可执行文件和脚本。

## 11. 总体架构

```text
Cloudflare Pages 官网                   TrailSnap 应用
          │                                │
          └──────────────┬─────────────────┘
                         ▼
              feedback.trailsnap.cn
                         │
              Cloudflare WAF / Turnstile
                         │
                       Nginx
                         │
          ┌──────────────┴──────────────┐
          │                             │
   Requirement Web              Requirement API
                                        │
                      ┌─────────────────┼──────────────┐
                      │                 │              │
                 SQLite 数据库     Task Worker      附件存储
                                        │
                         ┌──────────────┴─────────────┐
                         │                            │
                    AI 分析服务                  GitHub App
                                                      │
                                             Issue / Milestone / PR 状态
```

AI 开发 Runner 和 Release Runner 不在首期部署范围内。

## 12. 身份与权限方案

不同自托管 TrailSnap 实例的用户数据库彼此独立，中心平台不能直接信任任意实例签发的 JWT。

首期建议：

- 公开需求和版本计划无需登录即可查看。
- 提交需求必须通过 Turnstile。
- 用户通过邮箱验证链接创建中心平台轻量账号，可选 GitHub OAuth。
- 登录后可以跨设备查看自己的需求和通知。
- TrailSnap 打开中心平台提交页并预填非敏感版本信息，由用户确认。
- 管理员和所有者使用 GitHub OAuth 和账号白名单，所有者启用二次认证。
- 会话使用 Secure、HttpOnly、SameSite Cookie，权限判断全部在服务端执行。

首期不实现自托管实例间的联合登录。

## 13. 数据模型

### 13.1 用户与权限

- `users`
- `user_identities`
- `roles`
- `user_roles`
- `sessions`
- `login_events`

### 13.2 需求

- `requirements`
- `requirement_revisions`
- `requirement_comments`
- `requirement_attachments`
- `requirement_relations`
- `requirement_followers`
- `requirement_review_decisions`

### 13.3 AI 分析

- `triage_jobs`
- `triage_reports`
- `duplicate_candidates`

### 13.4 版本批次

- `release_batches`
- `release_batch_items`
- `release_batch_revisions`
- `release_batch_decisions`

需求加入版本时保存需求快照和验收标准，后续修改不得静默改变已锁定范围。

### 13.5 GitHub 映射

- `github_links`
- `github_webhook_events`
- `outbox_events`

首期主要同步 Issue 和 Milestone，PR、Actions 和 Release 只读展示。

### 13.6 任务、通知和审计

- `background_jobs`
- `notifications`
- `audit_events`
- `idempotency_keys`
- `usage_quotas`

审计记录只允许追加，关键表包含并发版本字段。

## 14. GitHub 集成

### 14.1 事实边界

- 原始反馈和审核：需求平台。
- 正式开发需求：GitHub Issue。
- 版本批次：需求平台为主，GitHub Milestone 为镜像。
- PR、Actions 和 Release：首期只读关联和状态展示。

只有进入开发候选池的需求才允许创建 GitHub Issue。

### 14.2 GitHub App 权限

首期只部署需求同步 App，允许读取仓库元数据、创建和更新 Issue/Milestone、读取 PR 和检查状态、接收 Webhook。不授予代码写入、分支推送、PR 合并、标签和 Release 权限。

### 14.3 同步一致性

- 数据库事务完成后写入 Outbox。
- Worker 异步调用 GitHub。
- Webhook 验证签名并按事件 ID 去重。
- 同步操作具备幂等键和失败重试。
- GitHub 故障不能阻止用户提交。
- 同步冲突进入审核工作台人工处理。

## 15. AI 分析安全

```text
需求提交 → 格式和配额检查 → 内容安全检查
→ 文本标准化 → FTS5 和关键词查重
→ AI 结构化分析 → 保存报告 → 人工审核
```

- 分析模型没有 Shell、代码或 GitHub 写权限。
- 只读取当前需求和允许的历史摘要。
- 用户文本始终作为不可信内容处理。
- AI 输出必须通过固定 Schema 校验。
- 低置信度或失败结果交给人工。
- 同一需求内容版本默认只分析一次。
- 管理员重新分析受每日额度限制。

## 16. 防滥用和容量控制

```text
Cloudflare WAF → Turnstile → Nginx 请求大小限制
→ API 频率限制 → 用户配额 → 内容与附件检查 → SQLite
```

建议初始配额：

- 未验证用户不允许正式提交，或每天最多 1 条。
- 已验证查看者每天最多 5 条、每月最多 20 条。
- 单条正文合计不超过 16 KB。
- 每条最多 3 张图片，每张不超过 2 MB。
- 单个账号未关闭需求最多 20 条。
- 设置全站每小时和每日提交硬上限。
- 数据库、附件或磁盘达到高水位后暂停提交。

垃圾或未验证反馈 7 至 14 天后清理；数据库和附件达到 50%、70% 和 85% 阈值时告警，达到 85% 或剩余磁盘不足时进入只读保护。AI 每个需求版本默认分析一次，相同内容哈希复用结果，达到每日预算后任务排队。

## 17. 独立构建发布 Action

需求平台使用独立工作流：

```text
.github/workflows/requirement-platform.yml
```

仅监听：

```text
package/requirement-platform/**
.github/workflows/requirement-platform.yml
```

不得把 `package/requirement-platform/**` 加入现有 TrailSnap 产品构建发布 workflow。需求平台修改不触发 Website、Server、AI、Desktop、Mobile 和 CLI 构建。

### 17.1 PR 阶段

- 后端格式、单元测试和 SQLite 迁移测试。
- 前端类型检查、构建和 E2E。
- Docker 镜像构建验证，不推送正式镜像。
- 依赖与密钥扫描。

### 17.2 主分支阶段

合并到 `master` 且需求平台路径变化时：

- 运行需求平台完整测试。
- 构建独立 Docker 镜像。
- 推送 `edge` 和 Commit SHA 标签。
- 不创建 TrailSnap GitHub Release。
- 不触发 TrailSnap 语义化版本标签流程。

### 17.3 正式发布阶段

需求平台使用独立标签：

```text
requirement-v1.0.0
```

禁止使用 TrailSnap 产品的 `vX.Y.Z` 标签。

发布流程：

1. 手动触发或推送 `requirement-v*.*.*` 标签。
2. 运行需求平台测试。
3. 构建并推送独立镜像。
4. 进入 `requirement-production` GitHub Environment。
5. 所有者确认部署。
6. 服务器拉取精确镜像摘要。
7. 备份 SQLite。
8. 执行迁移并重启服务。
9. 执行健康检查；失败时恢复上一镜像和备份。

镜像使用独立名称，例如 `ghcr.io/lc044/trailsnap-requirement-platform`。需求平台版本独立维护，不写入 TrailSnap 产品 `version.json`，也不调用 TrailSnap 的 `release-publisher`。

## 18. 部署设计

### 18.1 域名

```text
trailsnap.cn                  官网，继续使用 Cloudflare Pages
feedback.trailsnap.cn         需求平台用户端和管理端
feedback.trailsnap.cn/api     Requirement API
feedback.trailsnap.cn/events  SSE
feedback.trailsnap.cn/hooks   GitHub Webhook
```

### 18.2 单机 Docker Compose

首期部署四个容器：

```text
requirement-nginx
requirement-web
requirement-api
requirement-worker
```

持久化目录：

```text
/srv/trailsnap-requirement/
├─ data/
├─ attachments/
├─ backups/
└─ logs/
```

使用独立 Linux 用户和 Docker Network。数据目录不与 TrailSnap 照片目录共享；API 只通过 Nginx 暴露；SQLite 不放在网络文件系统；容器使用非 root 用户；需求平台不能访问 TrailSnap 数据库和照片卷。

### 18.3 SQLite 并发约束

- 首期一个 API 实例和一个 Worker 实例。
- AI 和 GitHub 请求在事务外执行。
- Worker 使用短事务和任务租约。
- SSE 不持有数据库事务。
- 未来需要多个写实例时迁移 PostgreSQL，不共享 SQLite 文件。

## 19. 备份与恢复

- 每日执行 SQLite 在线备份。
- 正式部署和迁移前强制备份。
- 使用 SQLite Backup API 或正确的 WAL checkpoint，不直接复制正在写入的单个数据库文件。
- 保留 7 个每日备份和 4 个每周备份。
- 加密后复制到异地存储。
- 每月至少验证一次恢复。

恢复时暂停提交和 Worker，校验并恢复数据库与附件，执行一致性检查，启动服务后检查未完成任务和 GitHub 同步状态。

## 20. 监控

至少监控：

- API 可用性、延迟和错误率。
- 提交成功率、Turnstile 失败率和限流数量。
- SQLite 数据库、WAL 和磁盘使用量。
- SQLite 锁等待和 busy 错误。
- 后台任务长度、失败和重试。
- Webhook 和 Outbox 积压。
- AI 调用量、失败率和费用。
- 邮件发送失败率。
- 需求平台构建和部署结果。

## 21. 实施阶段

### 第一阶段：基础人工需求管理

- 在 `package/requirement-platform/` 建立独立子包。
- SQLite、Alembic 和持久化目录。
- 查看者、管理员和所有者三角色。
- 用户登录、需求提交、我的需求和公开列表。
- 审核工作台、状态机、通知和审计。
- Turnstile、限流、配额和附件限制。
- TrailSnap 内增加需求入口。
- 建立独立构建发布 Action。

### 第二阶段：AI 分析与 GitHub 同步

- SQLite 持久化任务 Worker。
- AI 结构化分析。
- FTS5、关键词和内容哈希查重。
- 开发候选池。
- 候选需求转 GitHub Issue。
- GitHub Webhook 双向同步。
- GitHub PR 和 Actions 状态只读展示。

### 第三阶段：版本批次管理

- 创建版本批次和选择候选需求。
- 需求快照、范围锁定和重新确认。
- GitHub Milestone 映射。
- 版本依赖、冲突和风险检查。
- 人工维护开发、测试和发布状态。
- 版本进度公开展示。
- 版本完成后回写需求最终状态。

### 后续阶段：暂不实施

- AI 自动开发和 PR 创建。
- 独立开发 Agent Runner。
- 自动测试修复循环。
- Release Runner 和 TrailSnap 自动发布。
- 接入 `release-publisher` 的受控发布流程。

后续实施前重新进行权限、隔离和发布风险评审。

## 22. 首期验收标准

- 需求平台代码位于 TrailSnap 主仓库独立子包。
- 使用独立 SQLite 数据库，不连接照片数据库。
- 查看者可以在 TrailSnap 内提交需求并查看状态。
- 所有者和管理员可以审核、合并、拒绝、暂缓和接受需求。
- AI 只能生成辅助分析，不能自动通过审核。
- 未经审核的需求不会进入 GitHub。
- 管理员可以将需求加入候选池。
- 所有者或管理员可以创建版本批次并人工选择需求。
- 范围锁定后保存不可变的需求和验收标准快照。
- GitHub Issue 和 Milestone 同步失败可重试且不会重复创建。
- 开发、测试和发布状态可以人工维护并向用户展示。
- 需求平台 Action 与 TrailSnap 产品工作流路径和标签完全隔离。
- 发布需求平台不会触发 TrailSnap 产品构建发布。
- SQLite、附件和备份有容量限制与恢复流程。
- 用户提交、AI 分析、审核、版本调整和角色变更全过程可审计。
