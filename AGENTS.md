# AGENTS.md

本文件适用于在 TrailSnap（行影集）仓库中工作的编码代理，仅保留执行约束和文档入口。

## 按需查阅

- 开发环境与贡献流程：[CONTRIBUTING.md](CONTRIBUTING.md)。
- 安装与部署：[README.md](README.md)；架构概览：[doc/architecture_design.md](doc/architecture_design.md)。
- 各模块的启动与构建命令：对应的 `package/<模块>/README.md`。
- 测试参数、服务生命周期与 CI 约定：[tests/README.md](tests/README.md)。

## 后端约束

- 新增 API 统一返回 `BaseResponse[T]`（`code`、`msg`、`data`），使用 `success()` / `fail()`；主后端定义见 `package/server/app/dependencies.py`。
- 修改 ORM 模型后，使用 Alembic 生成并提交迁移，同时提供 PostgreSQL（`package/server/alembic/`）和 SQLite（`package/server/alembic_sqlite/`）版本。同一 PR 内的多次迁移按数据库类型分别合并为一个迁移文件。

## 前端约束

以下路径均相对于 `package/website/`。

- Vue 组件使用 `<script setup lang="ts">`；状态使用 Pinia；HTTP 请求统一通过 `src/api/*`。
- 跟随主题的强调色使用 `src/style.css` 中的 `primary-*` 工具类，不硬编码品牌色。JS 绘图或动态样式通过 `src/composables/useTheme.ts` 的 `injectTheme()` 读取 `currentTheme.value.primary` / `.rgb`，并在主题切换后重新绘制。
- 每个 `text-gray-*` 和 `bg-white` 都必须搭配对应的 `dark:` 变体。Element Plus 组件继承全局暗色配置，不在各实例内覆盖内部颜色。

## 测试约束

- 本地与 CI 统一使用 `tests/scripts/run-tests.ps1`，按改动范围选择测试层和级别。
- 测试环境变量统一由 `tests/.env.test` 提供（模板：`tests/.env.test.example`；CI：`tests/.env.test.ci`）。
- 使用 Playwright CLI 调试本地开发环境时，账号密码为 `trailsnap` / `trailsnap`；登录失败应向用户询问，不得自行创建测试账号。

常用冒烟测试（仓库根目录执行）：

```powershell
pwsh .\tests\scripts\run-tests.ps1 -Layer unit -Level smoke
```
