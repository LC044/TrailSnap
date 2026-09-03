---
name: trailsnap-commit
description: TrailSnap 仓库提交、推送、Issue 与 PR 工作流规则。Use when preparing commits, writing commit messages, pushing branches, creating issues or pull requests, or monitoring PR CI in this repository; do not use for ordinary code changes that do not involve submission.
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

## 分支、Issue 与 PR

- 建议新建分支推送，并通过 PR 合并到主分支。
- 创建 PR 前必须先创建对应的 GitHub Issue，用中文说清本次 PR 要修改的问题、目标和范围；不要只写“修复问题”或“更新代码”。
- PR 标题与描述应与 Issue 呼应，并在 PR 描述中关联 Issue（例如 `Closes #123`）。
- PR 使用 `.github/pull_request_template.md`，并在评论中确认 CLA：`I have read and agree to the CLA`（基于 AGPLv3）。

## PR CI 监控

- 提交 PR 后必须监控对应 CI 流水线，直到全部工作流完成。
- 使用 GitHub CLI 查看 run 状态与日志，并只关联当前 PR 的 runs，避免混入其他分支任务。
- 任一工作流失败时，定位到具体 job 和失败日志，分析根因；在本地或工作区实施最小必要修复，推送修复提交后继续监控。
- 在所有必需 CI 通过前，不要宣称 PR 已完成或可以合并。
- 一个pr提交多个一个pr提交多个修改，提交新的修改后需要更新对应的issue。
- PR 合并后需要关闭对应的issue，如无未迁移的工作，可删除功能分支。
