---
name: trailsnap-commit
description: TrailSnap 仓库提交、推送、需求平台与 PR 工作流规则。Use when preparing commits, pushing branches, managing the corresponding platform requirement, creating or merging pull requests, or monitoring PR CI in this repository; do not use for ordinary code changes that do not involve submission.
---

# TrailSnap 提交与推送规则

仅在用户明确要求提交、推送或创建 PR 时执行相应 Git 操作。先保护并核对用户已有改动，不要覆盖或擅自丢弃工作区内容。

## 提交原则

- 不要求为了提交而在本地运行测试；测试由 GitHub Actions 负责。
- 只有用户明确要求本地验证时才运行本地测试。

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
- MCP 返回未认证、无权限或缺少 scope 时，说明当前操作所需的最小权限，并请用户联系需求平台管理员开通或调整令牌权限。未经授权不得绕过权限或改用 GitHub Issue。
- 开始需要提交或创建 PR 的工作前，先用 MCP 查询是否已有对应需求。存在则复用；不存在则用 `create_requirement` 创建内容完整的需求，记录其 `REQ-*` 编号，并将需求状态设置为`developing`。
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
