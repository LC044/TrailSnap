---
name: trailsnap-commit
description: TrailSnap 需求规格、Agent 编码交付、提交与 PR 工作流。Use when implementing TrailSnap requirements, managing platform requirements and acceptance criteria, preparing commits, pushing branches, creating pull requests, or monitoring PR CI in this repository.
---

# TrailSnap Agent 交付与提交规则

仅在用户明确要求提交、推送或创建 PR 时执行相应 Git 操作。先保护并核对用户已有改动，不要覆盖或擅自丢弃工作区内容。

## 提交原则

- 按根目录 AGENTS.md 和 tests/README.md 选择验证范围，统一通过 tests/scripts/run-tests.ps1 执行；需求平台使用 `-Layer unit -Component requirement-platform -Level all`。

## 提交信息

- 遵循 Conventional Commits：`feat(scope):`、`fix(scope):`、`refactor(scope):` 等。
- 以下关键字会触发成本较高的发布/构建流水线，只有在用户明确要求时才包含：
  - `构建后端`：Server Docker 构建与推送，仅 `package/server/` 变更时生效。
  - `构建前端`：Frontend Docker 构建与推送，仅 `package/website/` 变更时生效。
  - `构建ai`：AI 服务 Docker 构建与推送，仅 `package/ai/` 变更时生效。
  - `构建cli`：CLI 构建并保留 Actions Artifacts，仅 `package/trailsnap-cli/` 变更时生效；只有 `v*.*.*` 标签会创建 Release 并发布 npm/PyPI。

## 需求平台

- 所有开发事项统一通过已配置的 `trailsnap-feedback` MCP 管理。不要使用 GitHub CLI、GitHub API 或网页直接创建、编辑、关闭 GitHub Issue；GitHub Issue 由需求平台在后台创建和同步。
- 如果未配置、无法连接或找不到 `trailsnap-feedback` MCP，先引导用户在[需求平台](https://feedback.trailsnap.cn/)的“集成设置”创建 Agent MCP 令牌，并采用平台提供的 MCP 配置完成连接后再继续。不要自行创建令牌、要求用户在对话中粘贴令牌，或回退为直接操作 GitHub Issue。
- MCP 返回未认证、无权限或缺少 scope 时，说明当前操作所需的最小权限，并请用户联系需求平台管理员开通或调整令牌权限。
- 开始平台需求的编码交付前调用 `get_agent_capabilities`，检查现有令牌权限和任务绑定；不创建或调整令牌，不通过其他接口绕过 scope。任务创建、领取、取消仍沿用现有鉴权规则；完整编码交付需要 `runs:write`，规格编写需要 `requirements:write`，批准规格和答复执行澄清需要 `requirements:review`。
- 查询并复用对应需求；不存在则调用 `create_requirement`，记录 `REQ-*` 编号。调用 `list_requirement_specs` 读取规格修订，由 Agent 根据用户需求编写 `problem`、`user_scenario`、`goal`、`in_scope` 和 Given/When/Then 验收标准 `acceptance`（例如 `AC-01`），通过 `create_requirement_spec` 或 `update_requirement_spec` 保存。不要机械地将原需求正文复制成验收标准。
- 现有令牌有审核权限时，Agent 可调用 `approve_requirement_spec` 自动批准无阻塞问题的规格，不要求用户到页面点击。只根据用户已授权范围和已确认事实编写规格；产品歧义通过澄清解决，不编造答案。GitHub 基线解析失败时报告原因；不要自行伪造 SHA。
- 计划形成后优先调用 `start_requirement_delivery(requirement_id=REQ编号, ...)`，原子创建/复用任务、指定领取并提交计划。`acceptance_plan` 的键覆盖每个必需 AC，值说明如何实现及验证；不使用空白内容或不存在的 AC。保存返回的 `id`（run_id）、`attempt_id`、`lease_token` 和 `state_version`。也可以依次调用 `create_delivery_task`、`claim_delivery_task(task_id=... 或 requirement_id=...)` 和 `submit_implementation_plan`。指定需求时禁止不带筛选领取其他队列任务。
- 计划提交成功后编码。每约 20 秒续租，所有执行写入携带当前 attempt、lease、状态版本和幂等键；同一请求重试复用幂等键，新动作使用新键。心跳不改变状态版本，其他写入使用返回的新版本。长时间的编码/测试命令可用需求平台的 `requirement_platform.agent_runner` 包装自动续租，使用已有令牌的环境变量，凭证文件放在仓库外，不输出凭证或提交凭证文件。
- 遇到阻塞问题调用 `request_clarification`，收到用户答案后可用 `answer_run_clarification` 回填；涉及范围变化时修订并重新批准规格。失去租约或被取消后停止旧 attempt，不继续上报；重新读取状态后再决定领取。
- 实现完成后如实填写 `acceptance_coverage`、`self_test_results`、改动文件和限制，通过 `submit_run_result` 上报；需要证据产物时使用 `submit_run_artifact`（`artifacts:write`）。成功结果需完整提交 SHA，未获提交授权时保留工作区改动并说明尚未提交，不冒充已有交付提交。创建 PR 后用 `list_delivery_tasks` 读取最新 task 版本，再 `link_pull_request`。不使用 `update_requirement_status(developing)` 代替规格、计划和交付门禁。
- 需求描述应说明问题、目标、范围和验收标准。范围变化时更新平台需求，不直接更新其关联的 GitHub Issue。
- GitHub Issue 编号或链接只能作为平台返回的只读关联信息使用，不能作为状态管理入口。
- PR 合并后，确认 GitHub Webhook 已自动关闭对应需求；若自动同步失败，再通过需求平台关闭，并在理由中写明 PR 编号、合并结果和 CI 状态。

## 分支与 PR

- 建议新建分支推送，并通过 PR 合并到主分支。
- 创建 PR 前必须存在对应的平台需求及其关联 GitHub Issue。PR 标题与描述应与需求呼应，并在 PR 描述中同时写明平台需求编号、链接（例如 `关联需求：[REQ-123](https://feedback.trailsnap.cn/REQ-123)`）和 GitHub 关闭关键字（例如 `Closes #456`）。关闭关键字用于在需求详情页展示关联 PR，并在合并后自动关闭 Issue 与需求单。
- PR 使用 `.github/pull_request_template.md`，并在评论中确认 CLA：`I have read and agree to the CLA`（基于 AGPLv3）。

## PR CI 监控

- 提交 PR 后必须监控对应 CI 流水线，直到全部工作流完成。
- 使用 GitHub CLI 查看 run 状态与日志，并只关联当前 PR 的 runs，避免混入其他分支任务。
- 任一工作流失败时，定位到具体 job 和失败日志，分析根因；在本地或工作区实施最小必要修复，推送修复提交后继续监控。
- 在所有必需 CI 通过前，不要宣称 PR 已完成或可以合并。
- 一个 PR 包含多个修改或后续扩大范围时，需要同步更新对应的平台需求。
- PR 合并后确认平台需求已关闭；如无未迁移的工作，可删除功能分支。
