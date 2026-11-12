# 飞牛 fnOS 安装包

GitHub 安装包 CI 的打包源，仅支持 x86 CPU。最终文件名为 `TrailSnap-<产品版本>-fnos-x86.fpk`，manifest 版本为 `<产品版本>-<打包修订>`。

## 本地构建

需要 Python 3.12+ 和官方 fnpack 1.2.3。工具地址及 SHA256 记录在 `fnpack.json`，执行前必须校验。源码中的产品版本从 `package/server/pyproject.toml` 读取。

在仓库根目录执行，示例版本应替换为当前产品版本：

```bash
python package/fnos/resolve_images.py --version 0.19.1 --namespace siyuan044 --output /tmp/fnos-images.json
python package/fnos/build.py --images-lock /tmp/fnos-images.json --fnpack /path/to/fnpack
```


目录内现有锁对应 `0.19.1`，可离线重现该版本的打包结构，不能拿来打其他版本。`--source-only` 仅生成可交给 fnpack 的源包。

输出在 `dist/`：FPK、同名 `.fpk.sha256`、`.images.json` 镜像锁。构建后读取最终 FPK，校验标识、版本、完整 HTML 介绍、安装提示、PNG 尺寸和所有镜像。校验失败不会输出新安装包。同产品版本仅修改打包内容时，递增 `build.py` 的 `REVISION`。

## CI 和下载链接

现有 `.github/workflows/build-desktop.yml` 增加独立的 `fnos` 任务：

- PR 仅测试，不等待发布镜像，不发布飞牛预览包。
- 标签 `vX.Y.Z`、手动执行或 `构建飞牛` 提交触发实际打包；标签必须与源码版本相同。
- 下载并验证固定版本 fnpack，构建 FPK、校验后上传 `fnos-package` Actions artifact。

仓库变量 `FNOS_IMAGE_NAMESPACE` 可以指定公开镜像命名空间。默认优先使用已有 ACR registry/namespace，未配置时使用 `siyuan044`；不需要 NAS 凭据。Release 使用工作流已有的 `GITHUB_TOKEN`。

## 图标和介绍

`description.md` 是维护者确认的原文，`description.html` 为加粗与插图版本。图片使用明确宽高，适配飞牛原生折叠区域；不要依赖会被过滤的行内 CSS。manifest 描述值完整引用，避免分号被当成注释。

## 数据与升级


## 测试

```powershell
pwsh ./tests/scripts/run-tests.ps1 -Layer unit -Component fnos -Level all
```

飞牛包的 server 服务设置 `TS_FNOS=1`。新版后端在外部图库候选接口返回 `deployment: fnos`，新版网页据此显示飞牛添加说明和运行设置接入步骤；未设置时显示通用 Docker 指引。环境标识需要相应版本的前后端镜像，旧镜像不会仅因重新打包而获得新界面。
