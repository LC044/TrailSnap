> 2026-10-14 修订：安装包与 ZIP 统一为安装目录内 instance.json + userdata + app 布局。不再自动读取 AppData 或环境变量指定的旧配置；旧库由用户在设置页显式选择并复制。下文涉及旧安装模式的描述属于原实施记录，现行使用规则见 [桌面说明](../package/desktop/README.md)。

# 桌面便携化与旧用户兼容实现方案

日期：2026-10-13。状态：Windows 便携实例、旧库转换、独立升级事务和服务端兼容代码已实现；验收结果见 `desktop-portable-verification.md`。本文件保留设计目标，实际交付边界以验收文档为准。

## 1. 目标和交付边界

Windows 首轮交付完整便携实例：一个文件夹包含程序、图库、配置、模型与扩展；不同文件夹可以同时运行、独立更新；整体移动后不依赖原路径和原 Windows 用户。继续支持现有安装版，普通升级保持其原数据位置。macOS/Linux 保持现有发行方式，本轮共享路径与数据库改动必须通过其回归测试，暂不宣称跨系统便携。

便携指同平台、同架构、满足最低系统要求的电脑之间移动。已有外部图库默认继续引用，只有复制进入实例的原文件才能随实例移动。移动硬盘必须在应用安全退出后拔出。运行中拔盘只能停止写入、报告错误和尝试恢复，不能保证文件系统不会损坏。

## 2. 当前代码与可复用能力

| 入口 | 当前行为 | 改造方向 |
| --- | --- | --- |
| `package/desktop/src-tauri/src/data_directory.rs` | Windows 全用户共用目录指针、锁和端口 | 实例配置解析、实际图库锁、旧配置桥接 |
| `package/desktop/src-tauri/src/lib.rs` | 自动创建窗口、启动服务、准备目录迁移 | 先解析实例，再建独立 WebView；统一维护模式 |
| `package/server/app/utils/desktop_data_migration.py` | 停服务后复制，改写绝对路径，SQLite quick_check，成功后切换 | 保留暂存与校验能力，增加显式字段转换、清单和恢复日志 |
| `package/server/desktop_entry.py` | 启动时直接 Alembic upgrade | 迁移前备份、版本检查、更新验证启动模式 |
| `package/website/src/components/DesktopUpdatePrompt.vue` | 下载后直接调用 updater.install() | 通过桌面 API 按发行模式路由更新 |
| `.github/workflows/build-desktop.yml` | Windows NSIS 与原有 latest.json | 保留安装版产物，增加便携 ZIP 与独立签名更新清单 |

已有目录迁移的任务排空、单次授权、失败保留原目录可以复用。现有通用字符串重写只作为旧绝对路径兼容工具，不作为便携路径格式，也不在所有 JSON 中盲目替换。

## 3. 目录布局：稳定入口与版本目录

```text
TrailSnap-家庭/
├─ TrailSnap.exe                         小型启动器，路径以自身位置为基准
├─ instance.json                        实例配置与当前程序版本指针
├─ app/
│  ├─ <build-id>/                        不可变程序版本，包含桌面壳、server/、清单
│  └─ <previous-build-id>/               上次成功版本，更新验收后按策略清理
├─ userdata/                            兼容现有桌面 root 的内部布局
│  ├─ library.json                      图库 ID、路径格式与兼容版本
│  ├─ data/                             SQLite、用户目录、配置、模型等现有布局
│  ├─ ai-config.json                    保持现有位置
│  ├─ ai-extensions/                    包含已安装扩展、下载缓存与事务日志
│  ├─ runtime/                          llama.cpp 等托管运行时
│  ├─ webview/                          当前实例的浏览器配置与缓存
│  ├─ logs/
│  ├─ backups/<transaction-id>/         数据库、配置备份及恢复清单
│  └─ .instance.lock                    OS 文件锁，文件是否存在不代表锁已占用
└─ maintenance/
   ├─ transaction.json                  更新或转换事务，含操作类型、阶段和版本
   └─ staging/                          下载与解压暂存
```

