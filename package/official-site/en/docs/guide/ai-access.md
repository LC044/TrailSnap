---
title: AI Agent Documentation Access
description: Stable, low-noise documentation entry points for AI agents, including llms.txt, a structured index, and Markdown mirrors.
---

# AI Agent Documentation Access

Besides the human-oriented website, TrailSnap publishes stable text entry points for AI agents. Agents can read plain-text documentation without parsing navigation, search UI, or rendered HTML.

## Recommended entry points

| Entry point | URL | Use it for |
| --- | --- | --- |
| Documentation index | [/llms.txt](/llms.txt) | Browse all docs by category; links point to Markdown source |
| Full documentation | [/llms-full.txt](/llms-full.txt) | Read the user guide, deployment guide, agent guide, and core developer docs in one file |
| Structured index | [/ai-docs.json](/ai-docs.json) | Programmatically read titles, descriptions, categories, languages, HTML URLs, and Markdown URLs |
| CLI installation prompt | [/install.md](https://trailsnap.cn/install.md) | Agent-oriented installation and configuration flow for `trailsnap-cli` |
| Sitemap | [/sitemap.xml](/sitemap.xml) | Discover all indexable website pages |

## Markdown mirror rule

Every selected documentation page is published in both HTML and Markdown:

- Human page: `/en/docs/guide/install.html`
- AI-friendly source: `/en/docs/guide/install.md`
- Directory page: `/en/docs/guide/agent/` and `/en/docs/guide/agent/index.md`
- Chinese documentation: `/docs/guide/install.html` and `/docs/guide/install.md`

An agent can therefore replace `.html` with `.md` in a documentation URL and read the original Markdown directly.

## Recommended reading order

1. Read [/llms.txt](/llms.txt) first to identify the relevant document.
2. For a single topic, read only its `.md` file to preserve context.
3. Read [/llms-full.txt](/llms-full.txt) when broader background is required.
4. Read [/ai-docs.json](/ai-docs.json) when processing the documentation list programmatically.
5. To install or call TrailSnap CLI, read [/install.md](https://trailsnap.cn/install.md) and the [TrailSnap CLI guide](/en/docs/guide/agent/trailsnap-cli.md).

## Guidance for agents

- **Read the index first, then the needed document.** `llms.txt` avoids homepage and navigation noise.
- **Prefer Markdown source.** Markdown has no page scripts or rendering noise and preserves source structure.
- **Keep language consistent.** Use Chinese docs for Chinese users and `/en/docs/...` for English users.
- **Separate human-only steps.** Ask users to complete browser login, token creation, or photo-directory authorization manually; never guess credentials.
- **Verify CLI configuration.** Before running `trailsnap`, confirm the API URL and token with `trailsnap config set`.

