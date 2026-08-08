# 设置访问令牌

::: info Token 设置
使用token可以让第三方应用访问TrailSnap的后端API，你可以从TrailSnap后端获取一个Token。
:::

## 获取 Token

打开 “设置” -> “令牌管理” -> “新增令牌”，输入令牌名称和过期时间，验证账号登录密码之后即可获取到Token。

token示例：`ts_hV5nsCZJDheBvvmcd5L248IiAUnIwwZAn`

## API URL

TrailSnap API URL 为 `http://<TrailSnap 主机IP>:8800/`（取决于docker端口映射）。

```yaml
  server:
    image: crpi-d7wuvvdylhqugyu2.cn-hangzhou.personal.cr.aliyuncs.com/siyuan044/trailsnap-server:latest
    restart: always
    expose: [ "8000" ]
    ports: [ "8800:8000" ]
```

这里的 `8800` 是TrailSnap的端口号，你可以根据实际情况修改。

## 使用token

参考[TrailSnap CLI 工具](/docs/guide/agent/trailsnap-cli)
