---
title: 绿联 NAS（UGREEN）部署
---

# 绿联 NAS（UGREEN）部署

## 使用 Docker Compose 部署容器

在 UGOS Pro 系统上，推荐使用项目 Docker Compose 快速部署容器，适合需同时管理多个容器的场景，这种方法简化了容器的部署与管理工作。以下是使用 Docker Compose 部署 TrailSnap 的详细步骤。

如果你还没部署过，建议先读通用章节：[/docs/guide/docker/](/docs/guide/docker/)

### 1. 进入 Docker 项目界面

在 UGOS Pro 系统中，打开 Docker 应用，点击【项目】 > 【创建】，启动项目创建向导。
项目名称填为 `trailsnap`，其他默认即可。

![Alt text](/images/ugos.png)

## 2. 配置 Docker Compose 文件

填入[/docs/guide/docker/](/docs/guide/docker/)中的 Docker Compose 模板。

1. 修改 `server` 服务的照片目录挂载：

```yaml
volumes:
  - ./data:/app/data
  - /你的照片文件夹真实路径:/app/Photos
```

绿联的默认照片路径通常为：`/home/用户名/Photos`

如果有多个文件夹需要挂载，推荐使用下面的格式，/app/Photos子目录下会简化后续的一些操作：

```yaml
volumes:
  - ./data:/app/data
  - /你的照片文件夹真实路径1:/app/Photos/旅行
  - /你的照片文件夹真实路径2:/app/Photos/航拍
  - /你的照片文件夹真实路径3:/app/Photos/家庭
```

如果你希望最大化安全性，可以把照片目录挂载为只读，但这样会导致删除功能和其他一些修改本地文件的工具不可用：

```yaml
- /你的照片文件夹真实路径:/app/Photos/:ro
```

## 3. 设置端口与网络

TrailSnap 默认只开放一个访问端口：`8082`。网页、App 和 CLI 都使用该地址；后端、AI 与数据库端口仅在 Docker 内部使用。

如与 NAS 上其他服务冲突，只需修改 `frontend.ports` 映射（例如改为 18082）。

## 4. 启动与验证

启动后在浏览器访问：

- `http://<NAS_IP>:8082`

![Alt text](/images/ugos-start.png)

打开设置->外部图库，填入容器内的照片路径：`/app/Photos`，添加外部图库之后会自动扫描并在后台运行任务（可以在设置->任务管理查看任务详情）。

API 文档位于 `http://<NAS_IP>:8082/api/docs`。

## 5. 权限与扫描问题排查

若 TrailSnap 扫描不到照片，通常是权限或路径问题：

- 先进入 `server` 容器的终端/控制台，确认 `/app/Photos` 目录下能看到照片文件。
- 确认 NAS 侧共享文件夹权限允许 Docker/容器服务读取。
- 如照片目录在外接存储或特定存储池，确认该存储池对容器可见。

