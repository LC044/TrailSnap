---
name: "release-publisher"
description: "发布并验收 TrailSnap 新版本：汇总提交、同步全项目版本号、更新官网日志与客户端更新清单、执行发布前测试、创建 GitHub Release、监控标签 CI、核验 Release 附件，并生成小红书和公众号文案。Use when the user asks to 发布新版本、发版、创建或检查 GitHub Release、总结版本变更、监控发布 CI、检查发布产物，或撰写版本更新帖子。"
---

# TrailSnap 版本发布与验收

严格按顺序执行。完整性优先于打标签；未经用户确认，不得创建 GitHub Release。

## 1. 发布前检查

1. 确认位于 TrailSnap 仓库根目录。
2. 运行 gh auth status，确认 GitHub CLI 已登录。
3. 运行 git status --short --branch。保护用户已有改动；工作区不干净时先判断归属，不得覆盖。
4. 获取远程标签，并只选择严格语义化标签：
   - 接受正则 ^v[0-9]+\.[0-9]+\.[0-9]+$
   - 排除 pr-preview、app-v*、预发布标签等
   - 不要直接信任 git describe --tags；它可能选中非版本标签
5. 确认目标标签和 Release 均不存在：
   - 检查本地标签、git ls-remote --tags origin 和 gh release view
6. 获取上个正式版本到 HEAD 的提交。若为空，停止并提示先提交代码。
7. 运行 git grep 搜索上个版本的带 v 和不带 v 形式，建立版本影响清单。

PowerShell 可按版本对象排序标签：

    $lastTag = git tag --list |
      Where-Object { $_ -match '^v\d+\.\d+\.\d+$' } |
      Sort-Object { [version]($_ -replace '^v', '') } -Descending |
      Select-Object -First 1

## 2. 确定版本号

- 用户已指定版本时直接采用。
- 未指定时根据提交建议 patch、minor 或 major。
- patch：修复和小优化。
- minor：向后兼容的新功能。
- major：不兼容变更；必须向用户确认影响与迁移方式。
- 标签始终使用 v 前缀，项目文件使用不带 v 的版本号。

## 3. 同步版本号

以下是当前基线清单，不是完整清单。先更新这些位置，再用 git grep 发现新增位置。

### AI 服务

- package/ai/pyproject.toml
- package/ai/uv.lock
- package/ai/desktop_app.py
- package/ai/app/services/photo_model_repository.py 中的 User-Agent

### Server

- package/server/pyproject.toml
- package/server/uv.lock
- package/server/app/core/config_manager.py 中的全部版本常量和默认值

### Website 与 CLI

- package/website/package.json
- package/trailsnap-cli/package.json
- package/trailsnap-cli/pyproject.toml
- package/trailsnap-cli/trailsnap/cli.py
- 仅在测试夹具表达“当前产品版本”时同步测试版本；不要误改依赖版本，例如 ts-node@10.9.2

### Desktop 与 AI 扩展

- package/desktop/package.json
- package/desktop/src-tauri/Cargo.toml
- package/desktop/src-tauri/Cargo.lock
- package/desktop/src-tauri/tauri.conf.json
- package/desktop/src-tauri/resources/ai-extensions.json
- package/desktop/src-tauri/src/ai_extension.rs 中的扩展版本
- .github/workflows/build-desktop-ai-extension.yml 中的 EXTENSION_VERSION

完成后再次搜索旧版本：

- 历史 changelog 和 version.json 中的旧版本应保留。
- 第三方依赖版本不得误改。
- 所有当前产品版本、锁文件本地包版本和发布工作流版本必须一致。

## 4. 分析提交并撰写内容

按功能模块归并最终用户可见结果，不要机械罗列 commit。

- 优先提炼 feat、fix、perf 和有用户影响的 refactor。
- 忽略构建前端、构建后端、构建ai、构建cli 等 CI 触发词。
- 忽略中间修复：如果同一功能先实现后优化，只描述最终能力。
- 测试、内部重构和 CI 调整仅在影响稳定性、安装或发布体验时提及。
- Release Notes 使用中文，按桌面端、移动端、照片浏览、设置、安装部署、修复稳定性等实际模块组织。
- 避免无必要的实现术语。

## 5. 更新官网和客户端更新清单

必须在创建标签前完成：

1. 在 package/official-site/docs/guide/changelog.md 顶部加入中文日志，使用“新增功能 / 优化功能 / Bug 修复”。
2. 在 package/official-site/en/docs/guide/changelog.md 顶部加入等价英文日志，使用“New / Improvements / Bug Fixes”。
3. 在 package/official-site/public/version.json 数组末尾加入新版本：
   - version 不带 v
   - update_info 使用面向用户的简洁中文 HTML，以 <br> 换行
   - download_url 指向本次 GitHub Release 地址
4. 生成 releases/v{version}/：
   - release-notes.md
   - xiaohongshu.md
   - wechat.md

releases/ 通常被 git 忽略；确认三个文件存在即可，不强行提交。

## 6. 发布前验证、提交与推送

依次执行：

1. 在 package/official-site 下解析 public/version.json。
2. 在 package/official-site 下运行 pnpm docs:build。
3. 在仓库根目录运行完整 E2E：

    pwsh .\tests\scripts\run-tests.ps1 -Layer e2e -Level full

4. 若失败：
   - 区分代码失败与环境/启动器失败。
   - 修复属于本次发布范围的根因后，重新运行同一完整命令。
   - 不得把扫描准备通过或部分用例通过报告为完整通过。