不在本轮重新组织现有 `data/users/`、模型等内部布局。`userdata` 直接作为现有 `TS_DESKTOP_ROOT`；`TS_DATA_DIR` 继续为 `userdata/data`。所有资源从当前版本程序目录读取，所有持久化写入从明确的数据路径读取；不使用 shell 工作目录推导安装位置。

便携 ZIP 带发行模式标记和默认程序清单，不带图库身份、JWT 密钥或已初始化用户数据库。首次初始化生成这些内容；已初始化配置丢失或损坏时进入恢复界面，不自动覆盖为新图库。

## 4. 实例配置和启动选择

示例 `instance.json`（版本号和 ID 为占位值）：

```json
{
  "schemaVersion": 1,
  "mode": "portable",
  "instanceId": "<uuid>",
  "displayName": "家庭图库",
  "activeBuild": "<build-id>",
  "previousBuild": null,
  "dataRoot": { "kind": "relative", "path": "userdata" },
  "network": { "mode": "auto", "preferredPort": null }
}
```

配置采用临时文件、flush、平台替换 API 保存；事务跨文件修改依靠日志恢复，不能把多次 rename 称为整体原子操作。版本目录指针必须由清单中的合法 build ID 构造，不接受任意路径。

启动选择规则：

1. 官方便携入口通过明确的参数将实例配置位置交给桌面壳；桌面壳验证入口与实例关系。存在明确便携模式但配置损坏时停止启动，不回落到旧 AppData。
2. 原安装版入口进入 `legacy-installed` 模式，继续读取 `%LOCALAPPDATA%/TrailSnap-desktop.json`；旧配置存在时严格沿用 root、pendingRoot、previousRoot、migrationError、serverPort。
3. 旧配置未创建但 `%LOCALAPPDATA%/TrailSnap` 有数据的情况仍识别为旧布局，不新建便携库。首次干净安装的便携发行包只初始化自己的目录。
4. 开发模式使用单独明确配置；禁止调试启动默认接管用户生产图库。

原安装版保留旧配置锁作为兼容锁，同时新增实际图库锁。便携版锁定解析和规范化后的实际 `userdata`，避免两个入口指向相同图库。新旧客户端并发写入保护还需桥接版本：旧版不识别新图库锁，转换源必须同时持有旧锁并确认旧服务退出。

## 5. 运行流程与隔离

```text
启动器恢复未完成事务
  → 验证实例配置与版本清单
  → 锁定实际数据目录（维护期间锁不得出现空窗）
  → 检查磁盘、目录可写性、数据库兼容版本
  → 解析所有运行路径
  → 创建当前实例的 WebView
  → 启动 AI Gateway 与 Server
  → 校验当前子进程健康状态及图库身份
  → 开放界面与后台任务
```

新增 Rust `instance.rs` / `instance_lock.rs`，提供 `InstanceContext`：发行模式、实例 ID、图库 ID、安装根、当前程序根、数据根、缓存根、端口策略。`data_directory.rs` 保留现有 API 外观，内部委托给它，避免前端一次性改掉全部调用。

便携启动器作为无可见控制台的常驻父进程，自正常启动到更新完成都持有图库 OS 锁；桌面壳通过受当前用户权限保护、含随机 token 的本地控制通道确认锁租约，不重复打开排他锁，也不凭一个命令行布尔值跳过锁。直接启动内部桌面 exe 应重新进入启动器。桥接安装版直接运行时由桌面壳持锁；其原 NSIS 更新保留旧配置锁保护并加入维护标记。Windows 下由启动器 Job Object 跟踪本实例进程树，启动器异常退出时关闭其子进程，重新取得锁前还要验证并清理孤儿写者；不能按全局进程名结束其他实例。

Tauri 配置主窗口设置 `create: false`，在 setup 解析路径后用 `WebviewWindowBuilder::from_config(...).data_directory(...)` 创建，保持 `main` 标签和现有能力配置。失败启动提供原生错误/恢复入口，不能因为业务 WebView 未创建而静默退出。

