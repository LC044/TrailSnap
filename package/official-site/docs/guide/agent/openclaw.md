---
outline: [2, 3]
---

# OpenClaw / Roo Code

OpenClaw / Roo Code 等 IDE Agent 可以调用 TrailSnap CLI 作为 Skill，让 AI 通过 TrailSnap API 查询你的个人相册数据。

## 一、获取访问 token

参考 [Token 设置](../settings/tokensetting.md) 获取访问 token。

## 二、安装 trailsnap-cli 和 Skill

:::tabs
== Agent 自动安装

请将以下提示词复制给你的AI Agent（OpenClaw、Claude Code、Cursor、TRAE 等）, 它会引导你添加 token 并完成安装：

```text
帮我安装 trailsnap-cli 和 skill：https://trailsnap.cn/install.md
我的 TrailSnap 地址是 http://localhost:3180
我的token 是 ts_hV5nsCZxxxxx
```

== 手动安装

```shell
npm install -g trailsnap-cli
npx skills add lc044/trailsnap  -y -g
trailsnap config set --url <url> --token <token>
```
:::

## 三、在对话中使用

示例：

> "帮我使用 trailsnap-cli skill，查一下最近在上海拍的20张照片有哪些？"
> "帮我找出包含登机口文字的照片，整理一下我的航班记录。"
