---
title: Configure TrailSnap MCP
description: Create a least-privilege Agent Token and connect external AI agents to TrailSnap photo search, memory investigation, person timelines, and confirmable album proposals over Streamable HTTP.
outline: [2, 3]
---

# Configure TrailSnap MCP

TrailSnap includes a Model Context Protocol (MCP) server. MCP-compatible AI clients can query the current user's photos, albums, people, and memory clues without accessing the database or original file paths. They can also create album organization proposals that require explicit confirmation inside TrailSnap.

MCP uses a dedicated Agent Token, so an external agent never needs your account JWT or login password.

## 1. Choose the endpoint

TrailSnap MCP uses **Streamable HTTP**:

| Deployment | MCP endpoint |
| --- | --- |
| Docker, NAS, desktop, or reverse-proxy public entry | `https://your-domain.example/api/mcp/` |
| LAN public entry | `http://host-ip:8082/api/mcp/` |
| Direct backend access during development | `http://127.0.0.1:8000/mcp/` |

The unified public entry only requires the TrailSnap frontend port. Do not expose the backend, AI service, or database ports separately. Keep the trailing `/` in the endpoint.

## 2. Create an Agent Token

1. Sign in to TrailSnap.
2. Open **Settings → Token Management**.
3. Select **New Token**, then set a name and expiration time.
4. Grant only the scopes required by the agent.
5. Verify your account password and immediately store the generated `ts_` token securely.

| Scope | Purpose |
| --- | --- |
| `photos:read` | Search photos and investigate memory clues |
| `albums:read` | List albums |
| `people:read` | List people and build person timelines |
| `albums:propose` | Create a proposal for user confirmation; cannot execute it |

::: tip Least privilege
Photo Q&A usually needs only `photos:read`. Add `albums:propose` only when the user wants the agent to organize selected photos.
:::

Store the token securely as soon as it is generated. Never commit it to Git, publish it in an issue or screenshot, or share it with an untrusted agent.

## 3. Configure an MCP client

Configuration locations vary by client, but every client needs the Streamable HTTP endpoint and Bearer token:

```json
{
  "mcpServers": {
    "trailsnap": {
      "type": "http",
      "url": "https://photos.example.com/api/mcp/",
      "headers": {
        "Authorization": "Bearer ts_your_agent_token"
      }
    }
  }
}
```

Some clients call the type `streamable-http` or store headers in a separate authentication section. Follow your client's MCP documentation and replace all example values.

After saving the configuration and restarting the client, these tools should be available:

- `search_photos`: search by date, place, OCR, media type, people, and scores.
- `list_albums`: list albums, covers, and photo counts.
- `list_people`: list visible people and identity IDs.
- `investigate_memory`: find candidate memories from fuzzy time, place, person, and text clues.
- `get_person_timeline`: build an event timeline for a person.
- `propose_album_organization`: create an album proposal that expires after seven days.

Try this prompt to verify the connection:

> Find my 10 most recent photos taken in Shanghai and explain why they matched.

## 4. Configure Pi Agent

Pi does not load a generic MCP configuration directly. The TrailSnap repository provides a Pi Bridge and Skill that register the MCP tools as native Pi tools.

```shell
npm install -g trailsnap-cli
trailsnap config set --url "https://photos.example.com" --token "ts_your_agent_token"
pi install git:github.com/LC044/TrailSnap
```

Run this command inside Pi to verify the connection:

```text
/trailsnap-status
```

The Bridge prefers these environment variables:

```text
TRAILSNAP_MCP_URL=https://photos.example.com/api/mcp/
TRAILSNAP_API_TOKEN=ts_your_agent_token
```

If they are absent, it reuses the URL and token saved by `trailsnap config set`. Pi tool names use the `trailsnap_` prefix, for example `trailsnap_search_photos`.

## 5. Public and reverse-proxy deployment

When TrailSnap is accessed through a domain or LAN address, set the externally reachable site root on the Server service:

```text
TRAILSNAP_PUBLIC_URL=https://photos.example.com
```

Docker Compose example:

```yaml
services:
  server:
    environment:
      TRAILSNAP_PUBLIC_URL: https://photos.example.com
```

The public MCP endpoint becomes `https://photos.example.com/api/mcp/`. Album proposals also contain approval links that an external agent can give directly to the user.

Only configure a dedicated MCP address when MCP uses a separate hostname:

```text
TRAILSNAP_MCP_URL=https://mcp.example.com/mcp/
TRAILSNAP_MCP_ALLOWED_HOSTS=mcp.example.com
```

`TRAILSNAP_MCP_ALLOWED_HOSTS` accepts comma-separated hosts. Add only hosts that actually serve TrailSnap MCP; do not disable Host validation.

## 6. Confirm an album proposal

An agent with `albums:propose` can only create a plan in the `proposed` state. No album, photo relationship, or tag changes occur at this point.

The agent must give the returned `approval_url` to the user. The user signs in with a normal TrailSnap account, reviews the name, photos, cover, and tags, then explicitly confirms or rejects the proposal. An Agent Token cannot confirm, reject, or undo a plan.

## Troubleshooting

### 401 Unauthorized

Check that the header is `Authorization: Bearer ts_...` and that the token has not expired or been revoked. A model-provider API key is not a TrailSnap Agent Token.

### A tool reports a missing scope

Create a new token with the required scope. Person timelines need `people:read`; album proposals need `albums:propose`. Avoid granting every scope by default.

### Invalid Host header over a public address

Set `TRAILSNAP_PUBLIC_URL` to the correct public site root. For a dedicated MCP hostname, add it to `TRAILSNAP_MCP_ALLOWED_HOSTS`.

### The approval URL is relative

Set `TRAILSNAP_PUBLIC_URL` on the Server to return an absolute approval URL. The TrailSnap Pi Bridge also resolves relative URLs against the MCP origin.

### Can an agent delete or move photos?

No. MCP does not expose photo deletion, file moves, renames, direct album mutation, or HTML execution. Use the [TrailSnap CLI](./trailsnap-cli.md) for administrative workflows and protect credentials that allow writes.
