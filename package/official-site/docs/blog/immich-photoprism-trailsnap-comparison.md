---
title: "Immich、PhotoPrism 还是行影集？2026 自托管开源相册选型对比"
description: "对比 Immich、PhotoPrism 与行影集 TrailSnap 三款自托管开源相册：手机自动备份、以文搜图、人脸识别、足迹地图、票根纪念、NAS 部署与中文体验的差异，附选型结论与常见问题，帮你挑到合适的 Google Photos 开源替代。"
date: "2026-11-18"
updated: "2026-11-18"
author: "司小远"
image: "https://blog.siyuan.ink/static/img/194e04dd2f9d9cee780ec10d3734adbf.01-home-hero.webp"
keywords: ["Immich 替代", "PhotoPrism 对比", "开源相册", "自托管相册", "Google Photos 替代", "AI 相册", "NAS 相册"]
---

# Immich、PhotoPrism 还是行影集？2026 自托管开源相册选型对比

把照片从云盘搬回自己的硬盘，是越来越多人的选择。但"自托管开源相册"并不是一个同质化的品类：搜一圈你会发现，Immich、PhotoPrism 和行影集 TrailSnap 经常被放在一起比较，而它们其实想解决的是**三个不同的问题**。

这篇对比不做"谁碾压谁"的排名，只回答一件事：**你的照片和你的习惯，更适合哪一个。** 文中信息截至 2026 年 11 月（Immich v3.2、PhotoPrism 2026 年度版本、TrailSnap 0.21.0），功能以各项目官方文档为准。

## 一张表看懂三者差异

| 维度 | Immich | PhotoPrism | 行影集 TrailSnap |
| --- | --- | --- | --- |
| 一句话定位 | Google Photos 的开源替代 | 摄影师的本地照片档案库 | 为旅行记忆而生的中文 AI 相册 |
| 开源协议 | AGPL-3.0 | AGPL-3.0（另有商业版本） | AGPL-3.0 |
| 手机自动备份 | 原生 iOS/Android 后台备份 | 需借助第三方 PhotoSync | 原生Android 后台备份 |
| 以文搜图 | CLIP 语义搜索 + OCR 等过滤 | 标签 / 地点 / 颜色等结构化搜索 | CLIP 以文搜图，并标注语义线索 |
| 人物组织 | 人脸识别、跨用户聚类 | 人脸识别与聚类 | 人脸聚类 + 人物时光线 |
| 地图与足迹 | 地图浏览 | 地图浏览 | 照片地图 + 3D 足迹地球 + 5A 景区统计 + 线路里程 |
| 票据与旅行纪念 | 无专门能力 | 无专门能力 | 火车票 OCR 管理、纪念票根、行程时间线 |
| 中文体验 | 多语言社区翻译 | 多语言社区翻译 | 中文优先：界面、文档、票根与景区数据 |
| 部署形态 | Docker 多容器（Postgres/Redis/ML） | 单容器，可选 NVIDIA GPU 加速 | Docker Compose 一键 + 多家 NAS 安装包 + Windows/MacOS/Linux 系统安装包 |
| AI Agent 扩展 | API | API | 相册 SKILL：接入 OpenClaw / WorkBuddy 一句话整理、写旅行日记 |

## Immich：最接近 Google Photos 的"全家桶"