WebView profile 属于当前实例，但不作为权威业务数据。跨电脑/Windows 用户后旧 profile 可能因系统加密或运行时变化无法复用，允许备份并重建，再用本地桌面认证恢复会话；需保留的主题等偏好写入业务配置。便携不承诺 Windows/WebView2 不产生任何系统级缓存。

新图库生成随机 JWT 密钥并保存在自己的系统配置中。转换原图库保留现有账户和有效配置；从默认固定密钥升级为随机密钥应明确说明手机需要重新登录。运行期桌面会话 secret 继续每次启动生成。原文件夹搬迁保留身份，显式“复制为独立图库”生成新的实例/图库身份与密钥，并清除旧会话。

手工复制文件夹会连同 ID 一起复制，离线条件下无法可靠自动区分“搬家”和“克隆”。同机检测到身份重复且根目录不同可提示复制为独立图库，不能仅因路径变化自动改变图库 ID。

## 6. 路径设计：存储根与相对路径

新增 `StorageRoot` 表：`id`、`owner_id`、`name`、`kind`（`managed` / `instance-relative` / `external`）、`location`、创建时间。托管根的位置相对实例数据根；外部根保留明确的绝对路径。根 ID 不因盘符变化而改变。

`Photo` 新增可空 `storage_root_id`、`storage_relative_path`。保留现有 `file_path` 字段兼容旧数据与旧 API；新代码将新字段视为权威，两字段不全或非法组合必须报错，不悄悄使用陈旧绝对路径。旧字段可在写入时保留实际路径用于过渡，但转换后不能允许旧程序打开新图库。

增加 `(owner_id, storage_root_id, storage_relative_path)` 查询索引；去重与扫描按此组合匹配，并统一大小写/分隔符的比较策略。是否设置唯一约束先核对现有重复记录语义与历史数据，不把索引创建失败当作自动删除重复照片的理由。StorageRoot 与所属用户的完整性在迁移及读写入口均检查。

数据库结构先做增量迁移，旧照片的新字段保持 NULL，桥接版不自动全量重写。显式便携转换时按已知存储根填充新字段，采用最长匹配根、完整目录边界、Windows 大小写规则。与 ORM 修改对应的 PostgreSQL 和 SQLite Alembic 迁移必须同时提交，同一 PR 每个数据库仅保留一个迁移文件。

新增 `package/server/app/service/storage_paths.py`，对外提供：

```python
encode_path(owner_id, absolute_path) -> StoredPath
resolve_path(owner_id, root_id, relative_path) -> Path
resolve_photo_path(photo) -> Path
resolve_legacy_path(owner_id, file_path) -> Path
```

规则：相对路径统一 `/`，拒绝绝对路径、驱动器路径、`..`、NUL 和逃逸根目录的链接；读写权限按 root.owner_id 检查，系统托管根需由服务显式授权。路径编码失败不自动把照片移动到其他目录。外部根不可用时返回“需要重新定位”，扫描任务不得把磁盘离线视为照片删除。

必须一起改造的调用点：

| 领域 | 代码范围与处理 |
| --- | --- |
| 原图、视频、Live Photo、缩略图 | `app/api/media.py`、`app/service/storage.py`：文件 IO 前解析，配对路径按同一根构造 |
| 上传、覆盖、重命名、整理、回收站 | `app/crud/photo.py`、`app/api/photo.py`、任务策略：写入时编码，删除时解析并验证根 |
| 扫描、去重、目录检索 | `crud/photo_paths.py`、扫描任务、搜索与存储 API：按根 ID + 相对目录查询，不依赖旧绝对路径的字符串前缀 |
| 任务队列与子进程 | `api/tasks.py`、`service/tasks/*`、`service/jobs/*`：照片任务存 photo_id，文件夹任务存根引用；子进程执行前解析 |
| 用户设置与扫描计划 | `user_storage.py`、配置管理：存根引用，旧配置使用兼容解析器，不直接 `abspath()` 新格式 |
| 本地模型与 AI 配置 | AI 扩展、Gateway、模型服务：字段级路径引用；托管运行时优先，外部程序显式选择 |
| 导出、每日回忆、Agent 工具 | 文件 IO、路径展示、目录过滤使用同一解析器；只对外返回明确需要的路径 |

