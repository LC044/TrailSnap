---
outline: [2, 3]
---

# Agent Skills

TrailSnap CLI 可以作为 Agent 工具（Skill）被无缝集成到各种 AI 编码助手或 Agent 平台中，例如 Claude Code、OpenClaw / Roo Code 等。通过让 Agent 调用 CLI，AI 能够直接获取、分析和查询您的相册数据，实现基于个人图库的智能问答。

支持 MCP 的客户端可以直接连接 TrailSnap 内置的 Streamable HTTP 服务，无需包装 CLI。请参考 [配置 TrailSnap MCP](./mcp.md)。

1. Claude Code
    [使用说明](./claudecode.md)

2. OpenClaw / Roo Code 等 IDE Agent
    [使用说明](./openclaw.md)

3. 其它 Agent 平台集成

如果您正在使用 Dify、Coze、FastGPT 或自研 Agent 框架，您可以将 CLI 包装为系统级工具（Tool）：

请将以下提示词复制给你的AI Agent（OpenClaw、Claude Code、Cursor、MaxClaw、AutoClaw、KimiClaw、TRAE、OpenCode等）, 它会引导你添加token并完成安装：

```text
帮我安装 trailsnap-cli 和 skill：https://trailsnap.cn/install.md
我的 TrailSnap 地址是 http://localhost:3180
我的token 是 ts_hV5nsCZxxxxx
```

## 使用skill

<span class="marker-evy">直接通过自然语言让 Agent 查询相册</span>：

> "帮我使用 trailsnap-cli skill，查一下最近在西安拍的照片有哪些？"
> "我去年国庆节去了哪些地方，帮我写一个HTML格式的旅游日记。"

👉 [查看 AI 生成的旅行日记示例](/examples/travel-diary-2025-golden-week.html)
