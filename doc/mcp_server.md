# TrailSnap MCP Server

TrailSnap 内置一个最小权限的 Model Context Protocol（MCP）服务，使外部 AI Agent 可以安全查询当前用户的照片、相册、人物和回忆线索，也可以创建必须由用户在站内确认的相册整理提案。MCP 与内置 LangGraph Agent 复用相同的相册领域服务，但拥有独立的协议入口和工具权限检查。

## 连接地址

- 通过 TrailSnap 前端或反向代理访问：`https://你的域名/api/mcp/`
- 直接访问后端：`http://127.0.0.1:8000/mcp/`
- 传输协议：Streamable HTTP
- 鉴权：`Authorization: Bearer ts_xxx`

Agent Token 可在「设置 → 令牌管理」中创建。创建时可以只授权任务实际需要的 MCP 权限。

通用客户端配置示例：

```json
{
  "mcpServers": {
    "trailsnap": {
      "type": "http",
      "url": "https://你的域名/api/mcp/",
      "headers": {
        "Authorization": "Bearer ts_xxx"
      }
    }
  }
}
```

配置文件的具体位置和字段名由 MCP 客户端决定。不要把真实令牌提交到 Git 仓库或粘贴给不受信任的 Agent。

## Pi Agent

Pi 本身不内置 MCP 客户端。TrailSnap 仓库提供一个 Pi Package，其中的 TypeScript Extension 会把远程 MCP 工具注册为 Pi 原生工具，并一同加载 `trailsnap-agent` Skill。

先安装 CLI、保存 TrailSnap 地址与 `ts_` Agent Token，然后安装 Package：

```shell
npm install -g trailsnap-cli
trailsnap config set --url "https://你的域名" --token "ts_xxx"
pi install git:github.com/LC044/TrailSnap
```

进入 Pi 后运行 `/trailsnap-status` 验证连接。Bridge 优先读取环境变量 `TRAILSNAP_MCP_URL` 和 `TRAILSNAP_API_TOKEN`，否则复用 CLI 位于用户配置目录中的 `.env`，不会把 Token 写进 Pi 项目配置。

Pi Package 注册的工具名带 `trailsnap_` 前缀，以避免与其他扩展冲突：

- `trailsnap_search_photos`
- `trailsnap_list_albums`
- `trailsnap_list_people`
- `trailsnap_investigate_memory`
- `trailsnap_get_person_timeline`
- `trailsnap_propose_album_organization`

## 工具

| 工具 | Scope | 用途 |
| --- | --- | --- |
| `search_photos` | `photos:read` | 按日期、地点、OCR、媒体类型、方向、人物和评分搜索照片 |
| `list_albums` | `albums:read` | 分页查询可访问的相册、封面和照片数量 |
| `list_people` | `people:read` | 查询可见人物和人物 ID |
| `investigate_memory` | `photos:read` | 融合模糊日期、地点、人物、文字和语义照片线索，生成候选回忆事件 |
| `get_person_timeline` | `people:read` | 生成人物的年份、事件、地点、同行者和代表照片时间线 |
| `propose_album_organization` | `albums:propose` | 创建 7 天内有效的待确认相册方案并返回站内审批链接，不直接执行 |

所有工具都会从经过验证的 Agent Token 解析用户身份，数据库查询强制按该用户隔离。照片结果只返回安全元数据和缩略图 URL，不返回原始文件路径。回忆侦探给出的是可解释候选，而不是自动确认的事实。

`albums:propose` 与读取权限相互独立。外部 Agent 调用提案工具后只会新增一条 `proposed` 计划，并得到 `approval_url`；相册在此时尚未创建。配置 `TRAILSNAP_PUBLIC_URL` 后该地址是可直接打开的绝对链接，本机开发环境则返回站内相对路径。用户需要使用正常账号登录 TrailSnap，检查名称、照片、封面和标签后明确选择“确认执行”或“拒绝方案”。Agent Token 不能调用执行、拒绝或撤销接口。

## 部署配置

本机访问无需额外设置。通过域名、局域网 IP 或反向代理部署时，推荐配置：

```dotenv
TRAILSNAP_PUBLIC_URL=https://photos.example.com
```

此时 MCP 的公开资源地址自动成为 `https://photos.example.com/api/mcp/`，并把公开主机加入 DNS rebinding 防护白名单。

如果 MCP 使用独立地址，可以覆盖：

```dotenv
TRAILSNAP_MCP_URL=https://mcp.example.com/mcp/
TRAILSNAP_MCP_ALLOWED_HOSTS=mcp.example.com,192.168.1.10:8000
```

`TRAILSNAP_MCP_ALLOWED_HOSTS` 以逗号分隔。只添加实际由 TrailSnap 服务的主机，不要为方便而关闭 Host 校验。

## 当前边界

- MCP 查询工具保持只读；唯一的非只读工具只能创建待确认计划，不会直接修改相册。
- 不开放删除照片、修改相册、文件写入和 HTML 执行。
- 内置 LangGraph Agent 不被 MCP 替换；两者分别服务站内交互和外部 Agent 接入。
- Agent Token 的 scopes 同时约束 MCP 与 REST/CLI：仅允许匹配领域的 GET/HEAD/OPTIONS 请求，写请求和未映射接口返回 403。普通用户 JWT 行为不变。

后续写能力继续使用独立 scopes，并复用“生成计划 → 站内预览 → 用户确认 → 可审计执行/撤销”的模式。删除文件等不可逆操作仍不开放给外部 Agent。