已有任务载荷、元数据 JSON、系统配置中的路径建立字段清单和转换适配器。照片任务恢复优先重新从 photo_id 获取位置；无法解释的未知路径载荷保留并暂停对应任务，提供诊断，禁止盲目执行。新路径格式完成全部读写适配前不得开放转换按钮。

## 7. 端口与手机连接

原安装版原有 serverPort 作为固定端口继续沿用，保持已有手机地址。便携新实例默认 auto：优先 preferredPort，不可用则分配并持久化新端口。用户选 fixed 时冲突明确报错，不自动换端口。

当前“临时 bind 后释放再启动”的做法存在竞争；Server 实际绑定失败需返回明确错误，auto 模式有限重试，fixed 模式失败停止。健康检查必须证明响应来自本次启动的服务，包含图库 ID、启动随机 nonce 及子进程状态校验，不能把占用端口的另一实例当成启动成功。

`service/discovery.py` 的服务名称、`server=trailsnap.local.` 改为实例唯一名称/主机名，TXT 增加图库 ID 与显示名称。同身份副本使用独立运行标识避免同机公告冲突；移动端不能只依赖不唯一的图库 ID 自动选中未知副本。移动端保存稳定图库身份，发现地址变化后校验身份再更新；现有账号仍需认证。

## 8. 旧用户升级和显式便携转换

普通升级仅进行兼容结构升级，不移动照片、不改目录指针、不触发全量路径转换。数据库迁移前创建快照，失败显示恢复入口，保持旧目录信息。已有 pendingRoot 必须遵循当前安全授权与迁移顺序，便携转换与旧目录迁移不能同时执行。

转换向导提供：目标空目录、数据总量、复制空间需求、外部引用清单、“保持外部引用”或“复制外部照片”。模型与扩展默认一起复制。预检只读取，不创建目标有效图库、不修改源配置。

事务阶段：

```text
planned → draining → copying → converting → verifying
        → target_ready → committed
失败：failed（保留源，记录可恢复阶段）
```

执行步骤：

1. 持有旧配置锁与源图库锁，阻止更新、扩展操作和其他迁移。
2. 复用现有 prepare-migration 排空上传、执行中的任务、定时任务、模型下载、AI 与 llama 写入；未执行任务随队列保留。
3. Server 与 AI 全部退出后建立源快照；在目标同卷的 staging 中复制目录和选定外部文件。
4. 生成可恢复清单：相对文件名、长度、SHA-256；断点重试必须重新验证源快照与已复制文件，源已变化则旧阶段作废。
5. 在目标副本中转换显式路径字段和已知配置；不要修改源数据库。对数据库用 integrity_check 和 foreign_key_check，核对各用户照片、相册关联、标签、任务统计与原文件哈希。源已有丢失文件记录单独报告，不伪装成迁移新损失。
6. 使用目标新程序以验证模式启动：禁止业务写入、定时任务和扫描清理，检查账户、原图、视频、Live Photo、缩略图和可用扩展；模型硬件不兼容明确报告，不误判为图库损坏。
7. 目标验证通过才发布目标配置和完成记录；记录源与目标归属，提供新启动入口。源目录保留；随后允许用户从目标正常打开图库。
8. 新桥接客户端再次从原入口启动时显示“图库已转移”，跳转目标或明确恢复源副本，不静默打开陈旧数据。桥接版之前的老程序不认识此标记，不能彻底阻止其打开源；转换验收必须包含旧入口替换和旧进程关闭。

回退分界：目标开放业务写入前可安全取消转换并恢复源；开放后源只作为历史备份。此后回退应执行反向迁移或恢复明确时间点，不能自动用源覆盖目标的新照片。跨卷没有整体原子切换，依靠目标完成标记和源记录幂等恢复。

## 9. 便携更新：切程序指针，带数据保护

