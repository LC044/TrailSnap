---
outline: [2, 3]
---

# OpenClaw / Roo Code

OpenClaw / Roo Code can call TrailSnap CLI as a Skill, so the Agent can query your personal album data through TrailSnap APIs.

## 1. Get an access token

See [Token Settings](../settings/tokensetting.md).

## 2. Install trailsnap-cli and the Skill

You can let the Agent guide you:

```text
Help me install trailsnap-cli and the skill: https://trailsnap.cn/install.md
My TrailSnap address is http://localhost:3180
My token is ts_hV5nsCZxxxxx
```

Or install manually:

```shell
npm install -g trailsnap-cli
npx skills add lc044/trailsnap -y -g
trailsnap config set --url <url> --token <token>
```

## 3. Use it in chat

Examples:

> "Use trailsnap-cli to list the last 20 photos I took in Shanghai."
> "Find photos containing 'boarding gate' text and summarize my flight history."