5. 审查 git diff、git diff --check 和工作区状态。
6. 提交所有版本号、官网日志、version.json 及必要的发布测试修复。
7. 使用 Conventional Commits，例如 chore(release): prepare vX.Y.Z。
8. 除非用户明确要求，不在提交消息中加入镜像或包发布触发词。
9. 推送当前分支，确认本地 HEAD 与远程一致且工作区干净。

## 7. 确认并创建 Release

1. 向用户完整展示 release-notes.md。
2. 明确说明官网构建和完整 E2E 结果。
3. 等待用户确认。
4. 确认后创建 Release：

    gh release create vX.Y.Z --title "vX.Y.Z" --notes-file "releases\vX.Y.Z\release-notes.md"

5. 记录 Release URL、标签 SHA 和创建时间。
6. 不要手动重复创建标签；gh release create 会创建并推送标签。
7. 不得移动已发布标签或删除 Release，除非用户明确授权。

## 8. 监控标签 CI

创建 Release 后不要立即结束。持续监控该标签触发的工作流，直到全部进入 completed。

当前应关注的工作流基线：

- Build and Push Frontend
- Build and Push Server
- Build and Push AI
- Build Desktop Installers
- Build Desktop AI Extension
- Build Mobile App
- Build and Publish CLI

使用 gh run list --branch vX.Y.Z 和 gh run view 检查状态、矩阵任务及失败步骤。

- 记录本次标签触发的 run ID，避免混入同一提交的分支 push 任务。
- 定期汇报状态变化，不重复播报无变化快照。
- 工作流 queued 或 pending 时继续等待。
- 任一工作流失败时，读取失败 job 和日志，报告根因。
- 未经用户授权，不移动标签、重建 Release 或实施范围外修复。
- Docker 镜像工作流成功不代表有 Release 附件；分别报告镜像与附件状态。

## 9. 验收 Release 附件

从工作流定义推导预期附件，不只依赖固定数量。当前 v0.10.0 结构的基线为 12 个：

- Desktop：Windows EXE、macOS DMG、Linux AppImage、Linux DEB
- Mobile：Android APK
- CLI：Windows、Linux、macOS 可执行文件
- Desktop AI Extension：Windows、Linux、macOS 压缩包和 ai-extensions.json

验收要求：

1. 运行 gh release view vX.Y.Z --json assets。
2. 确认每个预期文件存在、size 大于 0、state 为 uploaded。
3. 确认标签 SHA 与发布提交 SHA 一致。
4. 确认 Release 不是 draft 或 prerelease，除非用户要求。
5. 确认全部相关 CI 为 completed/success。

## 10. 生成安装包下载区并验证 Release 正文

多个上传工作流可能使用 generate_release_notes 更新同一个 Release，从而修改标题。

所有 CI 完成后必须：

1. 检查 Release 标题和正文。
2. 将其与用户确认过的 release-notes.md，追加的 “What's Changed”可以保留。
3. 若标题或正文被改变，恢复：

    gh release edit vX.Y.Z --title "vX.Y.Z" --notes-file "releases\vX.Y.Z\release-notes.md"

4. 从 `gh release view vX.Y.Z --json assets` 的 `assets[].url` 读取浏览器直链，在本地 release-notes.md 末尾生成或替换 `## 安装包下载`：
   - Windows：EXE 安装包
   - macOS：DMG 安装包，并标注实际架构
   - Linux：AppImage 和 DEB 安装包
   - Android：APK 安装包
   - 只列面向普通用户的应用安装包；不要列 CLI 可执行文件、Desktop AI Extension 压缩包或 ai-extensions.json
   - 只使用 size 大于 0 且 state 为 uploaded 的附件；必须使用 `url`，不要使用 `apiUrl`
   - 链接文字包含文件名或明确格式；按平台归组，同一平台有多种格式时放在同一项
   - 操作必须幂等：已有 `## 安装包下载` 时替换该节，不得重复追加
5. 若任何预期安装包缺失，停止并报告，不得发布不完整的下载区或宣称验收成功。
6. 使用更新后的 release-notes.md 再次恢复 Release 标题和正文：

    gh release edit vX.Y.Z --title "vX.Y.Z" --notes-file "releases\vX.Y.Z\release-notes.md"

7. 再次确认正文与更新后的 release-notes.md 完全一致、安装包直链均来自已验收附件、附件数量不变且全部 uploaded。

## 11. 社媒文案规范

### 小红书

- 300–500 字，产品向、口语化，活泼但不过分。
- 标题突出核心价值，可使用一个 emoji，不做标题党。
- 用【】标记重点功能，每段最多 1–2 个 emoji。
- 描述用户收益，不解释 API、框架或内部实现。
- 结尾邀请反馈，并附 5–8 个相关标签。

### 公众号

- 800–1500 字，专业友好，使用 Markdown。
- 标题包含版本号与主要更新。
- 按功能模块解释“是什么、有什么价值、适用场景”。
- 包含体验优化、升级方式和结尾感谢。
- major 版本必须增加“⚠️ 升级注意事项”，说明影响与迁移方式。
- 不凭空承诺下一版本；仅在提交或计划中有依据时预告。

Skill 不自动向社交平台发布内容，只生成文件并提醒用户审阅。

## 12. 完成报告

报告以下内容：

- 版本号和 GitHub Release 链接
- 发布提交与标签 SHA
- 官网构建结果
- 完整 E2E 汇总
- 每个发布工作流的最终状态
- Release 附件数量、分类和 uploaded 状态
- Release 正文中的各平台安装包下载链接，以及已排除 CLI 和 AI 扩展下载链接
- Release 标题与正文是否通过最终复核
- 三份本地文案的绝对路径链接
- 提醒用户审阅后再手动发布社媒内容

若任何 CI 或预期附件失败，不得宣称发布全部成功。
