# Token Settings

::: info Token
Using a token allows third-party apps (such as TrailSnap CLI or Agent Skills) to access TrailSnap Backend APIs.
:::

## Get a Token

Open **Settings** → **Token Management** → **New Token**, then set a name and expiration time. After verifying your account password, you will get a token.

Example token: `ts_hV5nsCZJDheBvvmcd5L248IiAUnIwwZAn`

## API URL

TrailSnap API URL is `http://<TrailSnap host IP>:8800/` (depends on your Docker port mapping).

```yaml
  server:
    image: crpi-d7wuvvdylhqugyu2.cn-hangzhou.personal.cr.aliyuncs.com/siyuan044/trailsnap-server:latest
    restart: always
    expose: [ "8000" ]
    ports: [ "8800:8000" ]
```

Here, `8800` is the port exposed on the host. Adjust it to your actual setup.

## Use the Token

See [TrailSnap CLI](/en/docs/guide/agent/trailsnap-cli).
