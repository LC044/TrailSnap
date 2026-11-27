# TrailSnap 定时测试交付（GitHub CI）

**供 05:00 / 10:00 / 15:00 / 20:00 值守使用。** 以本页代替旧的本地 E2E 清单；不读历史会话、长篇记忆或完整 CI 日志。允许按现有测试规范修复可证实的失败和补有效覆盖，不能修改流水线、弱化断言/跳过失败，或动人工工作区。必要时只查根 `AGENTS.md` 和相关 `trailsnap-commit` 规则。

1. **开工。** 从定时任务给出的主仓库路径执行 `pwsh -NoLogo -File tests/scripts/Start-NightlyWorktree.ps1 -Slot <1–4>`。只读一行结果。`READY` 才继续；之后所有编辑和提交在 `worktree` 中。复用已标记 `codex-automation` 的唯一值守 PR；无 PR 从 `origin/master` 开工。有多个 PR、Git 失败或 head 变化则停，不碰原 checkout。找不到 PR 时用 `Watch-NightlyCI.ps1 -Baseline` 看 `master` 最近一次 Tests，不主动重跑；基线不是当前 `base` 时，不把旧失败当成当前回归。
2. **修复或补测。** 有 PR 时用 `Watch-NightlyCI.ps1 -PullRequest <号> -ExpectedHead <完整SHA> -CheckOnce` 看现有状态。`PENDING` 先交脚本等待，别推新提交打断正在跑的 CI；失败时只读摘要及相关文件。基础设施/取消/权限错误不要改业务代码。修复优先；全绿时挑一个近期改动、风险明确的模块，看相邻测试，补 1–3 个有断言价值的用例；不全仓扫描、不强行凑数。限 `package/server/{app,tests}`、`package/ai/{app,tests}`、`package/website/tests` 及与用例直接相关的 `tests/`（不改测试入口或工作流）。`baseNeedsSync` 时在 worktree 内合入返回的 `base`，冲突则报告，不强推。**本地只编辑、检查 diff、提交；不执行测试套件、不起服务、不扫全量覆盖率。**
3. **交付。** 明确暂存本轮文件，`git diff --check`，小提交一次，`git push origin HEAD:refs/heads/<返回的branch>`，永不 force。沿用现有 PR；确需新建时按仓库 `trailsnap-commit` 的需求/Issue 和 PR 门禁创建同仓 PR，并加 `codex-automation`；不能满足门禁则报告缺什么，不伪造关联。PR 创建或更新自然触发 GitHub Tests，不重复 dispatch。无有效改动则不做空提交；20:00 仍可收尾合并已有合格 PR。
4. **等待与收尾。** 对刚推送的完整 SHA 运行 `Watch-NightlyCI.ps1 -PullRequest <号> -ExpectedHead <完整SHA>`；仅第 4 槽加 `-Merge`。让脚本每 300 秒检查，静默至最终一行 JSON；用可阻塞的 shell 等待方式，别让模型自己循环查 GitHub。默认等 65 分钟；一轮总预算 120 分钟，剩余不够则缩短等待或留给下一轮。只对明确归因、可小范围修复的失败额外修推一次；同类失败、等待超时或限额即停，不再循环。脚本只在北京时间 20:00–23:00 内、PR 非草稿且 `CLEAN`、当前 PR head 与 master 均未变、当前 head 包含已查的 master、Tests E2E 通过且其他检查没有失败/取消/待定时尝试 squash；不绕过 GitHub 保护。`MERGE_UNCONFIRMED` 只查一次 PR 状态，不盲重试。

最后最多 5 行：`状态 | 失败或覆盖项 | SHA | PR/CI 链接 | 下一步`。保留未推改动的 worktree 并报告路径，不擅自归入下一轮；已验明 clean 且最后提交在远端后，用 `git worktree remove <本轮路径>` 回收，绝不 `--force`。需要同步晚班验证结果时，只更新已有 PR 一条短说明，不反复留言。
