# TrailSnap Desktop（Tauri 2）

桌面应用使用 Tauri 2 管理 PyInstaller 打包的 FastAPI Sidecar。Vue 构建产物
直接内嵌到 WebView，Rust 首次分配并保存服务端口、启动后端、执行健康检查，并在退出
时清理后端进程树。桌面端使用本地 SQLite 数据库，无需安装 PostgreSQL。

## Windows 安装版与 ZIP

安装包安装完成或 ZIP 解压后，运行根目录 `TrailSnap.exe`（安装快捷方式也进入同一启动器）。首次启动会生成当前文件夹的
`instance.json` 和 `userdata/`；`app/<build-id>/` 只存程序版本。不同文件夹拥有
独立图库、配置、端口、浏览器数据、模型和认证密钥，可同时使用。移动文件夹前使用
设置页“安全退出”；换盘符或换电脑后，托管照片和任务路径从当前实例重新解析。
仅支持同平台、同架构且满足系统要求的电脑，外部图库引用需要另行携带或重新配置。

当前图库配置由实际程序目录的 `instance.json` 决定，默认使用同级 `userdata/`，不会将环境变量或旧 AppData 指针直接作为当前图库。新版只读检查安装目录旁的旧 `data`、`%LOCALAPPDATA%/TrailSnap`、`%LOCALAPPDATA%/com.trailsnap.desktop` 和历史 `TrailSnap-desktop.json`，发现旧照片后提示用户确认。不会创建或修改被检查的旧库。无旧记录的新用户直接开始使用新图库。

**找回旧版本照片**：

1. 完全退出旧版本，点击首次提示的“检查旧照片”，或进入 **设置 → 数据目录 → 找回旧版本照片**。
2. 选择检测到的旧目录，或手动选择包含 `data` 文件夹的那一级。以前更改过保存位置时，选择改后的目录。旧磁盘离线、配置损坏或数据库不可读时会说明原因；选择 `data` 子目录会提示正确的上一级，不创建空库。
3. 点击 **检查照片** 并核对来源和照片数。检查只读，尚未导入。
4. 按需勾选 **同时备份其他文件夹中的原照片**；不勾选时仍依赖原磁盘。自定义存储的原图、缩略图、分块和配置一起复制，保持媒体读取与继续上传所需的目录结构。
5. 选择新的空文件夹（例如 `D:\行影集-旧照片`），点击 **检查可用空间**，查看含程序、外部原照片和数据库快照余量的空间需求。更改来源、目标或外部照片选项后需重新检查。
6. 点击 **导入并使用这些照片**。复制期间显示阶段及文件进度；原图库保留，不合并当前图库。当前图库已有照片时会额外提醒。
7. 新副本通过数据库、路径、可读照片抽样与真实启动验证后才切换。原启动入口保存目标位置和图库身份，之后原快捷方式也打开导入后的图库，正常更新不重复提示导入。手机需重新连接、登录。导入前若已有新照片，可在高级信息中切换到保留的原图库查看，再返回导入后的图库；两边不自动合并。

目标磁盘离线或目标身份改变时，原入口明确报错，不静默打开旧库或空库。移动导入后的整个文件夹后，应从新位置运行 `TrailSnap.exe`；原入口的绝对位置关联不会自动搜索磁盘跟踪移动。

**备份当前图库**：保存独立副本，完成后重启并继续使用当前图库，不改变启动关联。副本不会自动同步；完整备份需勾选复制其他位置的原照片。

**失败恢复**：目录预检失败可直接纠正。排空、安全退出或复制失败后提供“重启并恢复使用”。操作记录先于服务停止保存；中断后启动会提示继续处理。已发布副本可“重新验证并继续”，不重复复制；未完成的临时文件可清理后从头重试。清理仅删除本操作标识对应、带匹配标记的临时目录，原图库和已发布副本始终保留。复制未完成时不支持按文件断点续传。

安装覆盖导致旧 `data` 与新 `userdata` 共存时，复制排除新实例的数据、锁、浏览器缓存和程序目录。导入后仍将安装包覆盖至原安装位置时，新程序会转交实际图库目录，由该目录的启动器执行正常的备份、候选验证和失败回滚；较低版本不会自动降级。

两个发行格式都使用独立的 `portable-latest.json` 和签名 ZIP 更新。安全停止任务后备份数据库和配置，再验证候选程序；验证期间不开放写入。失败或断电后恢复旧程序及升级前快照；已提交的升级不会自动恢复旧快照。设置页显示失败原因与备份位置，失败版本不会自动重复下载，可手动重试。安装包覆盖安装同样通过启动器验证新版本。

移动前安全退出，并携带整个安装目录（包括 `instance.json`、`userdata/`、`app/`）。不要只移动 exe。配置损坏、数据盘不可用或数据库丢失会显示错误，不会自动建立空库替代。启动失败界面可以打开数据/日志目录并重启；修复前请保留原目录和备份。卸载仅删除程序，保留图库、配置和升级快照；多个安装目录的卸载项和快捷方式相互独立。

构建便携包：