新增 `update_manager.rs`，前端通过 `src/api/desktopUpdates.ts` 和 Pinia 调用原生命令：检查、下载、准备、应用、状态。业务 UI 不接触更新包路径或自定义 shell 命令。legacy-installed 仍使用安装包，但安装前补安全排空与数据库备份；portable 只使用便携更新包。

签名更新清单至少包含 schemaVersion、产品/模式、平台/架构、版本、build ID、包大小、SHA-256、签名、最低启动器版本、支持的数据库/路径格式范围。签名覆盖清单与包内容摘要，校验使用客户端内置公钥；不能只校验远端返回的裸 SHA-256。ZIP 解压拒绝路径逃逸、链接和超限解压。

便携包只包含一个完整 `app/<build-id>` 与程序清单，不包含 instance.json、userdata 或用户内容。更新包校验后的目录保持不可变；不得覆盖运行中的 exe/DLL。当前安装版 latest.json 和 Windows NSIS 产物保留，便携版用独立清单，防止旧客户端收到 ZIP。

更新阶段：

```text
downloaded → verified → draining → backed_up
           → switched → validating → committed
失败：rolling_back → rolled_back；恢复失败：needs_recovery
```

1. 下载、解压和签名检查可以在应用运行时完成，不改变当前版本。
2. 安全排空并退出当前实例所有服务；启动器或维护 helper 持有实例锁，期间启动请求只显示维护状态，不允许第二进程写库。
3. 持久化恢复日志；用 SQLite backup API 备份主库、railway 库，备份系统/用户/AI/扩展配置及图库格式标记，flush 后才进入 switched。
4. 切换 activeBuild，启动候选版验证模式；先检查未知/更高 schema，拒绝不支持的格式，不执行自动降级。
5. 候选版执行 Alembic 并做业务只读检查。验证期间禁用模型自动更新、扩展 reconcile 写入、旧用户目录搬迁、扫描删除、任务派发与普通写 API；本轮升级不允许无恢复记录地移动/删除原文件。
6. 启动器验证当前子进程、图库 ID、nonce、数据库版本与代表性媒体读取；大型数据库迁移显示阶段进度，不套用现有固定 60 秒启动失败判定。
7. 验收通过先持久化 committed，再发送放行命令开放写入。committed 后异常不自动恢复旧快照，以免丢失新增数据。
8. 验收前失败时完全停止候选版，恢复数据库与配置集合，切回旧 build 并验证。restore 中再次断电仍可从日志重试；恢复失败保持维护状态，不启动半恢复数据。

数据库修改后的兼容性与数据文件修改必须作为同一事务设计。若某版本必须变换原文件，采用复制后发布与明确文件恢复日志，不允许简单“备份 DB 后任意执行启动迁移”。大模型、原照片在普通程序更新中不复制；更新验收禁止对它们做破坏性修改。

第一版启动器保持稳定接口，签名清单中 minLauncherVersion 超出支持范围时提示下载新版启动器，不偷偷替换正在运行的入口。以后需要启动器自动更新，再单独设计 helper 替换事务。

## 10. 打包、系统依赖与用户界面

新增 `package/desktop/scripts/build-portable.ps1`：从 Tauri 编译产物、完整 PyInstaller onedir 和内置资源构造版本目录；禁止只打包单个桌面 exe。产物建议：便携完整 ZIP、便携程序更新 ZIP、对应签名和更新清单。CI 从解压后的最终发布结构启动验收，不能只测试源码。

Windows WebView2 两档：标准便携包依赖电脑已安装的兼容运行时，缺失时明确引导安装；离线完整包可随带 Fixed Version。Fixed Version 的包体、系统支持与安全更新责任需要实际构建验证。其他原生依赖同样在干净电脑验收后才能声明“解压即用”。

设置页在现有数据目录功能基础上显示：发行模式、实例名、程序位置、数据位置、外部存储、当前更新/迁移状态。便携模式提供打开实例目录、转换/导入、复制为独立图库、安全退出；改用外部数据根后显示“包含外部依赖”，不再声称整个文件夹就是完整备份。实例名进入窗口标题和手机连接页面。

