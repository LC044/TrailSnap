# TrailSnap Desktop（Tauri 2）

桌面应用使用 Tauri 2 管理 PyInstaller 打包的 FastAPI Sidecar。Vue 构建产物
直接内嵌到 WebView，Rust 在后台选择随机本地端口、启动后端、执行健康检查，并在退出
时清理后端进程树。桌面端使用本地 SQLite 数据库，无需安装 PostgreSQL。

## Windows 本地构建

需要预先安装 Node.js/pnpm、Python/uv、Rust stable，以及 Tauri 对应平台的系统依赖。
在仓库根目录执行：

```powershell
pwsh .\scripts\build-windows-installer.ps1
```

构建脚本会检查必要工具，并依次完成依赖安装、Vue 构建、PyInstaller Server 打包、
Sidecar 暂存和 Tauri NSIS 打包。重复构建时可以用 `-SkipInstall` 跳过依赖安装，
用 `-OpenOutput` 在成功后打开产物目录：

```powershell
pwsh .\scripts\build-windows-installer.ps1 -SkipInstall -OpenOutput
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

## AI 扩展包

AI 运行时作为独立扩展包发布，不增加基础安装包体积。桌面设置页支持在线安装、断点续传、
暂停/重试、SHA-256 校验、离线导入和卸载。Tauri 在本地启动固定生命周期的 AI Gateway，
主 Server 始终连接 Gateway；OCR、票据识别或图片分类首次请求时才按需启动已安装的 AI
Sidecar，空闲十分钟后自动退出。日志写入桌面数据目录下的 `logs/ai.log` 和
`logs/ai.err.log`。

在线安装依赖对应版本 GitHub Release 中的 `ai-extensions.json` 和平台扩展包。在预发布阶段，
也可以从 GitHub Actions 下载 `.tar.gz` 扩展包，在设置页选择“离线导入”。

## 当前 SQLite 边界

SQLite 首轮覆盖用户/认证、照片、相册、标签、元数据、任务和向量存储；PostgreSQL 专属统计
查询需要逐项补充方言实现。该边界不影响服务端完整版的远程 AI 配置，也不改变已有 AI 模型
与数据库数据。