如果你的核心诉求是"**手机拍完自动进自己服务器**"，Immich 目前是完成度最高的答案。它的原生 App 覆盖 iOS 与 Android，2026 年 7 月的 v3.0 重做了后台备份调度（Android 可后台上传整个旧相册，iOS 并行利用后台刷新窗口），9 月的 v3.2 又更新了搜索界面与跨用户人脸聚类（[v3.0 发布说明](https://immich.app/blog/v3.0.0-release)、[v3.2 发布说明](https://immich.app/blog/v3.2.0-release)）。

搜索侧它用 Postgres + 向量扩展跑 CLIP 语义搜索，叠加 OCR、地点、人物等过滤条件；外部库、文件夹视图、标签、锁定照片、分享链接等"云相册习惯"也基本齐备。代价是部署组件较多（服务器、Postgres、Redis、机器学习容器），以及一份需要认真读的 AGPL 协议。

**适合谁**：把 Immich 当"私有版 Google Photos"主力相册的人，尤其是手机摄影为主、需要自动备份与家庭多用户的场景。

## PhotoPrism：摄影师的"原地索引"档案库

PhotoPrism 的思路相反：**不搬动你的文件**。它直接索引现有目录结构，配合 WebDAV 让电脑像操作本地盘一样管理照片，对已经有一套文件夹体系的摄影爱好者非常友好（[官方功能页](https://www.photoprism.app/features/)）。

它的长板是格式与画质流程：覆盖主流相机 RAW 格式的索引、查看与转换，2026 年的版本还加入了 PSD、分层 TIFF、Insta360 素材与 NVIDIA GPU 加速 AI 模型。人脸识别采用检测—嵌入—聚类三段管线，地图浏览齐备。手机备份不是原生能力，需要 PhotoSync 这类第三方工具完成；自然语言搜图也不是它的方向，搜索更多依赖标签、地点、颜色等结构化字段。

**适合谁**：相机出片、RAW 流程、已有文件夹档案体系，想要一个"不打乱我目录"的索引与浏览层的人。

## 行影集 TrailSnap：为"旅行记忆"而生的中文 AI 相册

行影集不试图做上面两者的全集。它问的是另一个问题：**照片存下来之后，那些旅行到底有没有被"记住"？**

- **票根、照片、足迹串成一条线**：火车票截图经 OCR 还原成行程数据，与照片、地点一起生成行程时间线、[3D 足迹地球](/docs/blog/tickets-photos-3d-footprints)与线路里程；纸质票停供后，还有[电子火车票纪念工具](/docs/blog/preserve-train-ticket-memories)把回忆做成可保存的票根。
- **用"记得的画面"找照片**：[以文搜图](/docs/blog/text-to-image-search)输入"海边看日落的照片"，结果会标出「海边 / 日落 / 傍晚」语义线索，而不是只匹配文件名。
- **中文场景做深**：5A 景区足迹统计、全国火车站数据、中文界面与文档、[多家国产 NAS 的一键安装包](/docs/guide/docker/)，以及桌面版内置 AI 运行环境——装完就能用，不折腾环境变量。
- **把相册交给 AI Agent**：通过相册 SKILL 接入 OpenClaw / WorkBuddy，[一句话整理几万张照片](/docs/blog/workbuddy-organizes-70k-photos)、生成旅行日记与[年度相册报告](/docs/blog/2025-annual-album-report)。

也要说清楚它的边界：移动端目前是预览阶段的浏览/搜索容器（Android APK、iOS 推荐 PWA），**还没有 Immich 那样的系统相册级自动后台备份**（见[移动 App 指南](/docs/guide/mobile-app)）；社区与生态规模也远小于前两者。照片主力入口仍是电脑目录与 NAS 挂载。

**适合谁**：旅行与出行记忆整理、中文用户、NAS 自托管玩家，以及想让 AI Agent 直接"读懂"自己相册的人。

## 怎么选：按场景给结论

- **手机备份是刚需、要全家共用** → Immich。
- **相机 RAW 档案、目录体系不能动** → PhotoPrism。
- **旅行记忆、票根纪念、中文体验、NAS 一键部署** → 行影集 TrailSnap。
- **备份与回忆整理都想要** → 两者可以共存：用 Immich 做手机备份入口，把行影集指向同一份照片目录做语义检索与足迹回顾——它们读的是同一堆文件，互不冲突。

选型没有银弹。先想清楚"照片进来之后，你最常做的动作是什么"，答案通常就出来了。

## 常见问题

**行影集能替代 Immich 吗？**
看用途。替代"手机自动备份 + 家庭云相册"目前不行；替代"找照片、回顾旅行、整理记忆"这一层，行影集做得更专。两者定位不同，也可以组合使用。

**PhotoPrism 的手机照片怎么进去？**
官方推荐用 PhotoSync 等第三方工具备份到服务器目录，或用 WebDAV 同步；PhotoPrism 本身不提供原生手机备份 App。

**三款会把照片上传到别人的云吗？**
都不会。三者均为自托管：照片、索引与识别结果都在你自己的机器上。行影集本身不提供任何公共云端服务，App 只连接你自己部署的服务器。

**都是开源免费吗？**
Immich 与行影集为 AGPL-3.0 自由使用；PhotoPrism 核心 AGPL-3.0 开源，另提供商业版本与订阅档位，选用前留意版本差异。

## 延伸阅读

- [功能全景速览：TrailSnap 能做什么？](/docs/blog/feature-scan)
- [你有多久没打开过相册了？—— 行影集「以文搜图」](/docs/blog/text-to-image-search)
- [开源相册行影集：把票根、照片、旅行自动串成 3D 足迹](/docs/blog/tickets-photos-3d-footprints)
- [为什么我推荐你拥有一台 NAS](/docs/blog/why-own-a-nas)
- [Docker 部署指南](/docs/guide/docker/)