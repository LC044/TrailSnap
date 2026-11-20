---
title: "相册·SKILL，把你的相册接入OpenClaw，一句话生成旅游日记"
description: "昨天，我把 TrailSnap 的 SKILL 接入了我的养的龙虾。"
date: "2026-04-28"
updated: "2026-11-03"
author: "司小远"
image: ""
source: "https://blog.siyuan.ink/post/46"
---
# 相册·SKILL，把你的相册接入OpenClaw，一句话生成旅游日记

昨天，我把 TrailSnap 的 SKILL 接入了我的养的龙虾。

那天晚上，我随口说了一句：「帮我看看去年国庆节期间我去了哪些地方。」

三十秒后，它给我返回了一个页面。

不是照片的简单罗列，而是一篇手账风格的 HTML 页面，按时间顺序排列，配上了 AI 写的文字。

- 10 月 1 日 下午，拙政园·白墙黛瓦，倒影里的建筑比岸边更稳当些；
- 10 月 2 日 傍晚，呈坎·灯笼夜·烟花国庆，夜色被烟火烫出了人间的颜色。
- 10 月 6 日 清晨， 舟山·跨海大桥·日出，连大桥都忍不住把脸藏进云里陪它看人间。


我盯着那张照片看了很久。

那张照片我从来没发过朋友圈，甚至当时拍完就忘了。但 AI 记得。它从照片的 GPS 数据里读出了地点，从时间戳里读出了日期，然后告诉我：「这是你去年夏天最值得回忆的一组照片，memory_score 是 97。」

我不知道 97 分是怎么算出来的。但那一刻，我信了。


## 相册的「死」与「活」

我们拍太多照片了。

2024 年中国人均拍摄照片超过 1000 张，但大多数人——包括我——翻看相册的频率可能是一年一次。有些照片，我们再也不会看第二眼。

这不是照片的错。是我们找不到和它相处的方式。

我把照片存在 NAS 上，用 TrailSnap 管理，按地点、按人物、按时间分类。但分类解决的是「找到」的问题，不是「回忆」的问题。

真正让我重新「看到」那些照片的，是 AI。


## 那它是怎么做到的？

TrailSnap 自带一个命令行工具，叫 trailsnap-cli。

你在终端里敲：

```
trailsnap photos list --city 青岛市 --start-time 2025-06-01 --end-time 2025-06-30
```

它会返回那个月你在青岛拍的所有照片。

```
trailsnap locations timeline --level city
```

它会返回你去过哪些城市，按时间排列。

这就是关键：**照片变成了可查询的数据，而不只是文件名。**

我给 AI 写了一份 SKILL——本质上就是一份「工具说明书」。告诉它这个 CLI 怎么用、查什么、返回什么格式。

然后 AI 就能读懂你的相册了。

## 它能做什么？

### 🌍 旅行日记

「帮我生成今年夏天的旅行日记」—— AI 自动整理旅途中所有照片，按时间地点排序，生成一篇精美的手账风格页面。比手工做的精美十倍，而且只花了三分钟。

### 📅 时光机

「去年今天我在干什么？」—— AI 查询一年前的照片，告诉你那天的故事。有些你以为忘记的事，AI 替你记着。

### 👨‍👩‍👧 家庭回忆

「找出所有有我外婆的照片」—— AI 识别人物，聚合所有相关照片，可以生成分享页，留给家人。

### 🔍 照片整理

「帮我看看哪些照片可能拍糊了」—— AI 查质量评分，帮你发现废片。「找出我重复保存的照片」—— 释放存储空间。

## 怎么做到的（技术角度）

整件事分三层：

**第一层：trailsnap-cli**
命令行工具，负责和 TrailSnap 后端交互。安装方式：

```
# pip
pip install trailsnap-cli

# npm
npm install -g trailsnap-cli
```

配置 API 地址和 Token 后即可使用。

**第二层：SKILL**
SKILL 是 OpenClaw 平台的工具描述协议。写一份 SKILL，相当于告诉 AI：「这个工具能做什么，怎么用它，返回什么。」有了 SKILL，AI 不需要懂 API，只要会「说话」就行。

**第三层：AI Agent**
AI Agent 读取 SKILL，理解用户意图，构造 CLI 命令，解析返回的数据，最后生成用户需要的内容——一篇日记、一张照片集锦、或者回答一个问题。

```
用户 → AI Agent → SKILL → trailsnap-cli → TrailSnap API → 相册数据
                                           ↑ JSON 数据
用户 ← AI Agent ← 组装内容 ←──────────────┘
```

整个过程，你的照片始终在自己的 NAS 上，不经过任何第三方服务器。

## 试试看？

**第一步**：安装 trailsnap-cli

```bash
pip install trailsnap-cli
```

**第二步**：在 TrailSnap 中获取 API Token（设置 → API Token）

**第三步**：配置 CLI

```bash
trailsnap config set --url http://你的NAS地址:端口 --token 你的Token
```

**第四步**：验证连接

```bash
trailsnap photos list --limit 5
```

**第五步**：给你的 AI Agent 配上 trailsnap-cli SKILL，然后开始对话。

**当然你也可以让你的AI帮你安装**

请将以下提示词复制给你的AI Agent（OpenClaw、Claude Code、Cursor、MaxClaw、AutoClaw、KimiClaw、TRAE、OpenCode等）, 它会引导你添加token并完成安装：

```text
帮我安装 trailsnap-cli 和 skill：https://trailsnap.cn/install.md
我的api url 是 http://localhost:8000
我的token 是 ts_hV5nsCZxxxxx
```

相册是一个极其私人、极其丰富、但长期沉睡的数据源。我们习惯了「拍完就存着」，相册变成了一座数字废墟。

但相册本质上记录的是**你曾经在哪里、和谁在一起、关心什么、经历了什么**。

现在，AI 帮你找到了，还帮你讲出来。

**试试 TrailSnap：**
- GitHub：https://github.com/LC044/TrailSnap
- 官网：https://trailsnap.cn/

---

*你有什么一直想找回的回忆吗？试试看，也许 AI 比你更记得。*

---

> 本文作者 司小远，首发于 [程序猿日常](https://blog.siyuan.ink/post/46)，行影集官网博客同步收录。
