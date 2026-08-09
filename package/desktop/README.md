# TrailSnap Desktop（阶段 0）

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
