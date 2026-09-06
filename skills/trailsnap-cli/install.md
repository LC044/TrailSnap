# TrailSnap  CLI 安装指南

以下步骤面向 AI Agent，部分步骤需要用户在浏览器中配合完成。

## 环境要求

开始安装之前，请确保环境中已安装：

- Node.js（npm/npx 安装需要）
- Python 3（pip 安装需要）


## 第 1 步 安装

根据环境选择安装方式（选择其中一种即可）：

- Node.js 安装：npm/npx 安装
- Python 安装：pip 安装

### npm/npx 安装

```shell
# 安装 CLI
npm install -g trailsnap-cli

# 安装 CLI SKILL（必需）
npx skills add lc044/trailsnap  -y -g
```

### pip 安装

```shell
# 安装 CLI
pip install trailsnap-cli

# 安装 CLI SKILL（必需）
npx skills add lc044/trailsnap  -y -g
```

## 第 2 步 配置 API URL 和 Agent Token

Agent 需要询问用户 TrailSnap 的访问地址和 `ts_` 开头的只读 Agent Token（如何获取请参考[TrailSnap API 文档](https://trailsnap.cn/docs/guide/settings/tokensetting.html)），收到用户输入后执行。不要把 Token 输出到日志或提交到仓库：

```shell
trailsnap config set --url <url> --token <ts_token>
```

## 第 3 步 验证

```shell
trailsnap photos list --limit 1
```