便携实例放在不可写目录时报告具体目录并提供移动到可写位置的指引，不静默回落 C 盘。安全退出排空后台任务再终止进程，完成后提示可以拔盘。NTFS/exFAT 等本地盘分别验收；FAT32 的单文件限制提前检查。网络共享文件夹不纳入首轮多电脑并发支持范围。

## 11. 按依赖拆分的实施批次

| 批次 | 交付 | 完成条件 |
| --- | --- | --- |
| A：兼容与身份基础 | InstanceContext、发行模式、图库锁、WebView 隔离、身份/端口策略；旧配置不迁移 | 两实例同时运行；旧配置与原端口保持；同库第二写者被拒绝 |
| B：路径兼容层 | StorageRoot 与增量字段、统一解析器、全部 IO/SQL/任务适配、两数据库迁移 | 旧绝对路径回归通过；新格式读写全链路可用；仍不开放用户转换 |
| C：程序更新事务 | 稳定启动器、签名便携包、日志恢复、验证模式、成套回退 | 更新每个阶段故障注入通过；已开放写入后禁止自动旧快照回退 |
| D：显式转换与复制 | 空目录转换、外部照片选择、清单、恢复、旧入口转移标记 | 源不变、目标完整、改盘符/换用户后照片和任务可用 |
| E：发行与验收 | 设置页、完整 ZIP、离线运行时选项、CI 和文档 | 最终产物在干净电脑与移动硬盘验收后发布 |

每批可独立评审，但仅 A+B 不等于可发布的便携版。原安装版桥接可以先发布，完整便携体验必须至少完成 A–E 的标准包闭环，更新保护不能延期。

### 11.1 具体文件清单

| 文件/模块 | 改动 |
| --- | --- |
| 新增 `package/desktop/launcher/` Rust crate | 稳定入口、实例锁、控制通道、版本指针、进程监管、启动与恢复 |
| 新增 `src-tauri/src/instance.rs`、`instance_lock.rs` | 上下文、配置格式、旧布局识别与锁租约校验 |
| 新增 `src-tauri/src/maintenance.rs`、`update_manager.rs` | 共用排空、更新互斥、验证模式、阶段状态与恢复 |
| 修改 `src-tauri/src/lib.rs`、`data_directory.rs`、`tauri.conf.json` | 动态建窗、实例参数、命令注册、路径解析、错误恢复 |
| 修改 `ai_extension.rs`、`ai_gateway.rs`、`llama_runtime.rs` | 根路径与运行时选择、验证期间禁止写操作、进程归属 |
| 新增 `package/server/app/db/models/storage_root.py`、修改 `photo.py` | 存储根和兼容字段，补模型注册与关系 |
| 新增 `app/service/storage_paths.py` | 编码/解析、所有权校验、外部根可用性与路径比较 |
| 修改 `desktop_entry.py`、桌面 system API、任务启动入口 | 数据版本保护、快照、验证模式、放行、启动身份 |
| 修改第 6 节列出的 API/CRUD/任务/配置模块 | 全部路径 IO 与 SQL 比较迁移到统一约定 |
| 修改 `desktop_data_migration.py`、新增显式转换适配器 | 文件清单、路径字段转换、断点恢复、完整性报告 |
| 修改 `service/discovery.py` 与移动端发现/连接逻辑 | 实例唯一公告、稳定身份、地址更新与副本提示 |
| 修改 `src/api/desktopDataDirectory.ts`、对应 store 与设置页 | 实例信息、迁移预检/进度/恢复与外部引用列表 |
| 新增 `src/api/desktopUpdates.ts`、更新 store；修改更新提示组件 | 统一更新状态，安装版与便携版原生命令路由 |
| 两套 Alembic、新增两套路径/恢复/发布产物测试 | 双数据库结构兼容、故障恢复、实际包运行验收 |
| 构建脚本、Windows hooks、`build-desktop.yml`、README | 便携 ZIP、清单签名、桥接产物、更新和卸载数据边界 |

表内 Rust `src-tauri/` 相对于 `package/desktop/`；前端 `src/` 相对于 `package/website/`；后端 `app/` 相对于 `package/server/`。以上新增路径是实施计划，当前尚未创建。

