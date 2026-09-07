# Token Settings

::: info Token
Using a token allows third-party apps (such as TrailSnap CLI or Agent Skills) to access TrailSnap Backend APIs.
:::

## Get a Token

Open **Settings** → **Token Management** → **New Token**, then set a name and expiration time. After verifying your account password, you will get a token.

Example token: `ts_hV5nsCZJDheBvvmcd5L248IiAUnIwwZAn`

## API URL

Third-party clients use the unified TrailSnap address, for example `http://<TrailSnap host IP>:3180`. The CLI automatically uses its `/api` path.

```yaml
  frontend:
    ports: [ "3180:80" ]
```

Here, `3180` is the only user-facing port. Server, AI, and database ports stay inside the Docker network.

## Use the Token

Agent Tokens support least-privilege scopes. Select photo, album, and people read scopes for queries. Grant **Propose albums** only when an external agent needs to organize selected photos; this scope creates a pending plan and cannot modify an album directly.

- MCP clients: see [Configure TrailSnap MCP](/en/docs/guide/agent/mcp).
- Command-line access: see [TrailSnap CLI](/en/docs/guide/agent/trailsnap-cli).
