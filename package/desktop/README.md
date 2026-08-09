# TrailSnap Desktop（阶段 0 + 阶段 2 AI 扩展）

桌面原型使用 Electron 管理 FastAPI sidecar，并通过随机本地端口同源提供 Vue 页面和
`/api` 反向代理。当前阶段仍依赖 PostgreSQL，尚未包含阶段 1 的 SQLite 改造。

## Windows 本地构建

在仓库根目录执行：

```powershell
pwsh .\package\desktop\scripts\build.ps1
```

安装包输出到 `package/desktop/dist/TrailSnap-*-Setup.exe`。默认数据库地址为
`postgresql://trailsnap:trailsnap@127.0.0.1:5532/trailsnap`，首次启动会生成
`%LOCALAPPDATA%\TrailSnap\data\.env`，也可通过 `TS_DB_URL` / `DB_URL` 和
`RAILWAY_DB_URL` 环境变量覆盖。运行日志位于
`%LOCALAPPDATA%\TrailSnap\logs`，持久数据位于 `%LOCALAPPDATA%\TrailSnap\data`。

阶段 0 的应用安装包不会安装 PostgreSQL；可复用仓库 `docker-compose.yml` 中的
PostgreSQL 服务。GitHub Actions 会在三个原生 runner 上分别构建 Windows NSIS、
macOS DMG，以及 Linux AppImage/DEB。

## AI 扩展包

基础安装包不包含 AI 运行时。AI 扩展包内置 RapidOCR 随包提供的小型资源；图片
分类和票据识别模型在运行时直接从 ModelScope 下载到
`%LOCALAPPDATA%\TrailSnap\models`。桌面设置中心的
“AI 扩展包”支持：

- 在线下载、SHA-256 校验、进度显示、暂停和断点续传；
- `.tar.gz` 扩展包离线导入与平台校验；
- 独立安装或卸载运行时，模型与 PostgreSQL 分析结果均不会随之删除；
- 通过 Server 鉴权接口查看、下载、重试和删除 AI 模型；
- OCR、票据识别、图片分类首次请求时启动 AI Sidecar；
- 空闲 10 分钟自动退出，关闭桌面应用时清理整个进程树。

扩展清单默认从当前版本对应的 GitHub Release 读取，也可通过
`TS_AI_EXTENSION_CATALOG_URL` 指向镜像源。GitHub workflow
`build-desktop-ai-extension.yml` 在 Windows、macOS 和 Linux 原生 runner 上分别构建
CPU 扩展，并在版本标签发布时生成带精确版本、大小和 SHA-256 的
`ai-extensions.json`。ModelScope 模型不再重复制作 GitHub Release 资源包。
