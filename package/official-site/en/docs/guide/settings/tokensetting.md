# Token Settings

::: info Token
Using a token allows third-party apps (such as TrailSnap CLI or Agent Skills) to access TrailSnap Backend APIs.
:::

## Get a Token

Open **Settings** → **Token Management** → **New Token**, then set a name and expiration time. After verifying your account password, you will get a token.

Example token: `ts_hV5nsCZJDheBvvmcd5L248IiAUnIwwZAn`

## API URL

Third-party clients use the unified TrailSnap address, for example `http://<TrailSnap host IP>:8082`. The CLI automatically uses its `/api` path.

```yaml
  frontend:
    ports: [ "8082:80" ]
```

Here, `8082` is the only user-facing port. Server, AI, and database ports stay inside the Docker network.

## Use the Token

See [TrailSnap CLI](/en/docs/guide/agent/trailsnap-cli).
