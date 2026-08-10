# TrailSnap Desktop（Tauri 2）

桌面应用使用 Tauri 2 管理 PyInstaller 打包的 FastAPI Sidecar。Vue 构建产物
直接内嵌到 WebView，Rust 在后台选择随机本地端口、启动后端、执行健康检查，并在退出
时清理后端进程树。当前阶段仍依赖 PostgreSQL，尚未包含 SQLite Lite 改造。

## Windows 本地构建

需要预先安装 Node.js/pnpm、Python/uv、Rust stable，以及 Tauri 对应平台的系统依赖。
在仓库根目录执行：

```powershell
pwsh .\package\desktop\scripts\build.ps1
```

构建脚本依次完成 Vue 构建、PyInstaller Server 打包、Sidecar 暂存和 `tauri build`。
Windows NSIS 安装包位于：

```text
package/desktop/src-tauri/target/release/bundle/nsis/
```

默认数据库地址为
`postgresql://trailsnap:trailsnap@127.0.0.1:5532/trailsnap`。首次启动会生成
`%LOCALAPPDATA%\TrailSnap\data\.env`；运行日志位于同级 `logs` 目录。
阶段 0 安装包不会安装 PostgreSQL，可复用仓库 Docker Compose 中的 PostgreSQL。

GitHub Actions 在 Windows、macOS 和 Linux 原生 runner 上分别打包 PyInstaller Sidecar 与
Tauri 安装包，产出 NSIS、DMG、AppImage 和 DEB。

## 当前迁移边界

Electron 时代由 Node 主进程实现的 AI 扩展下载、离线导入和本地 AI Gateway 尚未迁移
到 Rust，因此本轮 Tauri 构建先验证基础 Server、Vue 页面、API/SSE 和进程生命周期。
AI 运行时已经切换为 PyInstaller 构建，但需要完成 Rust 扩展管理器后才重新接入桌面设置页。

该边界不影响服务端完整版的远程 AI 配置，也不改变已有 AI 模型与数据库数据。