### 11.2 接口契约

保留 `desktop_data_directory`，增加 `mode`、`instanceId`、`libraryId`、`displayName`、`installRoot`、`portableComplete` 和外部根统计；实际路径仅向本地设置界面提供。

新增 Tauri 命令：`desktop_instance_info`、`desktop_migration_preview`、`desktop_migration_start`、`desktop_migration_status`、`desktop_update_check`、`desktop_update_download`、`desktop_update_apply`、`desktop_update_status`、`desktop_safe_exit`。迁移预检返回 planId、源版本标识、所需空间、外部根清单和阻塞项；执行时重新验证该计划，不接受过期预检直接写入。

长操作返回 transactionId，事件携带 phase、progress、message、recoverable；日志落盘为权威状态，重启后 UI 可查询。执行操作共享维护互斥锁，重复 transactionId 幂等，不允许更新、迁移、扩展替换并发。

新增/扩展后端本地维护 API 必须继续使用 `BaseResponse[T]` 与 `success()` / `fail()`。验证放行命令使用本次启动 secret 和 nonce，不向普通 LAN 用户开放；上传与写 API、任务调度、定时器、启动 reconcile 都必须检查共同维护状态，不能只靠按钮禁用。健康检查增加认证的运行身份信息，避免泄露本地 secret。

## 12. 测试与发布门槛

本地和 CI 统一通过 `tests/scripts/run-tests.ps1`，环境来自 `tests/.env.test` / CI 模板。现有 desktop component 仅支持 unit；新增发布产物测试应扩展统一入口与 desktop integration 支持，不另造绕开入口的测试脚本。新增测试重点为状态恢复和数据完整性，不复制实现逻辑。

基础回归命令：

```powershell
pwsh .\tests\scripts\run-tests.ps1 -Layer unit -Component desktop -Level all
pwsh .\tests\scripts\run-tests.ps1 -Layer unit -Component server -Level all
pwsh .\tests\scripts\run-tests.ps1 -Layer unit -Component website -Level all
pwsh .\tests\scripts\run-tests.ps1 -Layer e2e -Level p0
```

必须覆盖：

- 旧默认目录、旧自定义目录、未创建指针但已有库、pendingRoot、配置损坏、盘离线；均不能错误初始化空库。
- 两实例并发上传/AI/更新，更新 A 不终止 B；两个不同入口访问同库时第二写者失败，重启和锁交接无空窗。
- 盘符、目录名、Windows 用户变化；中文/空格/长路径；所有媒体种类及外部图库重新定位。
- 复制图库后账号、实例身份、JWT 和手机发现不会误连；原图库搬迁保留正确身份。
- 重复扫描不新增重复照片；目录搜索、重命名、回收站、导出、任务恢复读取正确文件。
- 磁盘满、只读、断电、锁残留、端口被占用、数据版本过高；未知任务载荷安全暂停。
- 每个迁移/更新阶段强制退出后幂等恢复；数据库校验/外键校验失败不开放写入；恢复过程中再次中断也可恢复。
- 旧版数据库升级、新版拒绝不兼容降级、NSIS 兼容更新；原图哈希、各用户记录和任务数量不丢失。
- 最终 ZIP 在未安装开发工具的干净 Windows 与实物移动硬盘上运行；WebView2 缺失与独立运行时情况分别验收。

发布先使用小型预览图库验证，再用真实历史布局的脱敏副本验收。记录构建 ID、迁移清单、数据库快照版本与测试结果；完成前不承诺“更新绝不会出错”，保证的是不静默换库、可定位失败、开放写入前可恢复。

## 13. 官方参考

- [Tauri WebviewWindowBuilder：data_directory 与 from_config](https://docs.rs/tauri/latest/tauri/webview/struct.WebviewWindowBuilder.html)
- [Tauri Updater：签名与平台安装产物](https://v2.tauri.app/plugin/updater/)
- [WebView2 用户数据目录](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/user-data-folder)
- [WebView2 分发与 Fixed Version](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)
