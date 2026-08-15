---
title: 安装指南
description: 在桌面安装包与 Docker 部署之间选择适合你的 TrailSnap 安装方式。
---

# 安装 TrailSnap

TrailSnap 同时提供桌面安装包和 Docker 自托管部署。先根据使用场景选择版本：

| 方式 | 适合场景 | 支持平台 | AI 能力 |
| --- | --- | --- | --- |
| 桌面版 | 单台个人电脑、希望快速开始 | Windows、macOS、Linux | 安装基础客户端后，按需安装 AI 扩展 |
| Docker | NAS、家庭服务器、多设备访问 | 支持 Docker Compose 的设备 | AI 服务随 Compose 部署，可选 CPU/GPU |

::: tip 不确定怎么选？
只在当前电脑使用，选择桌面版；需要手机、平板和多台电脑通过局域网访问同一图库，选择 Docker。
:::

## 桌面版

前往[下载页面](/download)，官网会优先标出当前系统的安装包：

- Windows 10/11（x64）：下载 `.exe` 并按向导安装。
- macOS（Apple Silicon）：下载 `.dmg`，将 TrailSnap 拖入“应用程序”。首次打开若被系统拦截，请在“隐私与安全性”中确认允许。
- Linux（x64）：Debian/Ubuntu 建议下载 `.deb`；其他发行版可使用 `.AppImage`，并为文件添加执行权限。

桌面基础包包含相册管理和本地服务，不会强制下载体积较大的 AI 运行环境。需要人脸识别、OCR、图片分类、语义检索或本地大模型时，请继续阅读 [AI 扩展使用说明](/docs/guide/desktop-ai-extension)。

安装完成后：

1. 启动 TrailSnap。
2. 在设置中添加照片目录。
3. 先用少量照片完成一次扫描，确认目录权限与运行状态。
4. 按需安装 AI 扩展并创建对应分析任务。

::: warning 数据安全
桌面版不会替代你的照片备份。首次使用批量整理、重命名或清理功能前，请先备份图库。
:::

## Docker 部署

Docker 适合 NAS 和常驻服务器，会同时运行前端、后端、PostgreSQL 与 AI 服务。开始前请先完成[部署前检查](/docs/guide/preflight)。

### 一键安装脚本

Windows PowerShell：

```powershell
irm https://trailsnap.cn/install.ps1 -OutFile install.ps1
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Linux / macOS / WSL2：

```bash
curl -fsSL https://trailsnap.cn/install.sh | bash
```

脚本会收集照片目录、端口、时区和 CPU/GPU 模式，生成 `.env` 与 `docker-compose.yml`，拉取镜像并完成健康检查。默认访问地址为 `http://<服务器 IP>:8082`。

常用管理命令（在安装目录执行）：

```bash
docker compose --env-file .env ps
docker compose --env-file .env logs -f
docker compose --env-file .env restart
docker compose --env-file .env down
```

升级和卸载：

```bash
./install.sh --upgrade
./install.sh --uninstall          # 保留数据
./install.sh --uninstall --purge  # 删除数据，谨慎使用
```

PowerShell 脚本使用对应的 `-Upgrade`、`-Uninstall` 参数；运行 `Get-Help .\install.ps1 -Detailed` 可查看完整参数。

### 手动部署与 NAS 教程

- [Docker 通用部署与 GPU 配置](/docs/guide/docker/)
- [Windows Docker 部署](/docs/guide/docker/windows)
- [绿联 NAS](/docs/guide/docker/ugreen)
- [极空间](/docs/guide/docker/zspace)
- [飞牛 OS](/docs/guide/docker/fnos)

## 下一步

- [添加外部图库](/docs/guide/settings/directories)
- [AI 扩展使用说明](/docs/guide/desktop-ai-extension)
- [AI 大模型连接配置](/docs/guide/settings/aisetting)
- [数据、隐私与备份](/docs/guide/data-safety)
- [开始使用](/docs/guide/user)
