# Claude Code

> 在 Claude Code 中使用 trailsnap-cli skill 使用 AI 管理相册。

## 一、获取访问token

参考 [Token 设置](../settings/tokensetting.md) 获取访问token。

## 二、安装 Claude Code

参考 [Claude Code 文档](https://code.claude.com/docs/en/setup) 进行安装。

## 三、安装 trailsnap-cli skill

:::tabs
== Agent 自动安装

请将以下提示词复制给你的AI Agent（OpenClaw、Claude Code、Cursor、MaxClaw、AutoClaw、KimiClaw、TRAE、OpenCode等）, 它会引导你添加token并完成安装：

```text
帮我安装 trailsnap-cli 和 skill：https://trailsnap.cn/install.md
我的 TrailSnap 地址是 http://localhost:8082
我的token 是 ts_hV5nsCZxxxxx
```

![alt text](/images/wechat_longscreenshot_2026-04-27_224237_662.jpg)

== 手动安装

根据环境选择安装方式（选择其中一种即可）：

- Node.js 安装：npm/npx 安装
- Python 安装：pip 安装

#### npm/npx 安装

```shell
# 安装 CLI
npm install -g trailsnap-cli

# 安装 CLI SKILL（必需）
npx skills add lc044/trailsnap  -y -g
```

#### pip 安装

```shell
# 安装 CLI
pip install trailsnap-cli

# 安装 CLI SKILL（必需）
npx skills add lc044/trailsnap  -y -g
```

#### 配置api url和 token

```shell
trailsnap config set --url <url> --token <token>
```

#### 验证

```shell
trailsnap photos list --limit 1
```
:::

## 使用skill

直接通过自然语言让 Claude 查询相册：
> "帮我使用 trailsnap-cli skill，查一下最近在西安拍的照片有哪些？"
> "我去年国庆节去了哪些地方，帮我写一个HTML格式的旅游日记。"

