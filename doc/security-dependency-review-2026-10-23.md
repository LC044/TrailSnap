# Dependabot 依赖安全审查（2026-10-23）

## 结论与范围

关联需求：[REQ-197](https://feedback.trailsnap.cn/REQ-197)。通过已认证 GitHub API 分页读取当前未关闭的 Dependabot 告警，共 169 条：critical 22、high 77、medium 58、low 12。同一依赖及漏洞在多个清单出现会重复计数，不代表 169 个独立漏洞或已经发生入侵。

将每条告警的受影响版本区间与对应清单/锁文件中的全部同名版本逐一比较，163 条已移除受影响版本，6 条仍保留。这是修复时的本地依赖覆盖结果，未 dismiss 告警；用户已授权提交、推送及 CI 通过后合并，GitHub 状态以默认分支重新扫描为准。

Code scanning API 返回 `no analysis found`，无法据此宣称代码扫描通过。Secret scanning API 返回未启用，亦未验证密钥扫描结果。

## 主要修改

- Server / AI：Pillow 升至 13.0.0（覆盖两模块共 78 条图像解析告警）；Server 同步升级 aiohttp、MCP、multidict、Mako、OpenTelemetry API；AI 升级 fsspec；四个 Python 项目升级 certifi。
- 主前端 / 官网 / 需求平台：DOMPurify、Markdown、Vue、Vite、Vitest 及相关传递依赖升级。CSS selector parser 从旧版 6.x 更新到 7.1.6，并通过构建验证。需求平台 npm / pnpm 两份锁文件均更新。
- 移动端 Capacitor Android / iOS / core / CLI 对齐 8.5.1；桌面 rustls 更新到 0.23.45；Pi MCP SDK 更新到 1.32.0。
- 使用包管理器重新解析依赖及校验信息，没有手工伪造锁文件版本或校验值。保留已有业务工作区修改。

## 保留的 6 条

| 告警 | 原因、现有防护和后续处理 |
| --- | --- |
| [#483](https://github.com/LC044/TrailSnap/security/dependabot/483)、[#479](https://github.com/LC044/TrailSnap/security/dependabot/479) python-jose | 公告未给出修复版本。DER 公钥与 HMAC 算法混淆；现有解码均显式指定 algorithms，需求平台固定 HS256，主服务默认 HS256。没有据此关闭告警：应另行迁移到受维护的 JWT 实现，并验证令牌兼容性、异常类型、过期时间与算法限制。 |
| [#39](https://github.com/LC044/TrailSnap/security/dependabot/39)、[#349](https://github.com/LC044/TrailSnap/security/dependabot/349) ecdsa | python-jose 传递依赖，无修复版本；Minerva 影响 ECDSA 签名等操作。项目默认使用 HS256，不能据此保证所有自定义配置安全。随 JWT 库迁移移除依赖。 |
| [#333](https://github.com/LC044/TrailSnap/security/dependabot/333) glib | Tauri/GTK 依赖 glib 0.18.5，修复从 0.20.0 开始；额外安装新版不能消除旧版。需要上游依赖链迁移或审查后的修复回移，并在 Linux 验证。Windows Rust 测试不能证明该 Linux 依赖问题已解决。 |
| [#469](https://github.com/LC044/TrailSnap/security/dependabot/469) brace-expansion | Pi 0.99.2 发布包的嵌套 shrinkwrap 固定 5.0.9。已尝试 override，但 npm 仍保留旧版，因此撤除无效 override。查询上游最新版本仍是 0.99.2，需要其更新嵌套锁文件；未擅自手改发布包。npm audit 仍报告该依赖风险。 |

参考：[python-jose 公告](https://github.com/advisories/GHSA-3qf3-8w2g-rqmx)、[ecdsa 公告](https://github.com/advisories/GHSA-wj6h-64fc-37mp)、[glib 公告](https://github.com/advisories/GHSA-wrw7-89jp-8q8g)。

## 补充 npm/pnpm 审计

包管理器审计发现初始 GitHub 快照之外的构建依赖问题：主前端 `yaml` 2.7.1 的深层嵌套栈溢出已通过 `yaml@2 >=2.8.3` override 修复；主前端和官网仍有 Tailwind/Chokidar 链引入的 `braces` 3.0.3 深层模式栈耗尽问题，公告暂无修复版本。保留风险，后续随构建工具链迁移解决；这不计入上述 169 条的 6 条剩余数。

参考：[YAML](https://github.com/advisories/GHSA-48c2-rrv3-qjmp)、[braces](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)。

## 验证

以下本地结果来自修复工作区（包含用户已有业务修改）；PR 从干净的 master 单独应用本次依赖修改，精确提交另由 GitHub CI 验证。

测试统一入口：`tests/scripts/run-tests.ps1 -Layer unit -Component <组件> -Level smoke`；需求平台使用 `-Level all`。

- 主前端：197 passed。
- 需求平台后端：36 passed。
- CLI：13 passed。
- 桌面：54 passed、1 ignored；测试进程设置 `TAURI_CONFIG={"bundle":{"resources":[]}}`，绕过本地缺失的打包资源。仅验证 Windows Rust 单元测试，未验证完整安装包和 Linux GTK。
- 主前端、官网、需求平台前端生产构建：通过（已有 chunk 大小、语法高亮提示）。
- Pi TypeScript 检查：通过；本机 Node 22.14.0 低于 Pi 依赖要求的 22.19.0，未声明 Pi 运行时全面验收。
- 四个 Python 项目 `uv lock --check`：通过；三处 pnpm frozen-lockfile 安装：通过；需求平台 npm audit：0 vulnerabilities。
- AI：405 passed；主后端：3405 passed、7 skipped、48 deselected。存在既有 marker/弃用/未等待 coroutine 等 warning，未计作测试失败。开发服务占用原虚拟环境文件，使用临时 `UV_PROJECT_ENVIRONMENT` 独立安装和测试，没有停止开发服务。
- 未做 Android/iOS 原生构建、完整 AI 模型推理、端到端与部署测试。

## 按清单逐项覆盖

“覆盖”仅指全部解析版本均不在该条告警区间；不等于业务已无任何安全风险。

| 清单 / 包 | 最终版本 | 覆盖 / 告警数 | 告警编号 |
| --- | --- | --- | --- |
| `integrations/pi/package-lock.json` / `@modelcontextprotocol/sdk` | 1.32.0 | 5/5 | #517, #516, #515, #513, #472 |
| `integrations/pi/package-lock.json` / `brace-expansion` | 5.0.9 | 0/1 | #469 |
| `integrations/pi/package-lock.json` / `ip-address` | 10.7.4 | 1/1 | #608 |
| `package/ai/uv.lock` / `certifi` | 2026.10.23 | 1/1 | #518 |
| `package/ai/uv.lock` / `fsspec` | 2026.9.0 | 1/1 | #473 |
| `package/ai/uv.lock` / `pillow` | 13.0.0 | 39/39 | #619, #618, #617, #616, #615, #614, #613, #612, #611, #610, #609, #546, #545, #544, #543, #542, #541, #540, #539, #538, #537, #536, #535, #534, #533, #532, #531, #530, #529, #528, #527, #526, #525, #524, #523, #522, #521, #520, #519 |
| `package/desktop/src-tauri/Cargo.lock` / `glib` | 0.18.5 | 0/1 | #333 |
| `package/desktop/src-tauri/Cargo.lock` / `rustls` | 0.23.45 | 1/1 | #474 |
| `package/official-site/pnpm-lock.yaml` / `@vue/server-renderer` | 3.5.44 | 1/1 | #475 |
| `package/official-site/pnpm-lock.yaml` / `dompurify` | 3.4.17 | 3/3 | #622, #621, #620 |
| `package/official-site/pnpm-lock.yaml` / `katex` | 0.18.10 | 1/1 | #478 |
| `package/official-site/pnpm-lock.yaml` / `postcss-selector-parser` | 7.1.6 | 1/1 | #476 |
| `package/official-site/pnpm-lock.yaml` / `source-map-js` | 1.2.2 | 1/1 | #477 |
| `package/official-site/pnpm-lock.yaml` / `vite` | 7.3.7 | 5/5 | #551, #550, #549, #548, #547 |
| `package/requirement-platform/server/uv.lock` / `certifi` | 2026.10.23 | 1/1 | #552 |
| `package/requirement-platform/server/uv.lock` / `ecdsa` | 0.19.2 | 0/1 | #349 |
| `package/requirement-platform/server/uv.lock` / `mako` | 1.4.3 | 1/1 | #480 |
| `package/requirement-platform/server/uv.lock` / `opentelemetry-api` | 1.45.1 | 1/1 | #623 |
| `package/requirement-platform/server/uv.lock` / `python-jose` | 3.5.0 | 0/1 | #479 |
| `package/requirement-platform/web/package-lock.json` / `@vitest/mocker` | 4.1.12 | 2/2 | #559, #558 |
| `package/requirement-platform/web/package-lock.json` / `follow-redirects` | 1.16.1 | 2/2 | #510, #507 |
| `package/requirement-platform/web/package-lock.json` / `markdown-it` | 15.0.3 | 3/3 | #504, #502, #501 |
| `package/requirement-platform/web/package-lock.json` / `source-map-js` | 1.2.2 | 1/1 | #481 |
| `package/requirement-platform/web/package-lock.json` / `vite` | 6.4.5 | 5/5 | #557, #556, #555, #554, #553 |
| `package/requirement-platform/web/pnpm-lock.yaml` / `@vitest/mocker` | 4.1.12 | 2/2 | #566, #565 |
| `package/requirement-platform/web/pnpm-lock.yaml` / `follow-redirects` | 1.16.1 | 2/2 | #511, #508 |
| `package/requirement-platform/web/pnpm-lock.yaml` / `markdown-it` | 15.0.3 | 2/2 | #505, #503 |
| `package/requirement-platform/web/pnpm-lock.yaml` / `source-map-js` | 1.2.2 | 1/1 | #482 |
| `package/requirement-platform/web/pnpm-lock.yaml` / `vite` | 6.4.5 | 5/5 | #564, #563, #562, #561, #560 |
| `package/server/uv.lock` / `aiohttp` | 3.14.5 | 8/8 | #572, #571, #570, #569, #568, #500, #499, #498 |
| `package/server/uv.lock` / `certifi` | 2026.10.23 | 1/1 | #567 |
| `package/server/uv.lock` / `ecdsa` | 0.19.2 | 0/1 | #39 |
| `package/server/uv.lock` / `mako` | 1.4.3 | 1/1 | #485 |
| `package/server/uv.lock` / `mcp` | 2.2.0 | 1/1 | #497 |
| `package/server/uv.lock` / `multidict` | 6.9.1 | 1/1 | #484 |
| `package/server/uv.lock` / `opentelemetry-api` | 1.45.1 | 1/1 | #634 |
| `package/server/uv.lock` / `pillow` | 13.0.0 | 39/39 | #635, #633, #632, #631, #630, #629, #628, #627, #626, #625, #624, #600, #599, #598, #597, #596, #595, #594, #593, #592, #591, #590, #589, #588, #587, #586, #585, #584, #583, #582, #581, #580, #579, #578, #577, #576, #575, #574, #573 |
| `package/server/uv.lock` / `python-jose` | 3.5.0 | 0/1 | #483 |
| `package/trailsnap-cli/uv.lock` / `certifi` | 2026.10.23 | 1/1 | #601 |
| `package/website/package.json` / `@capacitor/android` | 8.5.1 | 1/1 | #486 |
| `package/website/package.json` / `@capacitor/ios` | 8.5.1 | 1/1 | #487 |
| `package/website/pnpm-lock.yaml` / `@capacitor/android` | 8.5.1 | 1/1 | #489 |
| `package/website/pnpm-lock.yaml` / `@capacitor/ios` | 8.5.1 | 1/1 | #490 |
| `package/website/pnpm-lock.yaml` / `@vue/server-renderer` | 3.5.44 | 1/1 | #488 |
| `package/website/pnpm-lock.yaml` / `dompurify` | 3.4.17 | 3/3 | #638, #637, #636 |
| `package/website/pnpm-lock.yaml` / `follow-redirects` | 1.16.1 | 2/2 | #509, #506 |
| `package/website/pnpm-lock.yaml` / `handlebars` | 4.7.10 | 3/3 | #496, #495, #494 |
| `package/website/pnpm-lock.yaml` / `markdown-it` | 14.3.3 | 2/2 | #605, #514 |
| `package/website/pnpm-lock.yaml` / `postcss-selector-parser` | 7.1.6 | 1/1 | #491 |
| `package/website/pnpm-lock.yaml` / `source-map-js` | 1.2.2 | 1/1 | #492 |
| `package/website/pnpm-lock.yaml` / `vite` | 6.4.5 | 5/5 | #607, #606, #604, #603, #602 |
