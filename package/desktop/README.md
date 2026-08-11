# TrailSnap Desktop（Tauri 2）

桌面应用使用 Tauri 2 管理 PyInstaller 打包的 FastAPI Sidecar。Vue 构建产物
直接内嵌到 WebView，Rust 在后台选择随机本地端口、启动后端、执行健康检查，并在退出
时清理后端进程树。桌面端使用本地 SQLite 数据库，无需安装 PostgreSQL。

## Windows 本地构建

需要预先安装 Node.js/pnpm、Python/uv、Rust stable，以及 Tauri 对应平台的系统依赖。
在仓库根目录执行：

```powershell
pwsh .\build-windows-installer.ps1
```

构建脚本会检查必要工具，并依次完成依赖安装、Vue 构建、PyInstaller Server 打包、
Sidecar 暂存和 Tauri NSIS 打包。重复构建时可以用 `-SkipInstall` 跳过依赖安装，
用 `-OpenOutput` 在成功后打开产物目录：

```powershell
pwsh .\build-windows-installer.ps1 -SkipInstall -OpenOutput
```

Windows NSIS 安装包位于：

```text
package/desktop/src-tauri/target/release/bundle/nsis/
```

首次启动会在 `%LOCALAPPDATA%\TrailSnap\data\trailsnap.sqlite` 创建数据库、执行独立的
SQLite Alembic 迁移并创建本地管理员。界面启动时会自动换取标准 JWT，因此看起来无需登录，
后端的用户隔离与鉴权行为仍与服务器端一致。运行日志位于同级 `logs` 目录。

GitHub Actions 在 Windows、macOS 和 Linux 原生 runner 上分别打包 PyInstaller Sidecar 与
Tauri 安装包，产出 NSIS、DMG、AppImage 和 DEB。

## 当前 SQLite 边界

Electron 时代由 Node 主进程实现的 AI 扩展下载、离线导入和本地 AI Gateway 尚未迁移
到 Rust。SQLite 首轮覆盖用户/认证、照片、相册、标签、元数据、任务和向量存储；
PostgreSQL 专属统计查询需要逐项补充方言实现。
AI 运行时已经切换为 PyInstaller 构建，但需要完成 Rust 扩展管理器后才重新接入桌面设置页。

该边界不影响服务端完整版的远程 AI 配置，也不改变已有 AI 模型与数据库数据。
