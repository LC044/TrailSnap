# 设置访问令牌

::: info Token 设置
使用token可以让第三方应用访问TrailSnap的后端API，你可以从TrailSnap后端获取一个Token。
:::

## 获取 Token

打开 “设置” -> “令牌管理” -> “新增令牌”，输入令牌名称和过期时间，验证账号登录密码之后即可获取到Token。

token示例：`ts_hV5nsCZJDheBvvmcd5L248IiAUnIwwZAn`

## API URL

第三方客户端填写统一的 TrailSnap 地址，例如 `http://<TrailSnap 主机IP>:8082`。CLI 会自动通过该地址下的 `/api` 访问接口。

```yaml
  frontend:
    ports: [ "8082:80" ]
```

这里的 `8082` 是唯一的用户访问端口；不需要额外开放后端、AI 或数据库端口。

## 使用token

Agent Token 支持按用途选择最小权限。只读查询可选择照片、相册和人物读取权限；需要外部 Agent 整理照片时，可以额外授予“提出相册方案”权限。该权限只能创建待确认计划，不能直接修改相册。

- MCP 客户端：参考 [配置 TrailSnap MCP](/docs/guide/agent/mcp)
- 命令行工具：参考 [TrailSnap CLI 工具](/docs/guide/agent/trailsnap-cli)
