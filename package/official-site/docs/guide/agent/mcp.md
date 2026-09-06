---
title: 配置 TrailSnap MCP
description: 创建最小权限 Agent Token，并通过 Streamable HTTP 将 TrailSnap 的照片搜索、回忆侦探、人物时间线和待确认相册提案接入外部 AI Agent。
outline: [2, 3]
---

# 配置 TrailSnap MCP

TrailSnap 内置 MCP（Model Context Protocol）服务。支持 MCP 的 AI 客户端可以在不接触数据库和照片原始路径的情况下，查询当前用户的照片、相册、人物与回忆线索，还可以创建必须由用户在 TrailSnap 中确认的相册整理方案。

MCP 使用独立的 Agent Token，不需要把账号 JWT 或登录密码交给外部 Agent。

## 1. 确认连接地址

MCP 使用 **Streamable HTTP** 传输。根据 TrailSnap 的访问方式选择地址：

| 使用方式 | MCP 地址 |
| --- | --- |
| Docker、NAS、桌面版或反向代理的统一入口 | `https://你的域名/api/mcp/` |
| 局域网统一入口 | `http://主机IP:3180/api/mcp/` |
| 开发环境直接访问后端 | `http://127.0.0.1:8000/mcp/` |

统一入口只需要开放 TrailSnap 的前端端口，不需要额外暴露后端、AI 服务或数据库端口。建议保留地址末尾的 `/`。

## 2. 创建 Agent Token

1. 登录 TrailSnap。
2. 打开“设置 → 令牌管理”。
3. 选择“新增令牌”，填写名称和过期时间。
4. 只勾选 Agent 实际需要的权限。
5. 输入当前账号密码完成验证，并立即安全保存生成的 `ts_` Token。

| 权限 | 用途 |
| --- | --- |
| `photos:read` | 搜索照片、分析回忆线索 |
| `albums:read` | 查询相册列表 |
| `people:read` | 查询人物、人物时间线 |
| `albums:propose` | 创建待用户确认的相册方案；不能直接执行 |

::: tip 最小权限
只做照片问答时通常只需要 `photos:read`。只有当用户确实希望 Agent 整理照片时，才增加 `albums:propose`。
:::

生成 Token 后请立即安全保存。不要把真实 Token 提交到 Git、写入公开文档、发布到 Issue，或交给不受信任的 Agent。

## 3. 配置 MCP 客户端

不同客户端的配置文件位置可能不同，但核心配置相同：Streamable HTTP 地址和 Bearer Token。

```json
{
  "mcpServers": {
    "trailsnap": {
      "type": "http",
      "url": "https://photos.example.com/api/mcp/",
      "headers": {
        "Authorization": "Bearer ts_your_agent_token"
      }
    }
  }
}
```

部分客户端将 `type` 写作 `streamable-http`，或者把请求头放在单独的认证设置中；以该客户端的 MCP 文档为准。请勿把示例中的域名和 Token 原样使用。

保存配置并重启客户端后，应能看到以下工具：

- `search_photos`：按日期、地点、OCR、媒体类型、人物和评分搜索照片。
- `list_albums`：查询相册、封面和照片数量。
- `list_people`：查询可见人物与人物 ID。
- `investigate_memory`：根据模糊时间、地点、人物和文字线索寻找候选回忆。
- `get_person_timeline`：生成人物事件时间线。
- `propose_album_organization`：生成 7 天内有效的待确认相册方案。

可以用下面的问题验证连接：

> 查找我最近在上海拍摄的 10 张照片，并说明筛选依据。

## 4. 配置 Pi Agent

Pi 本身不直接加载通用 MCP 配置。TrailSnap 仓库提供了 Pi Bridge 和配套 Skill，会把 MCP 工具注册为 Pi 原生工具。

```shell
npm install -g trailsnap-cli
trailsnap config set --url "https://photos.example.com" --token "ts_your_agent_token"
pi install git:github.com/LC044/TrailSnap
```

进入 Pi 后运行：

```text
/trailsnap-status
```

Bridge 会优先读取以下环境变量：

```text
TRAILSNAP_MCP_URL=https://photos.example.com/api/mcp/
TRAILSNAP_API_TOKEN=ts_your_agent_token
```

没有设置环境变量时，它会复用 `trailsnap config set` 保存的地址和 Token。Pi 中的工具名称带有 `trailsnap_` 前缀，例如 `trailsnap_search_photos`。

## 5. 公网和反向代理部署

通过域名或局域网地址访问时，在 TrailSnap Server 的环境变量中配置对外可访问的站点根地址：

```text
TRAILSNAP_PUBLIC_URL=https://photos.example.com
```

Docker Compose 示例：

```yaml
services:
  server:
    environment:
      TRAILSNAP_PUBLIC_URL: https://photos.example.com
```

配置后，MCP 公开地址为 `https://photos.example.com/api/mcp/`，相册提案返回的审批链接也能被外部 Agent 直接交给用户打开。

只有在 MCP 使用独立域名时才需要额外配置：

```text
TRAILSNAP_MCP_URL=https://mcp.example.com/mcp/
TRAILSNAP_MCP_ALLOWED_HOSTS=mcp.example.com
```

`TRAILSNAP_MCP_ALLOWED_HOSTS` 可以填写多个以逗号分隔的主机。只添加真实提供 TrailSnap MCP 的主机，不要关闭 Host 校验。

## 6. 相册提案如何确认

具有 `albums:propose` 权限的 Agent 只能创建 `proposed` 状态的方案。此时相册尚未创建，照片和标签也没有变化。

Agent 应把返回的 `approval_url` 交给用户。用户使用正常 TrailSnap 账号打开页面，检查名称、照片、封面与标签，然后明确选择“确认执行”或“拒绝方案”。Agent Token 不能确认、拒绝或撤销方案。

## 常见问题

### 返回 401 Unauthorized

检查请求头是否为 `Authorization: Bearer ts_...`，Token 是否过期或已被撤销。Agent Token 不能替换成大模型服务商的 API Key。

### 工具提示缺少权限

重新创建包含对应 scope 的 Token。例如人物时间线需要 `people:read`，相册提案需要 `albums:propose`。不建议为方便一次性授权全部权限。

### 公网访问提示 Invalid Host header

确认已经设置正确的 `TRAILSNAP_PUBLIC_URL`。使用独立 MCP 域名时，将该主机加入 `TRAILSNAP_MCP_ALLOWED_HOSTS`。

### 提案链接是相对路径

为 Server 设置 `TRAILSNAP_PUBLIC_URL` 后会返回绝对审批链接。TrailSnap Pi Bridge 也会根据 MCP 地址自动补全相对链接。

### Agent 能否删除或移动照片

不能。当前 MCP 不开放删除照片、移动文件、重命名文件、直接修改相册或执行 HTML。需要管理和运维能力时，请使用 [TrailSnap CLI](./trailsnap-cli.md)，并谨慎保管具有写权限的登录凭证。
