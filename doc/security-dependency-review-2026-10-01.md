# Dependabot 依赖安全审查（2026-10-01）

## 范围与结果

- 来源：`gh api repos/LC044/TrailSnap/dependabot/alerts?state=open` 的已认证分页结果。
- 初始未关闭警告：244 条（critical 4、high 93、medium 117、low 30）。同一漏洞可能覆盖多个模块；数量不是独立漏洞数量。
- 将每条警告的受影响版本区间与当前全部锁文件版本逐一比较：240 条已移除受影响版本，4 条仍保留（high 2、medium 2）。
- 这是本地锁文件评估，不代表 GitHub 页面已关闭警告。变更进入默认分支并完成依赖扫描后，以 GitHub 实际状态为准。
- 未 dismiss 任何警告；未推送、发布或改变远端安全设置。

## 如何判断是否需要修复

| 依赖/使用位置 | 适用性判断 | 本次处理 |
| --- | --- | --- |
| DOMPurify、markdown-it、Mermaid、ECharts | 存在 HTML/Markdown/图表渲染入口；是否可利用取决于不可信内容、渲染参数和对应漏洞路径。应优先升级，不能仅因内容通常可信就判误报。 | 升级渲染依赖及其传递依赖。 |
| axios | 浏览器端会用到 axios。HTTP/2、Node HTTP adapter、代理等专用漏洞未必适用于浏览器请求，fetch adapter 类问题则需看实际配置；版本升级仍合理。 | 升级至 1.20.0。 |
| aiohttp、Starlette、python-multipart、requests、urllib3 | 请求解析、文件上传、下载和代理请求可能处理不可信数据。属于值得优先解决的服务端依赖风险。 | 更新兼容的 FastAPI/Starlette 组合与网络依赖。 |
| Pillow-HEIF、ONNX、Sharp | 主服务处理上传图片；AI 使用本地 ONNX 模型；Sharp 在移动端资源构建链。图片/模型来源和调用路径决定实际暴露程度。 | 更新依赖；验证 Sharp 编码和本地 ONNX CLIP 推理。 |
| Transformers | 应用主要使用 tokenizer、image processor 和 ONNX 推理，不使用 Trainer 或 Transformers 的模型推理路径；部分漏洞路径不直接适用。 | 升级 5.18.0 与 ModelScope 1.40.1，避免保留已知漏洞版本。 |
| LangChain/LangGraph/LangSmith | Agent 会用到工具调用、状态和消息；具体可利用性取决于漏洞涉及的接口及不可信输入。 | 更新受影响依赖，保留 OpenAI SDK 2.x。 |
| Vitest、pytest、构建工具和 CLI 测试依赖 | 不等同于线上服务的直接攻击面，但仍可能影响开发、CI 和处理不可信文件的构建过程。 | 更新可兼容版本，未将开发依赖风险标为误报。 |

## 尚未解决的 4 条