```powershell
pwsh .\package\desktop\scripts\build-portable.ps1
# 已完成桌面和后端构建时仅打包
pwsh .\package\desktop\scripts\build-portable.ps1 -SkipBuild
```

标准包使用电脑已有的 WebView2。要构建离线完整包，可用 `-WebViewRuntime <Fixed Version目录>`
附带含 `msedgewebview2.exe` 的同架构运行时；其后续更新包也应包含对应运行时。
`userdata/` 不应放在网络共享上供多台电脑同时写入。配置或磁盘不可用时会明确报错，
不会回落到新的 C 盘空图库。

Docker 用户无需修改挂载、环境变量或目录。新的存储引用字段默认为 NULL，旧绝对路径保持
原有读写与查询行为；`start.py` 沿用原来的 PostgreSQL/SQLite Alembic 升级入口。
便携路径转换仅在桌面便携模式下执行，不在 Docker 普通升级中搬动或重写照片。

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

首次启动会在安装目录的 `userdata/data/trailsnap.sqlite` 创建数据库、执行独立的
SQLite Alembic 迁移并创建本地管理员。界面启动时会自动换取标准 JWT，因此看起来无需登录，
后端的用户隔离与鉴权行为仍与服务器端一致。运行日志位于安装目录的 `userdata/logs` 目录。

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

默认数据随安装目录存放在 `userdata/`。搬迁时安全退出后移动整个实例目录，重新运行该目录的 `TrailSnap.exe`。设置 → 数据目录可预检、复制当前图库或显式指定的旧图库，目标必须为空，不能与源目录或当前安装目录互相包含。源目录保留；复制失败时界面提供原因、目录入口和重新启动操作。符号链接、目录联接、不足的磁盘空间及不可用外部照片需要先处理。

高级用户可在停机并备份 `instance.json` 后修改其中的 `dataRoot`；相对路径从当前安装目录解析，绝对路径会继续依赖指定磁盘，因此不会随程序目录搬迁。不要让两个实例同时写同一数据目录；启动器会加锁阻止此操作。

## 手机连接

后端监听局域网，首次分配的端口保存在安装目录的 `instance.json`，以后重启和迁移沿用。
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

启动时读取当前 Server 的版本和最低支持的 AI 扩展版本，再获取该 Server 的
`v{serverVersion}` Release 中已有的 `ai-extensions.json`；也可点击“检查更新”。
已安装版本 ≥ Server 最低支持版本时继续使用，不自动下载、重装或降级。
低于最低支持版本时，只下载与 Server 同版本、匹配当前平台且带 SHA-256 的扩展。
未安装时仍由用户选择安装。如果清单或同版本附件不可用，低于最低版本的任务保持等待更新；
满足最低版本的已安装扩展不受清单失败影响。可通过 `TS_AI_EXTENSION_CATALOG_URL` 覆盖清单地址。

替换或卸载先停止新任务派发，等待推理、结果提交、Gateway 响应流与模型下载结束，再停止 Sidecar。
缺失或维护期间任务待执行，不消耗失败重试次数；安装完成后自动继续，用户主动暂停保持不变。
失败回滚旧安装，低于最低支持版本的旧运行时仍保持等待；替换事务日志在异常退出后恢复。
扩展操作互斥，照片、独立 `models` 目录与分析结果保留。

设置页显示客户端、Server、最低扩展版本、系统与架构，提供官方下载页和同版本平台附件的手动下载直链。
下载 `.tar.gz` 后无需解压，点击“离线导入”。没有附件时仍保留官方下载页。

### Server 最低版本与扩展发布

唯一的兼容性配置在 `package/server/app/service/ai_extension_state.py`：

```python
MINIMUM_AI_EXTENSION_VERSION = "0.17.3"
```

它表示当前 Server 最早支持的 AI 扩展版本，只在 Server 需要旧扩展没有的 API 或能力时提高，
不随每次产品版本机械递增。扩展的升级目标始终与当前 Server 同版本。
清单只保存扩展版本、平台附件 URL、SHA-256、文件名与大小，不再使用远端强制规则或客户端版本范围。
既有 Schema 1 清单可直接使用，无需为兼容判断更新历史 Release 的 JSON。

`Build Desktop AI Extension` 对正式 `v*.*.*` 标签、相关 PR 或手动运行构建。
工作流先运行 `package/ai/scripts/validate_extension_release.py`，确认 Server、AI 源码/运行时、
桌面和内置清单的版本一致，并校验最低版本不高于 Server；之后从 Server 版本生成扩展版本。
同版本压缩包与清单一起上传到本次正式 Release，不创建额外的 `ai-extensions` 或 `ai-v*` Release。
生成清单时检查三平台附件齐全、版本与链接正确且带 SHA-256；断点文件按扩展、平台与 SHA-256 隔离。

Windows 下 llama.cpp 运行时由桌面壳直接从官方 GitHub Release 下载并做 SHA-256 校验，
不依赖 winget。

## 当前 SQLite 边界

SQLite 首轮覆盖用户/认证、照片、相册、标签、元数据、任务和向量存储；PostgreSQL 专属统计
查询需要逐项补充方言实现。该边界不影响服务端完整版的远程 AI 配置，也不改变已有 AI 模型
与数据库数据。
