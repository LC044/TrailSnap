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
Tauri 安装包，产出 NSIS、DMG、AppImage 和 DEB。正式标签构建还会使用仓库 Secret
`TAURI_SIGNING_PRIVATE_KEY` 为更新包签名并发布 `latest.json`；客户端启动后自动检查、
后台下载并验签，下载完成后可一键安装。

## 修改数据目录

桌面客户端的 **设置 → 数据目录** 支持选择空文件夹（也可输入绝对路径创建目录），
例如 `D:\TrailSnapData`。保存后可取消迁移或立即重启；重启前建议等待任务和下载完成。
启动器会在 Server 和 AI 服务启动之前复制数据库、上传照片、缩略图、配置、模型、AI 扩展包、
llama.cpp 运行时和日志，并更新数据库及 JSON 配置中位于旧目录下的绝对路径。
外部图库和自定义到应用数据目录之外的存储位置不移动。

目标目录必须为空且有足够可用空间；新旧目录不能互相包含。复制完成后校验 SQLite 数据库并
切换目录，迁移失败则继续使用原目录，设置页显示错误。原目录保留为备份，确认照片、模型正常
后可自行删除。迁移过程中请勿关闭应用；大型图库迁移期间启动等待不会受通常的 60 秒限制。

Windows 的目录指针保存在 `%LOCALAPPDATA%\TrailSnap-desktop.json`，此小配置文件及同级
锁文件保留在默认位置。数据盘不可用时会报错，避免在 C 盘创建新的空图库。
Windows 同一用户的桌面客户端只允许一个实例使用这份目录配置，避免迁移时其他窗口写入。
数据目录内含符号链接或目录联接时迁移会停止，需要先处理这些链接。

## AI 扩展包

AI 运行时作为独立扩展包发布，不增加基础安装包体积。桌面设置页支持在线安装、断点续传、
暂停/重试、SHA-256 校验、离线导入和卸载。Tauri 在本地启动固定生命周期的 AI Gateway，
主 Server 始终连接 Gateway；OCR、票据识别或图片分类首次请求时才按需启动已安装的 AI
Sidecar，空闲十分钟后自动退出。日志写入桌面数据目录下的 `logs/ai.log` 和
`logs/ai.err.log`。

在线安装依赖对应版本 GitHub Release 中的 `ai-extensions.json` 和平台扩展包。在预发布阶段，
也可以从 GitHub Actions 下载 `.tar.gz` 扩展包，在设置页选择“离线导入”。
Windows 下 llama.cpp 运行时由桌面壳直接从官方 GitHub Release 下载并做 SHA-256 校验，
不依赖 winget。

## 当前 SQLite 边界

SQLite 首轮覆盖用户/认证、照片、相册、标签、元数据、任务和向量存储；PostgreSQL 专属统计
查询需要逐项补充方言实现。该边界不影响服务端完整版的远程 AI 配置，也不改变已有 AI 模型
与数据库数据。
