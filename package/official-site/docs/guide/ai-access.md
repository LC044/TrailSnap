---
title: AI Agent 文档入口
description: 为 AI Agent 提供 llms.txt、结构化索引和 Markdown 原文等稳定、低噪声的官网文档入口。
---

# AI Agent 文档入口

TrailSnap 官网在面向人类的页面之外，还提供了一组面向 AI Agent 的稳定文本入口。Agent 不需要解析页面导航、搜索框或渲染后的 HTML，可以直接读取纯文本文档。

## 推荐入口

| 入口 | 地址 | 用途 |
| --- | --- | --- |
| 文档索引 | [/llms.txt](/llms.txt) | 按分类查看全部文档，链接直接指向 Markdown 原文 |
| 全量文档 | [/llms-full.txt](/llms-full.txt) | 一次性读取用户指南、部署指南、Agent 指南和核心开发文档 |
| 结构化索引 | [/ai-docs.json](/ai-docs.json) | 程序化读取标题、描述、分类、语言、HTML 与 Markdown 地址 |
| CLI 安装提示 | [/install.md](https://trailsnap.cn/install.md) | 面向 Agent 的 `trailsnap-cli` 安装与配置流程 |
| 站点地图 | [/sitemap.xml](/sitemap.xml) | 发现官网所有可索引页面 |

## Markdown 原文规则

官网教程会同时输出 HTML 与 Markdown 两种格式：

- 人类阅读页面：`/docs/guide/install.html`
- AI 阅读原文：`/docs/guide/install.md`
- 目录页：`/docs/guide/agent/` 与 `/docs/guide/agent/index.md`
- 英文文档：`/en/docs/guide/install.html` 与 `/en/docs/guide/install.md`

因此，Agent 可以把文档 URL 中的 `.html` 替换为 `.md`，直接读取原始 Markdown。

## 推荐读取顺序

1. 先读取 [/llms.txt](/llms.txt)，确定需要哪篇文档。
2. 单个主题只读取对应 `.md` 文件，减少上下文占用。
3. 需要完整背景时读取 [/llms-full.txt](/llms-full.txt)。
4. 需要程序化处理文档列表时读取 [/ai-docs.json](/ai-docs.json)。
5. 安装或调用 TrailSnap CLI 时读取 [/install.md](https://trailsnap.cn/install.md)，并参考 [TrailSnap CLI 工具](/docs/guide/agent/trailsnap-cli.md)。

## Agent 使用建议

- **先读索引，再按需读全文**：`llms.txt` 能帮助 Agent 快速定位教程，避免把官网首页和导航噪音带入上下文。
- **优先读取 Markdown 原文**：Markdown 没有页面脚本和渲染噪音，链接结构也更接近源文件。
- **保持语言一致**：中文用户优先使用中文文档；英文用户使用 `/en/docs/...` 下的对应文档。
- **注意区分人类流程与 Agent 流程**：涉及浏览器登录、Token 创建或照片目录授权时，应提示用户手动完成，不要代替用户猜测凭据。
- **CLI 操作先确认配置**：执行 `trailsnap` 命令前，先确认 API URL 与 Token 已通过 `trailsnap config set` 配置。

