# TrailSnap Desktop（Tauri 2）

桌面应用使用 Tauri 2 管理 PyInstaller 打包的 FastAPI Sidecar。Vue 构建产物
直接内嵌到 WebView，Rust 首次分配并保存服务端口、启动后端、执行健康检查，并在退出
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

桌面 CSP 单独通过 `style-src-attr 'unsafe-inline'` 允许元素的内联样式。
Tauri 会为入口 HTML 的 `<style>` 注入 hash/nonce，此时 `style-src` 中的
`'unsafe-inline'` 不再允许元素的 `style` 属性。位置相册的天地图照片标记、
轨迹缩略图和数量/日期标签依赖这些属性；缺少独立指令会导致照片尺寸和叠加布局失效。
此配置保留 Tauri 对脚本与样式表的 CSP 处理，修改后需要重新构建桌面应用才能生效。

3D 足迹使用 Cesium：`worker-src 'self' blob:` 允许其本地计算 Worker 与
跨来源 Worker 的 Blob 引导脚本；当前 Cesium 的 Knockout 和 WebAssembly
依赖需要 `script-src` 中的 `'unsafe-eval'`。`connect-src` 仅额外允许
`https://elevation3d.arcgis.com`，用于可选的 ArcGIS 三维地形。
调整 CSP 时需同时验证内置 Natural Earth 底图、天地图影像与地形开关，
避免只显示城市和连线而不显示地球底图。

天地图 SDK 及其子脚本、样式表由本地 Server 的 `/api/system/map-proxy/`
代理返回。桌面页面与 Server 不同源，Server 端口还会动态分配，因此
`script-src` 与 `style-src` 均需允许 `http://127.0.0.1:*`。
仅在 `connect-src` 中允许本地请求不会放行 `<script>` 或 `<link rel="stylesheet">`，
缺少对应指令时会出现 `Failed to load map script`。

安装与卸载前，NSIS hook 会按安装目录关闭旧桌面程序并清理残留的 Server、
AI 与 llama-server 进程。PyInstaller 子进程可能在窗口被强制关闭后继续运行，
占用 Pillow `.pyd` 等运行库；仅关闭桌面窗口不足以确保可覆盖安装。
清理仅匹配安装目录内的应用进程，不操作照片库文件或其他目录中的同名进程。

## 修改数据目录

桌面客户端的 **设置 → 数据目录** 支持选择空文件夹（也可输入绝对路径创建目录），
例如 `D:\TrailSnapData`。保存后可取消迁移或使用“安全重启并迁移”。准备期间停止接收新请求，
等待已接收的上传、当前后台任务、定时任务、模型下载和扩展安装结束，待执行任务重启后继续。
等待期间不要强制关闭应用；只有服务安全退出后才授权迁移。直接退出或异常中断后，
下次启动保留原目录并提示重新保存设置、进行安全重启。设置页支持直接打开当前数据目录。
未完成的分块上传后续请求会被拒绝并提示失败，已保存分块随数据迁移；重启后可重试上传或备份。
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

## 手机连接

后端监听局域网，首次分配的端口保存在 `TrailSnap-desktop.json`，以后重启和迁移沿用。
端口被占用时启动报错，不会悄悄更换端口。设置 → 连接手机 App 提供局域网地址和二维码；
手机保存地址后可继续连接并备份照片。电脑需保持运行，系统防火墙需允许专用网络访问。
电脑 IP 由路由器分配，改变时可重新扫码或通过手机的 mDNS 自动查找；建议配置 DHCP 地址保留。
连接二维码只包含地址，手机仍需使用已有账户登录。首次使用可在桌面“用户管理”中为
`desktop-admin` 重置密码，手机使用此账号即可备份到同一照片库。
照片查看器“更多”菜单支持在文件管理器中定位原文件。

## AI 扩展包

AI 运行时作为独立扩展包发布，不增加基础安装包体积。桌面设置页支持在线安装、断点续传、
暂停/重试、SHA-256 校验、离线导入和卸载。Tauri 在本地启动固定生命周期的 AI Gateway，
主 Server 始终连接 Gateway；OCR、票据识别或图片分类首次请求时才按需启动已安装的 AI
Sidecar，空闲十分钟后自动退出。日志写入桌面数据目录下的 `logs/ai.log` 和
`logs/ai.err.log`。

后台 AI 任务按类型分阶段处理，当前阶段完成后再切换到下一优先级类型；同类型
内部保留批量并行。切换模型类别前会等待推理结束并释放上一类别的模型缓存，
避免场景识别、人脸识别和特征提取模型共同驻留。CPU、IO 队列保留各自的并发调度。

在线安装依赖对应版本 GitHub Release 中的 `ai-extensions.json` 和平台扩展包。在预发布阶段，
也可以从 GitHub Actions 下载 `.tar.gz` 扩展包，在设置页选择“离线导入”。
Windows 下 llama.cpp 运行时由桌面壳直接从官方 GitHub Release 下载并做 SHA-256 校验，
不依赖 winget。

## 当前 SQLite 边界

SQLite 首轮覆盖用户/认证、照片、相册、标签、元数据、任务和向量存储；PostgreSQL 专属统计
查询需要逐项补充方言实现。该边界不影响服务端完整版的远程 AI 配置，也不改变已有 AI 模型
与数据库数据。
