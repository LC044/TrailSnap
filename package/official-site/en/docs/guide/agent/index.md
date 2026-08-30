---
outline: [2, 3]
---

# Agent Skills

TrailSnap CLI can be used as an Agent tool (Skill) in different AI coding assistants or Agent platforms, such as Claude Code and OpenClaw / Roo Code. By letting the Agent call the CLI, AI can query and analyze your album data and answer questions based on your personal library.

1. Claude Code  
   [How to use](./claudecode.md)

2. OpenClaw / Roo Code and other IDE Agents  
   [How to use](./openclaw.md)

3. Other Agent platforms

If you use Dify, Coze, FastGPT, or your own Agent framework, you can wrap the CLI as a system tool.

Copy the prompt below to your Agent (OpenClaw, Claude Code, Cursor, TRAE, etc.). It will guide you to add the token and finish installation:

```text
Help me install trailsnap-cli and the skill: https://trailsnap.cn/install.md
My TrailSnap address is http://localhost:8082
My token is ts_hV5nsCZxxxxx
```

## Use the Skill

Ask your Agent in natural language:

> "Use the trailsnap-cli skill and list my recent photos taken in Xi'an."
> "Where did I travel last National Day? Generate an HTML travel diary for me."

👉 [View an AI-generated travel diary example](/examples/travel-diary-2025-golden-week.html)
