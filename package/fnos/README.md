# 飞牛 fnOS 安装包

GitHub 安装包 CI 的打包源，仅支持 x86 CPU。最终文件名为 `TrailSnap-<产品版本>-fnos-x86.fpk`，manifest 版本为 `<产品版本>-<打包修订>`。

## 本地构建

需要 Python 3.12+ 和官方 fnpack 1.2.3。工具地址及 SHA256 记录在 `fnpack.json`，执行前必须校验。源码中的产品版本从 `package/server/pyproject.toml` 读取。

在仓库根目录执行，示例版本应替换为当前产品版本：

```bash
python package/fnos/resolve_images.py --version 0.19.1 --namespace siyuan044 --output /tmp/fnos-images.json
python package/fnos/build.py --images-lock /tmp/fnos-images.json --fnpack /path/to/fnpack
```

解析器等待 server、frontend、AI CPU 的同版本标签，确认 linux/amd64 可用后固定摘要。缺失或超时会失败，不回退 `latest`。本地默认等待 40 分钟，CI 为 90 分钟。数据库镜像固定在 `images.lock.json`；调整 PostgreSQL 主版本需单独验收。

目录内现有锁对应 `0.19.1`，可离线重现该版本的打包结构，不能拿来打其他版本。`--source-only` 仅生成可交给 fnpack 的源包。

输出在 `dist/`：FPK、同名 `.fpk.sha256`、`.images.json` 镜像锁。构建后读取最终 FPK，校验标识、版本、完整 HTML 介绍、安装提示、PNG 尺寸和所有镜像。校验失败不会输出新安装包。同产品版本仅修改打包内容时，递增 `build.py` 的 `REVISION`。

## CI 和下载链接

现有 `.github/workflows/build-desktop.yml` 增加独立的 `fnos` 任务：

- PR 仅测试，不等待发布镜像，不发布飞牛预览包。
- 标签 `vX.Y.Z`、手动执行或 `构建飞牛` 提交触发实际打包；标签必须与源码版本相同。
- 下载并验证固定版本 fnpack，构建 FPK、校验后上传 `fnos-package` Actions artifact。
- 标签发布同时等待桌面与飞牛构建成功，上传 FPK、SHA256 和镜像锁到 Release，并幂等更新飞牛下载链接段，保留其他发布说明。

仓库变量 `FNOS_IMAGE_NAMESPACE` 可以指定公开镜像命名空间。默认优先使用已有 ACR registry/namespace，未配置时使用 `siyuan044`；不需要 NAS 凭据。Release 使用工作流已有的 `GITHUB_TOKEN`。

官网只解析最新 Release 中实际存在的飞牛 x86 `.fpk`。没有附件或 API 不可用时回退 Release 页面，不拼接尚未存在的附件地址。

## 图标和介绍

`description.md` 是维护者确认的原文，`description.html` 为加粗与插图版本。图片使用明确宽高，适配飞牛原生折叠区域；不要依赖会被过滤的行内 CSS。manifest 描述值完整引用，避免分号被当成注释。

`logo.svg` 沿用项目矢量图形，仅移除柔化阴影。PNG 从矢量导出；根图标为 64/256 px，桌面入口固定引用 256 px。不要放大小 PNG 生成大图。

## 数据与升级

- 用户数据目录必填，应为个人或共享文件中的独立空文件夹，拒绝 `/volN/@app*` 管理目录。
- 外部照片默认只读，可逐目录选择服务端读写；AI 挂载始终只读。新安装主图库和新增图库使用源文件夹名，仅重名时加 `(2)`、`(3)` 序号，分配结果持久化。旧版升级保留「已有照片」和摘要映射，保护已有索引。
- 通过飞牛「访问权限」原生 UI 添加/移除目录，config_callback 按 `TRIM_DATA_ACCESSIBLE_PATHS` 的冒号分隔快照同步；缺失快照保留原生挂载，空快照取消全部原生挂载，过滤固定 data-share。按应用账号的实际访问权限映射只读/读写。旧版手工图库可通过稳定字段显式移除，或在原生界面选择同一路径接管管理。所有目录校验完成后才保存，不删除原文件或数据库索引。使用官方 `/var/apps/trailsnap/wizard` 目录向 bootstrap 提供向导写入挂载。
- 读写挂载不修改 NAS 文件 ACL，用户需为应用运行账号授予相应权限。目录名不支持英文分号（批量分隔符）。
- 保留原端口、数据位置、图库和数据库/JWT 凭据。升级前通过 Docker 数据挂载备份数据库及配置，避免依赖应用用户对个人目录的写权限。
- R2 布局不自动迁移。早期 R3 安装包中存在备份脚本权限问题；已安装的旧升级前脚本会先执行，因此单靠新包无法修复它，需先修补旧脚本并备份，再更新。
- 不承诺数据库降级回滚，不要通过卸载重装绕过升级错误。

迁入前的适配包已在 fnOS V1.2.0800 验证；每个新产品版本仍需 NAS 安装、升级和主要流程验收。CI 成功不代表已上架应用市场。

## 测试

```powershell
pwsh ./tests/scripts/run-tests.ps1 -Layer unit -Component fnos -Level all
```

R11 的原生授权新增、读写切换与移除回调仍需新包 NAS 验收；本地测试不替代实机安装验证。

测试覆盖镜像版本拒绝、等待超时、发布说明幂等、目录与凭据保留、同名图库分离、重复接入、旧索引保护。实际 FPK 校验随每次构建执行。

R12：按用户选择恢复运行设置内新增目录和权限，已有目录使用精简 select（只读/读写/移除），不显示映射和冗余提示；原生向导不支持横向目录控件。表单字段随配置代次轮换，避免飞牛保存的新增/移除值重放。介绍图片宽144px，在当前176px折叠区域实测保留两行正文。

飞牛包的 server 服务设置 `TS_FNOS=1`。新版后端在外部图库候选接口返回 `deployment: fnos`，新版网页据此显示飞牛添加说明和运行设置接入步骤；未设置时显示通用 Docker 指引。环境标识需要相应版本的前后端镜像，旧镜像不会仅因重新打包而获得新界面。
