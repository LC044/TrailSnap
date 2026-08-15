---
title: 桌面版 AI 扩展
description: 为 TrailSnap 桌面版安装人脸识别、OCR、分类、语义检索和本地大模型能力。
---

# 桌面版 AI 扩展使用说明

TrailSnap 桌面版将 AI 运行环境与基础安装包分开发布。这样不使用 AI 的用户无需下载大型依赖，需要时再安装一次与你的操作系统匹配的扩展包即可。

::: info Docker 用户
Docker 版的 AI 服务已经由 `docker-compose.yml` 管理，不需要安装桌面 AI 扩展。本文仅适用于 Windows、macOS 和 Linux 桌面客户端。
:::

## 扩展提供的能力

- 人脸检测、识别与聚类
- OCR 文字识别与票据识别
- 图片分类与智能标签
- 图片向量与语义检索
- 本地多模态大模型能力（另需 `llama-server`）

AI Sidecar 只会在相关功能首次调用时启动，空闲后自动停止。卸载扩展不会删除原始照片，但依赖该扩展的新分析任务将无法运行。

## 在线安装（推荐）

1. 先安装并启动 TrailSnap 桌面版。
2. 打开“设置 → AI 扩展包”。
3. 找到适合当前平台的扩展，点击“下载并安装 AI 扩展”。
4. 等待下载、校验和安装完成。安装过程中不要退出客户端。
5. 在同一页面确认扩展显示“已安装”，再创建人脸、OCR、分类等任务。

扩展目录在线访问失败时，可点击“刷新清单”；已安装扩展仍可继续使用。

## 离线导入

1. 打开 [GitHub 最新 Release](https://github.com/LC044/TrailSnap/releases/latest)。
2. 下载与当前平台匹配、名称包含 `TrailSnap-AI` 的 `.tar.gz`：Windows x64 选 `win32-x64`，macOS Apple Silicon 选 `darwin-arm64`，Linux x64 选 `linux-x64`。
3. 不要解压或修改文件。
4. 在“设置 → AI 扩展包”点击“离线导入”，选择下载的文件。
5. 客户端验证清单、平台与校验信息后完成安装。

::: warning 平台必须匹配
扩展包包含原生可执行文件，不能跨操作系统或 CPU 架构使用。只从 TrailSnap 官方 GitHub Release 下载。
:::

## 本地大模型与 llama.cpp

人脸、OCR、分类和语义检索不需要额外安装 `llama-server`。只有使用内置 MiniCPM 本地多模态模型时才需要 llama.cpp 运行时。

- Windows、macOS：在扩展页面的“llama.cpp 运行时”区域点击“一键安装”，完成后点击“重新检测”。
- Linux：自行安装或编译 `llama-server`，确保它位于系统 `PATH` 中，再重启 TrailSnap。

```powershell
# Windows
winget install --id ggml.llamacpp --exact
```

```bash
# macOS
brew install llama.cpp
```

## 扩展与“大模型连接”的区别

桌面 AI 扩展提供人脸、OCR、向量等本地 AI 运行能力；“设置 → AI 相关配置”中的大模型连接用于配置 OpenAI、Ollama 等对话或图片理解接口。两者可以独立使用。第三方模型的配置方法参见 [AI 大模型设置](/docs/guide/settings/aisetting)。

## 常见问题

- **下载失败或清单不可用：** 检查能否访问 GitHub Release，点击“刷新清单”重试，或使用离线导入。
- **安装后仍提示 AI 不可用：** 确认扩展为“已安装”，重启 TrailSnap。仍失败时查看应用数据目录 `logs` 下的 `ai.log` 和 `ai.err.log`。
- **更新或卸载：** 扩展页面支持卸载与重新安装；变更扩展前，正在运行的 AI Sidecar 会停止。
