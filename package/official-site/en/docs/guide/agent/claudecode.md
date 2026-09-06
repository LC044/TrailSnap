# Claude Code

> Use the trailsnap-cli skill in Claude Code to manage your album with AI.

## 1. Get an access token

See [Token Settings](../settings/tokensetting.md).

## 2. Install Claude Code

See the official docs: [Claude Code setup](https://code.claude.com/docs/en/setup).

## 3. Install trailsnap-cli skill

:::tabs
== Agent guided install

Copy the prompt below to your Agent (OpenClaw, Claude Code, Cursor, TRAE, etc.). It will guide you to add the token and finish installation:

```text
Help me install trailsnap-cli and the skill: https://trailsnap.cn/install.md
My TrailSnap address is http://localhost:3180
My token is ts_hV5nsCZxxxxx
```

![alt text](/images/wechat_longscreenshot_2026-04-27_224237_662.jpg)

== Manual install

Choose one install method:

- Node.js: npm/npx
- Python: pip

#### npm/npx

```shell
npm install -g trailsnap-cli
npx skills add lc044/trailsnap -y -g
```

#### pip

```shell
pip install trailsnap-cli
npx skills add lc044/trailsnap -y -g
```

#### Configure API URL and token

```shell
trailsnap config set --url <url> --token <token>
```

#### Verify

```shell
trailsnap photos list --limit 1
```
:::

## Use the Skill

Ask Claude in natural language:

> "Use the trailsnap-cli skill and list my recent photos taken in Xi'an."
> "Where did I travel last National Day? Generate an HTML travel diary for me."
