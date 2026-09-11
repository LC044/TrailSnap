# 手机 App 单一 Server 网络边界

TrailSnap 手机 App 的运行原则是：安装包包含前端代码、字体、图标、默认图片和其他静态资源；运行时只连接用户选定的自部署 TrailSnap Server。这里的“离线”指 App 不直连任何第三方服务，Server 是否允许访问互联网由部署者决定。

## 已实施的边界

- Android WebView 在原生层按协议、主机和端口校验每个 HTTP(S) 请求。首次连接设置完成后，仅 Capacitor 本地资源与所选 Server 同源请求可通过。
- iOS/Android 共用的浏览器层策略同时限制 `fetch`、XHR、EventSource、WebSocket 和 `sendBeacon`；手机 App 内的外部链接不会跳转或唤起外部站点。
- 天地图 SDK、瓦片、搜索和地理编码均通过 `/api/system/map-proxy/...` 转发。代理只允许天地图官方固定域名，不能作为通用代理使用。
- 天地图使用服务端 Key。真实 Key 只保存在用户的 Server 配置中；App 先获取短期、限地图用途的访问令牌，SDK、瓦片、搜索和地理编码请求由 Server 注入真实 Key 后转发，不依赖 WebView 的 Origin 或域名白名单。
- 从旧版本升级时，管理员必须在天地图控制台创建服务端 Key 并替换原浏览器端 Key；原 Key 不会自动转换。如启用 IP 白名单，应填写 TrailSnap Server 的公网出口 IP。
- Server 的定时更新任务每 6 小时检查版本并将最新 Android APK 原子下载到 `TS_DATA_DIR/app_updates/`。App 检查更新时只会收到 `/api/system/app-update-download/{version}`，Android 原生下载器还会拒绝非当前 Server 地址以及跨源重定向。
- 默认头像、空相册封面和软木纹理已经本地化，不再从公共占位图或纹理站点加载。

## 首次连接例外

尚未保存 Server 地址时，连接页需要探测 mDNS/LAN 服务或测试用户手动输入的公网自部署地址，因此网络白名单尚未收紧。地址保存后策略立即变为精确同源；清除 App 数据会重新进入首次连接状态。

## 切换 Server 的临时放行

连接页对候选地址是"先测试、后保存"：测试请求发出时已保存的还是旧地址，原生层与浏览器层都会把新源当作外部请求。为此 `withTemporaryServerAccess()`（浏览器层）和 `NativeNetworkPolicy` 插件（Android 原生层，`OfflineOnlyWebViewClient`）在同一时刻临时放行候选 origin：测试请求发出前注册，带 30 秒过期兜底，测试结束（成功或失败）即撤销。两层必须同时放行，缺一层时表现为 `Failed to fetch`（Android 原生层返回无 CORS 头的 403）。旧版 App（< v0.14.1）浏览器层也没有放行，报"已阻止外部网络请求"。

## 上架构建注意事项

当前 Android 自托管分发包包含 `REQUEST_INSTALL_PACKAGES`，用于用户确认后的 APK 自更新。Google Play 等商店通常会严格审核这项权限；正式商店渠道应建立单独 flavor，移除该权限和 App 内安装入口，交由应用商店更新。该渠道差异不改变 App 业务流量只访问自部署 Server 的原则。