| 警告 | 原因与适用性 | 后续建议 |
| --- | --- | --- |
| [#39](https://github.com/LC044/TrailSnap/security/dependabot/39)、[#349](https://github.com/LC044/TrailSnap/security/dependabot/349)：ecdsa Minerva | 上游没有修复版本，影响 ECDSA 签名/密钥生成/ECDH；验签不受影响。主服务默认 HS256，需求平台固定 HS256。`python-jose[cryptography]` 当前实际 EC backend 是 `jose.backends.cryptography_backend`，未发现业务直接调用 ecdsa 的签名 API。当前代码路径下风险较低，但不能推断所有部署配置。 | 保留告警。单独迁移 python-jose 到 PyJWT 等受维护实现，补齐令牌兼容性、异常类型及认证回归后移除传递依赖。 |
| [#333](https://github.com/LC044/TrailSnap/security/dependabot/333)：glib 0.18.5 | 修复版本为 0.20.0。当前 Tauri 2 → tauri-runtime-wry/wry → WebKitGTK/GTK 0.18 依赖旧 glib；仅额外添加 glib 0.20 不会消除原有依赖。应用 Rust 源码未发现直接使用 VariantStrIter，但不能排除上游调用。 | 跟踪 Tauri/GTK 依赖链迁移；必要时对上游旧分支做修复回移并完成 Linux 构建验证。此次没有强行改 Cargo.lock。 |
| [#399](https://github.com/LC044/TrailSnap/security/dependabot/399)：brace-expansion 5.0.9 | 位于 Pi 集成开发依赖。Pi 0.99.2 已更新 undici 至 8.10.2，但其发布包的 npm-shrinkwrap 仍固定 brace-expansion 5.0.9；已实测 npm override 无法替换这一嵌套锁定。 | 跟踪 Pi 上游更新 shrinkwrap 至 brace-expansion ≥5.0.12；如必须提前清零，需要维护/替换上游包并验证完整 Pi 行为。 |

参考：[ecdsa 公告](https://github.com/advisories/GHSA-wj6h-64fc-37mp)、[glib 公告](https://github.com/advisories/GHSA-wrw7-89jp-8q8g)。

## 兼容性与验证

- 主服务：FastAPI 0.142.2 / Starlette 1.7.0，LangChain 1.3.9 / langchain-openai 1.1.14；OpenAI SDK 保留 2.29.0，并声明 `<3`。
- AI：Transformers 4→5 是主版本升级。ModelScope 同步升级；使用现有本地 CLIP tokenizer、image processor，文本和图像 ONNX 推理均得到 `(1, 512)` 输出。没有下载新模型权重。
- 前端：通过 pnpm 的按版本范围 overrides 更新传递依赖；Mermaid 10 和 11 分别更新到本分支安全版本。Sharp 0.32→0.35、tar 6→7、uuid 7→11 涉及跨主版本替换，当前构建及资源工具入口验证通过，完整 Android/iOS 资源生成和打包仍需发布流程验证。
- CLI：运行时仍为 Python ≥3.9 且无第三方依赖；仅 dev 组要求 Python ≥3.10，使 pytest/requests/urllib3 可以选用安全版本。Python 3.9 开发者需升级测试解释器；使用 wheel/pip 安装运行不受影响。
- Pi 开发依赖升级到 0.99.2，Node ≥22.19 是其原有要求；本机 22.14 安装有 engine 提示，TypeScript 检查与两项现有测试通过。仍建议在受支持 Node 版本下执行发布前验证。
- 需求平台保留 npm 与 pnpm 双锁文件；npm override 将传递 Vite 固定到直接依赖范围，避免 npm 解析 Vitest 可选 peer 时的 `edgesOut` 错误。

已执行：

- `pwsh tests/scripts/run-tests.ps1 -Layer unit -Level smoke`：后端 2677 通过、AI 373 通过、CLI 13 通过。
- CLI dev 组调整后再经统一入口执行 CLI smoke：13 通过。
- `pnpm build`（主前端）与 `pnpm docs:build`（官网）通过。
- 需求平台前端 `pnpm test`：2 通过；`pnpm build`（包含 vue-tsc）通过；在独立临时目录验证 `npm ci` 成功。
- `npm run check:pi` 与 `npm run test:pi`：类型检查通过、2 项测试通过。
- `capacitor-assets --help` 与从其实际依赖链加载 Sharp 编码 PNG 成功。
- 未执行真实服务 E2E、需求平台后端流程测试、全平台桌面/移动端打包。Rust 离线依赖树命令因缺缓存未完成；glib 依赖关系由 Cargo.lock 核实。

## 按锁文件核对的明细

“消除”表示该快照警告的版本区间不再命中当前锁文件；依赖被移除也算消除。未声称消除快照以外的新漏洞。

| 锁文件 | 原警告数 | 本地消除 | 剩余 |
| --- | ---: | ---: | ---: |
| `package-lock.json` | 10 | 9 | 1 |
| `package/ai/uv.lock` | 23 | 23 | 0 |
| `package/desktop/src-tauri/Cargo.lock` | 1 | 0 | 1 |
| `package/official-site/pnpm-lock.yaml` | 50 | 50 | 0 |
| `package/requirement-platform/server/uv.lock` | 14 | 13 | 1 |
| `package/requirement-platform/web/package-lock.json` | 3 | 3 | 0 |
| `package/requirement-platform/web/pnpm-lock.yaml` | 3 | 3 | 0 |
| `package/server/uv.lock` | 63 | 62 | 1 |
| `package/trailsnap-cli/uv.lock` | 7 | 7 | 0 |
| `package/website/pnpm-lock.yaml` | 70 | 70 | 0 |

| 依赖（按锁文件分组） | 当前锁定版本 | 消除/总数 | 警告编号 |
| --- | --- | ---: | --- |
| `package-lock.json` / `brace-expansion` | 5.0.9 | 0/1 | #399 |
| `package-lock.json` / `fast-uri` | 3.1.8 | 1/1 | #402 |
| `package-lock.json` / `ip-address` | 10.7.2 | 2/2 | #401, #400 |
| `package-lock.json` / `undici` | 8.10.2 | 6/6 | #394, #393, #392, #391, #390, #389 |
| `package/ai/uv.lock` / `anyio` | 4.14.2 | 2/2 | #382, #381 |
| `package/ai/uv.lock` / `filelock` | 3.20.3 | 1/1 | #4 |
| `package/ai/uv.lock` / `idna` | 3.20 | 1/1 | #154 |
| `package/ai/uv.lock` / `onnx` | 1.23.1 | 2/2 | #287, #235 |
| `package/ai/uv.lock` / `pydantic-settings` | 2.15.0 | 1/1 | #227 |
| `package/ai/uv.lock` / `python-dotenv` | 1.2.4 | 1/1 | #103 |
| `package/ai/uv.lock` / `python-multipart` | 0.0.32 | 5/5 | #181, #180, #179, #178, #136 |
| `package/ai/uv.lock` / `requests` | 2.34.2 | 1/1 | #46 |
| `package/ai/uv.lock` / `setuptools` | 84.0.0 | 1/1 | #280 |
| `package/ai/uv.lock` / `transformers` | 5.18.0 | 5/5 | #406, #336, #237, #234, #81 |
| `package/ai/uv.lock` / `urllib3` | 2.8.0 | 3/3 | #405, #404, #403 |
| `package/desktop/src-tauri/Cargo.lock` / `glib` | 0.18.5 | 0/1 | #333 |
| `package/official-site/pnpm-lock.yaml` / `@xmldom/xmldom` | 0.9.12 | 13/13 | #372, #370, #368, #366, #364, #362, #360, #358, #356, #354, #352, #350, #345 |
| `package/official-site/pnpm-lock.yaml` / `baseline-browser-mapping` | 2.11.26 | 1/1 | #374 |
| `package/official-site/pnpm-lock.yaml` / `browserslist` | 4.29.3 | 1/1 | #338 |
| `package/official-site/pnpm-lock.yaml` / `dompurify` | 3.4.16 | 10/10 | #327, #281, #225, #208, #207, #206, #205, #204, #203, #187 |
| `package/official-site/pnpm-lock.yaml` / `esbuild` | 0.28.2 | 1/1 | #175 |
| `package/official-site/pnpm-lock.yaml` / `mermaid` | 10.9.8, 11.17.2 | 15/15 | #326, #325, #324, #323, #322, #321, #320, #319, #149, #148, #147, #146, #145, #144, #143 |
| `package/official-site/pnpm-lock.yaml` / `nanoid` | 3.3.19 | 3/3 | #340, #334, #329 |
| `package/official-site/pnpm-lock.yaml` / `postcss` | 8.5.28 | 2/2 | #310, #288 |
| `package/official-site/pnpm-lock.yaml` / `postcss-selector-parser` | 6.1.4 | 1/1 | #337 |
| `package/official-site/pnpm-lock.yaml` / `uuid` | 11.1.1 | 1/1 | #155 |
| `package/official-site/pnpm-lock.yaml` / `vite` | 7.3.6 | 2/2 | #202, #201 |
| `package/requirement-platform/server/uv.lock` / `PyJWT` | 2.15.1 | 9/9 | #419, #418, #416, #414, #413, #412, #411, #409, #407 |
| `package/requirement-platform/server/uv.lock` / `ecdsa` | 0.19.2 | 0/1 | #349 |
| `package/requirement-platform/server/uv.lock` / `pyJWT` | 2.15.1 | 1/1 | #415 |
| `package/requirement-platform/server/uv.lock` / `pyjwt` | 2.15.1 | 3/3 | #417, #410, #408 |
| `package/requirement-platform/web/package-lock.json` / `@vitest/mocker` | 4.1.11 | 1/1 | #375 |
| `package/requirement-platform/web/package-lock.json` / `brace-expansion` | 2.1.7 | 1/1 | #422 |
| `package/requirement-platform/web/package-lock.json` / `vitest` | 4.1.11 | 1/1 | #376 |
| `package/requirement-platform/web/pnpm-lock.yaml` / `@vitest/mocker` | 4.1.11 | 1/1 | #379 |
| `package/requirement-platform/web/pnpm-lock.yaml` / `brace-expansion` | 2.1.7 | 1/1 | #425 |
| `package/requirement-platform/web/pnpm-lock.yaml` / `vitest` | 4.1.11 | 1/1 | #380 |
| `package/server/uv.lock` / `PyJWT` | 2.15.1 | 9/9 | #441, #440, #435, #433, #432, #431, #430, #428, #426 |
| `package/server/uv.lock` / `Starlette` | 1.7.0 | 1/1 | #212 |
| `package/server/uv.lock` / `aiohttp` | 3.14.3 | 14/14 | #315, #314, #313, #196, #195, #194, #193, #192, #191, #190, #189, #188, #162, #161 |
| `package/server/uv.lock` / `anyio` | 4.14.2 | 2/2 | #384, #383 |
| `package/server/uv.lock` / `cryptography` | 50.0.2 | 6/6 | #386, #385, #316, #209, #82, #51 |
| `package/server/uv.lock` / `ecdsa` | 0.19.2 | 1/2 | #48, #39 |
| `package/server/uv.lock` / `langchain` | 1.3.9 | 1/1 | #214 |
| `package/server/uv.lock` / `langchain-openai` | 1.1.14 | 1/1 | #100 |
| `package/server/uv.lock` / `langgraph-checkpoint` | 4.2.0 | 1/1 | #230 |
| `package/server/uv.lock` / `langgraph-sdk` | 0.4.5 | 1/1 | #231 |
| `package/server/uv.lock` / `langsmith` | 0.14.2 | 3/3 | #228, #152, #95 |
| `package/server/uv.lock` / `pillow-heif` | 1.8.0 | 1/1 | #242 |
| `package/server/uv.lock` / `pyJWT` | 2.15.1 | 1/1 | #434 |
| `package/server/uv.lock` / `pyasn1` | 0.6.4 | 3/3 | #291, #283, #282 |
| `package/server/uv.lock` / `pydantic-settings` | 2.15.0 | 1/1 | #229 |
| `package/server/uv.lock` / `pyjwt` | 2.15.1 | 3/3 | #436, #429, #427 |
| `package/server/uv.lock` / `python-dotenv` | 1.2.4 | 1/1 | #102 |
| `package/server/uv.lock` / `python-multipart` | 0.0.32 | 4/4 | #185, #184, #183, #182 |
| `package/server/uv.lock` / `requests` | 2.34.2 | 1/1 | #45 |
| `package/server/uv.lock` / `starlette` | 1.7.0 | 4/4 | #213, #211, #210, #163 |
| `package/server/uv.lock` / `urllib3` | 2.8.0 | 3/3 | #439, #438, #437 |
| `package/trailsnap-cli/uv.lock` / `pytest` | 9.1.1 | 1/1 | #239 |
| `package/trailsnap-cli/uv.lock` / `requests` | 2.34.2 | 1/1 | #238 |
| `package/trailsnap-cli/uv.lock` / `urllib3` | 2.8.0 | 5/5 | #444, #443, #442, #241, #240 |
| `package/website/pnpm-lock.yaml` / `@xmldom/xmldom` | 0.9.12 | 10/10 | #371, #367, #365, #363, #361, #359, #357, #355, #351, #346 |
| `package/website/pnpm-lock.yaml` / `axios` | 1.20.0 | 12/12 | #466, #465, #464, #463, #462, #461, #460, #459, #458, #457, #456, #455 |
| `package/website/pnpm-lock.yaml` / `brace-expansion` | 1.1.21, 2.1.7, 5.0.12 | 4/4 | #454, #453, #452, #275 |
| `package/website/pnpm-lock.yaml` / `browserslist` | 4.29.3 | 1/1 | #342 |
| `package/website/pnpm-lock.yaml` / `dompurify` | 3.4.16 | 10/10 | #330, #285, #226, #223, #222, #221, #220, #219, #218, #186 |
| `package/website/pnpm-lock.yaml` / `echarts` | 6.1.0 | 1/1 | #233 |
| `package/website/pnpm-lock.yaml` / `glob` | 10.5.0, 13.0.6, 9.3.5 | 1/1 | #22 |
| `package/website/pnpm-lock.yaml` / `linkify-it` | 5.0.2 | 2/2 | #284, #232 |
| `package/website/pnpm-lock.yaml` / `lodash` | 4.18.1 | 3/3 | #76, #74, #23 |
| `package/website/pnpm-lock.yaml` / `lodash-es` | 4.18.1 | 3/3 | #77, #75, #24 |
| `package/website/pnpm-lock.yaml` / `markdown-it` | 14.3.2 | 2/2 | #445, #224 |
| `package/website/pnpm-lock.yaml` / `minimatch` | 10.2.6, 3.1.5, 8.0.7, 9.0.9 | 2/2 | #299, #38 |
| `package/website/pnpm-lock.yaml` / `nanoid` | 3.3.19 | 3/3 | #344, #335, #332 |
| `package/website/pnpm-lock.yaml` / `postcss` | 8.5.28 | 4/4 | #312, #289, #286, #112 |
| `package/website/pnpm-lock.yaml` / `postcss-selector-parser` | 6.1.4 | 1/1 | #341 |
| `package/website/pnpm-lock.yaml` / `sharp` | 0.35.5 | 2/2 | #377, #308 |
| `package/website/pnpm-lock.yaml` / `tar` | 7.5.22 | 8/8 | #307, #303, #301, #300, #296, #295, #294, #293 |
| `package/website/pnpm-lock.yaml` / `uuid` | 11.1.1 | 1/1 | #302 |
