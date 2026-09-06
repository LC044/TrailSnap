---
name: "trailsnap-cli"
description: "Query photos, albums, locations, tags, and people from a TrailSnap instance through its command-line client. Use when TrailSnap MCP tools are unavailable and the user asks about their own photo library; Agent Tokens are read-only, so do not use this skill to mutate library data."
---

# TrailSnap CLI 技能

当原生 TrailSnap MCP 工具不可用时，使用 `trailsnap` CLI 查询 TrailSnap；两者同时可用时优先 MCP。

## 功能
1. 根据指定条件（可选过滤参数）查询照片列表。
2. 查询分类标签、相册、位置和人物（面部）信息。
3. 查询某张照片的详细信息。

## 安装

使用以下命令检查是否安装了 `trailsnap` 工具，如果没有安装则可以参考[install.md](install.md)文档进行安装。

```bash
trailsnap -v
```

## 初始配置

首次使用需要配置 API 地址和 `ts_` 开头的只读 Agent Token。用以下命令检查配置：

```bash
trailsnap photos list --limit 1
```

如果收到配置错误，询问用户这两个信息，然后执行；不要把 Token 输出到日志或提交到仓库：
```bash
trailsnap config set --url <API_BASE_URL> --token <YOUR_API_TOKEN>
```

## 使用方法

使用前可以通过 `trailsnap <command> -h` 或 `trailsnap <command> <subcommand> -h` 查看每个命令的详细帮助信息。通常情况下，你需要先根据用户的问题逐步筛选出检索条件（一个简单的[示例](examples/simple.md)），然后查询符合条件的照片列表。

- `locations timeline` 命令能够查到时间和空间上的信息，是一个很好的工具，返回一个足迹时间轴（某一段时间去了那个地方）。
- 除非用户不需要显示照片，否则以合适格式展示照片；使用 `medias get --format url` 获取地址，保留返回值，不要编造路径。
- 在使用之前你需要阅读 [reference.md](reference.md) 文件，了解每个命令的详细参数和选项。
- 如果需要的话，可以参考 [examples/simple.md](examples/simple.md) 文件，了解如何使用该工具。
- Agent Token 仅允许匹配 scope 的读取。不要调用删除、toolbox、任务变更、上传或其他写命令，也不要声称已经修改相册。
- AI 描述、人脸匹配与回忆候选属于推断证据，不应表述为已确认事实。

使用 Python 运行脚本：

```bash
trailsnap <command> <subcommand> [options]
```
