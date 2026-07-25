# TrailSnap 测试指南

面向开发者的测试入门与约定。读完这一篇就能：跑现有测试、看懂测试分层、按规范加新用例、避开已知的坑。

---

## 1. 总览

四类测试，一个入口脚本，一份环境变量文件。

| 层 | 位置 | 框架 | 触发 | 速度 |
|---|---|---|---|---|
| 后端单元 | `package/server/tests/unit` | pytest | `run-tests.ps1 -Layer unit` | 秒级，无外部服务 |
| 后端集成 | `package/server/tests` | pytest | `run-tests.ps1 -Layer integration` | 需 DB |
| AI 服务 | `package/ai/tests` | pytest | `run-tests.ps1 -Layer unit -Component ai` | 部分需模型/显存 |
| 前端 E2E | `package/website/tests/e2e`、`package/website/e2e-system` | Playwright | `run-tests.ps1 -Layer e2e` | 慢，需 server+ai+web 全起 |

**统一入口**：`tests/scripts/run-tests.ps1`（CI 与本地共用）。它按 `.env` 文件委托 `services-up.ps1` 拉起服务（dev 本地进程 或 docker compose 栈）、注入环境变量、调度对应测试运行器（uv/pytest、pnpm/playwright），测后委托 `services-down.ps1` 关闭服务。

**单一数据源**：`tests/.env.test`（默认）或你传入的 `.env` 文件。改这一份，docker / 前端 e2e / 后端 / AI 四方共享。子进程（uv、pnpm、docker）全部继承。

### 脚本结构（`tests/scripts/`）

```
run-tests.ps1            ← 唯一入口（CI + 本地都用它）
  ├─ services-up.ps1        启动服务（dev 本地进程 / docker compose）+ AI 模型预热
  ├─ services-down.ps1      关闭服务 + 收集 docker 日志
  ├─ test-services-lib.ps1  共享函数库（端口探测 / 进程树清理 / uv 解析 / DB 删除 / AI 预热）
  └─ Import-EnvFile.ps1     .env 文件加载器（注入 $env:，子进程继承）
```

`run-tests.ps1` 在 e2e/integration 层的 `try` 块里调 `services-up` → 跑测试 → `finally` 调 `services-down`（`TS_TEST_KEEP_SERVICES=true` 时跳过）。unit 层不需要服务，直接跑 pytest。`-StopServices` 直接委托 `services-down`，不启动/不测。

### dev 模式 vs docker 模式（`-Mode`）

| 模式 | 服务载体 | 适用场景 | 速度 |
|---|---|---|---|
| `dev`（本地默认） | 本地进程：`uv run python start.py`（server）/ `uv run uvicorn main:app`（AI）/ `pnpm dev`（前端） | 日常迭代，改代码可热重载 | 启动快 |
| `docker` | `docker compose` 起 `tests/docker/docker-compose.yml`（postgres + server + ai + frontend） | 复现 CI、验证发布镜像、干净隔离环境 | 启动慢但可复现 |

两种模式都走同一个 `run-tests.ps1`，只是 `-Mode` 不同。CI 的 e2e job 用 `run-tests.ps1 -Layer e2e -Level <level> -Mode docker`，和本地 `-Mode docker` 完全同路径——本地过了 CI 就过。`-Mode` 不传时按 `TS_TEST_ENV` 推断：`docker`/`ci` → docker，否则 dev。

---

## 2. 环境变量（`tests/.env.test`）

最关键的几个开关：

| 变量 | 作用 | 默认 |
|---|---|---|
| `TS_TEST_ENV` | `dev`（本地手起服务）/ `docker` / `ci`；决定 `-Mode` 默认值 | dev |
| `TS_API_BASE_URL` / `TS_WEB_BASE_URL` / `TS_AI_API_URL` / `TS_DB_URL` | 各服务端点 | dev: 8000/5176/8001/5532 |
| `TS_E2E_SUITE` | e2e 套件=`-Level` 默认值：`dev`/`p0`/`p1`/`smoke`/`scan`/`all`/`light`/`full` | dev |
| `TS_TEST_SCOPE` | `all` / `photo` / `album` / ... 业务域过滤（unit/integration） | all |
| `TS_TEST_RESET_DB` | `true` 时启动 server 前 DROP 目标库 → 全新数据 | false |
| `TS_TEST_KEEP_SERVICES` | `true` 时测后保留服务与数据，方便查看现场 | false |
| `TS_E2E_ENABLE_FIXTURE_SCAN` | e2e 前是否自动添加照片目录 + 触发扫描 | false |
| `TS_TEST_PHOTOS_REPO` | 测试照片所在的独立 LFS 仓库 URL | `LC044/trailsnap-test-photos` |
| `TS_PHOTO_HOST_DIR` / `TS_PHOTO_DIR` | 测试照片源目录（host）/ server 视角路径 | — |
| `TS_TEST_USERNAME` / `TS_TEST_PASSWORD` | e2e 登录账号（本地 dev 通常就是首个超级用户） | e2e-admin / Passw0rd!123 |

> 本地开发建议复制一份 `tests/.env.test-local`，把账号/端口指向自己的环境，用第一个位置参数传入：`.\tests\scripts\run-tests.ps1 .\tests\.env.test-local -Layer e2e`。

---

## 3. 快速开始

```powershell
# 最简：后端 + AI 的 smoke 单元测试（默认 env 文件）
.\tests\scripts\run-tests.ps1

# 前端 e2e 全量（用自己的 env 文件）
.\tests\scripts\run-tests.ps1 .\tests\.env.test-local -Layer e2e -Level full

# 先 scan 预扫描再跑 e2e
.\tests\scripts\run-tests.ps1 -Layer e2e -ScanPrep true

# 后端 album 域 smoke 单元
.\tests\scripts\run-tests.ps1 -Layer unit -Component server -Level smoke -Scope album

# 起 docker compose 栈跑 p0（与 CI 同路径）
.\tests\scripts\run-tests.ps1 -Layer e2e -Level p0 -Mode docker

# 只起 docker 测试栈不跑测试
.\tests\scripts\services-up.ps1 -Mode docker

# 按端口清理所有服务（含孤儿子进程）
.\tests\scripts\run-tests.ps1 -StopServices
```

### `run-tests.ps1` 参数

| 参数 | 取值 | 说明 |
|---|---|---|
| `EnvFile`（位置参数） | 路径 | 默认 `tests\.env.test` |
| `-Layer` | unit/integration/e2e/all | 测哪一层 |
| `-Level` | dev/scan/smoke/p0/p1/all/light/full | 深度/套件；默认读 `TS_E2E_SUITE` |
| `-Component` | server/ai/website/cli/all | 测哪个组件 |
| `-Mode` | dev/docker | 服务载体；默认按 `TS_TEST_ENV` |
| `-Scope` | all/photo/album/... | 业务域（unit/integration） |
| `-ScanPrep` | auto/true/false | e2e 是否先 scan；覆盖 `.env` |
| `-Cleanup` | switch | 测后删库 |
| `-StopServices` | switch | 只关服务，不启动/不测 |

---

## 4. 后端测试（pytest）

### 目录与 marker

- 用例：`package/server/tests/unit/`（纯函数/契约，无外部服务）、`package/server/tests/`（集成，需 DB）。
- marker 体系（`pyproject.toml`）：覆盖度 `smoke`/`regression`/`slow` × 资源 `postgres`/`model` × 模块 `module_photo`/`module_album`/...。
- `run-tests.ps1` 把 `-Level`/`-Scope` 组合成 `-m` 表达式：`smoke + album` → `-m "smoke and module_album"`；非 `smoke` → 不加 cover marker（可叠加 `-Scope`）；`-Level full`/`all` → 跑全部。
- `slow`/`postgres`/`model` 默认跳过（需显式 `-m` 才跑）。

### 单独跑

```powershell
cd package\server
uv run python -m pytest tests/test_api_integration.py -v
uv run python -m pytest -m "smoke and module_album" -v
```

### 加新用例

1. 放到对应目录：纯函数→`tests/unit/`，需 DB→`tests/`。
2. 文件名 `test_*.py`，函数 `test_*`。
3. 打 marker：`@pytest.mark.smoke`、`@pytest.mark.module_album`。
4. **响应断言**：所有后端 API 返回 `BaseResponse`（`{code, msg, data}`），断言 `body["code"] == 0` 并校验 `data`，不要直接断言 HTTP body 顶层字段。
5. 需真实 pgvector 的打 `@pytest.mark.postgres`；需 AI 模型的打 `@pytest.mark.model`。

---

## 5. AI 服务测试（pytest）

- 用例：`package/ai/tests/`，`conftest.py` 同样加载 `tests/.env.test`。
- 需模型/显存的打 `@pytest.mark.model`，默认跳过。
- 跑：`.\tests\scripts\run-tests.ps1 -Layer unit -Component ai`。

---

## 6. 前端 E2E 测试（Playwright）

### 套件体系

`TS_E2E_SUITE`（=`-Level`）决定 testDir / testMatch / globalSetup / 登录方式：

| 套件 | 用途 | 登录 | 典型命令 |
|---|---|---|---|
| `dev` | 日常开发，全量 spec | globalSetup 登录一次落盘 | `run-tests.ps1 -Layer e2e -Level dev` |
| `p0` | 核心路径功能（`@p0`） | bootstrap 注册+登录 | `run-tests.ps1 -Layer e2e -Level p0` |
| `p1` | 业务深测（`P1 - `） | 同 p0 | `run-tests.ps1 -Layer e2e -Level p1` |
| `smoke` | 页面打开+系统冒烟（`@smoke`） | 同 p0 | `run-tests.ps1 -Layer e2e -Level smoke` |
| `scan` | 仅扫描准备，不跑断言 | — | `run-tests.ps1 -Layer e2e -Level scan` |
| `light`/`full` | 不走 globalSetup 的轻量/全量 | 每 spec 自登录 | `run-tests.ps1 -Layer e2e -Level full` |

> 不传 `-Level` 时读 `TS_E2E_SUITE`（`.env.test` 默认 `dev`）。`run-tests.ps1` 统一委托 `node playwright/run-e2e.mjs <level>`，不再有 `-Cover full` 实际跑 `pnpm test:e2e` 的歧义。

### 标签约定（写进 `test.describe` 标题）

- `@smoke` — 页面能否打开、静态骨架可见。不校验数据/交互。
- `@p0` — 功能是否可用、API 是否返回正确数据。
- `P1 - ` — 业务深测。
- `@setup` / `@teardown` — `00-setup` / `99-teardown`。

### 目录结构

```
package/website/
├─ playwright.config.ts          # 读 e2eEnv 配置
├─ playwright/
│  ├─ e2e-env.ts                 # 所有 e2e 环境变量与套件映射（单一来源）
│  ├─ run-e2e.mjs                # 跨平台 e2e 运行器（system/smoke/p0/... 套件）
│  └─ global-teardown.ts         # dev 等套件的 globalTeardown：清理照片目录
├─ tests/e2e/
│  ├─ helpers/
│  │  ├─ auth.ts                 # ensureAuthSession / ensureApiAccessToken
│  │  ├─ photo-fixtures.ts       # preparePhotoFixtures / cleanupPreparedPhotoFixtures
│  │  ├─ dev-global-setup.ts     # dev 套件 globalSetup：登录+落盘 storageState
│  │  └─ data-probe.ts
│  └─ specs/                     # 按业务域分目录的 spec
└─ e2e-system/                   # system 套件专用（bootstrap/scan-prep/api/ui）
   └─ helpers/                   # bootstrap.ts / scan-global-setup.ts / task-poller.ts
```

### 一次 e2e run 的时序

```
run-tests.ps1 -Layer e2e -Level <level> -Mode <dev|docker>
   │
   ├─ services-up.ps1
   │    dev    : 清理占用端口 → start.py / uvicorn / pnpm dev（端口幂等）→ 等 ready → AI 模型预热
   │    docker : docker compose up -d → 等 server health → AI 模型预热（轮询 /embedding/text 到 200）
   ├─ run-e2e.mjs <level>           # 设 TS_E2E_SUITE=<level>，注入 TS_E2E_PREP_RUN_ID（RESET_DB 时唯一）
   │    ├─ globalSetup (dev-global-setup.ts)            # dev 套件：登录+落盘 storageState
   │    │    登录 testUsername → preparePhotoFixturesForSuite(smoke+p0)
   │    ├─ 所有 spec（worker 进程，复用 storageState）
   │    │    00-setup.spec.ts → ...业务 spec... → 99-teardown.spec.ts
   │    └─ globalTeardown (global-teardown.ts)
   │         KEEP_SERVICES=true → 直接返回；否则 cleanupPreparedPhotoFixtures
   └─ services-down.ps1           # finally 块，KEEP_SERVICES=true 时跳过
        dev    : taskkill /F /T 进程树 + 端口兜底清扫
        docker : docker compose logs → tests/artifacts/ → down -v
```

`full` 套件内部 `run-e2e.mjs` 会再调 `startServices()`/`stopServices()`（`service-manager.mjs`）；`services-up` 已预起栈，`startServices` 检测到端口在用 → 复用、不重复起，`stopServices` no-op，真正的 `down` 由 `services-down` 负责。

### 测试照片来源（独立 LFS 仓库）

照片夹具**不进主 repo**,而是从独立仓库 [LC044/trailsnap-test-photos](https://github.com/LC044/trailsnap-test-photos)（Git LFS）拉取。结构：

```
trailsnap-test-photos/
└── fixtures/
    ├── smoke/   ← smoke 套件 photoBucket
    └── p0/      ← p0/p1 套件 photoBucket
```

本地首次跑 e2e 前先同步（需要本机装 `git-lfs`）：

```bash
./tests/scripts/sync-test-photos.sh           # Linux / macOS
# 或
.\tests\scripts\sync-test-photos.ps1        # Windows
```

环境变量 `TS_TEST_PHOTOS_REPO` 可覆盖默认仓库（用于 fork / 内网部署）。CI 上由 `.github/workflows/tests.yml` 的 `actions/checkout@v4` 自动拉 LFS 对象，无需手动同步。

### 照片夹具（`photo-fixtures.ts`）

`TS_E2E_ENABLE_FIXTURE_SCAN=true` 时，`preparePhotoFixtures` 会：
1. 把 `smoke`/`p0` 子目录加到用户 external 目录（`POST /settings/directories`）；
2. 等后端自动触发的 `SCAN_FOLDER` 跑完（**不再额外建第二个扫描任务**，避免并发重复入库）；
3. 等照片真的出现在 `/photos`；
4. 把「已就绪」状态落盘到 `.playwright-{dev,system}/photo-fixtures/<fingerprint>.json`，同轮内复用、避免重复扫描。

清理由 `cleanupPreparedPhotoFixtures` 做：`DELETE /settings/directories`（后端会连带删除该目录下的 Photo）。

### 登录态（`auth.ts`）

- system/dev 套件：globalSetup 已登录，`storageState` 注入到每个 page；`ensureApiAccessToken` 读出 token 供 `request` fixture 直连后端时手动带 `Authorization`。
- 兜底：storageState 为空时逐测试登录，通过 `addInitScript` 在 SPA 启动前注入 token（**不能** goto 后再写 localStorage——`userStore` 启动时只读一次 token）。

### 加新 e2e 用例

1. **选目录**：按业务域放 `tests/e2e/specs/<domain>/`，文件名 `*.spec.ts`。
2. **打标签**：`test.describe('xxx @smoke', ...)` 或 `@p0` / `P1 - `。
3. **登录态**：需要登录的页面，第一个 `test` 里 `const token = await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }); if (!token) return;`。需要照片的传 `photoBucket`。
4. **API 调用**（见下方「避坑」）：
   - 用 `request` fixture（baseURL=前端）→ 路径必须带 `/api` 前缀。
   - 用 `page.request`（同前端）→ 同样带 `/api`。
   - 用 `e2eEnv.apiBaseUrl` 全量地址 → 不带 `/api`（直连后端）。
5. **断言**：后端返回 `BaseResponse`，`expect(body.code).toBe(0)` 后再校验 `body.data`。
6. **账号**：用 `e2eEnv.testUsername` / `testPassword`，不要用 `e2eEnv.adminUser`（默认 `e2e-admin`，既有库常不存在）。
7. **SPA 别用 `networkidle`**：用 `domcontentloaded` + 等具体元素。

---

## 7. 关键约定与避坑（重要）

### 7.1 `request` fixture 的 `/api` 前缀

`request` fixture 的 baseURL 是**前端**（`e2eEnv.webBaseUrl`）。Vite 把 `/api/*` 代理到后端并 rewrite 掉 `/api`（`vite.config.js`）。所以：
- `request.get('/api/auth/status')` ✅ → 后端 `/auth/status`
- `request.get('/auth/status')` ❌ → Vite 回吐 `index.html` → `res.json()` 解析失败

`e2e-system/` 下的 helper 用 `baseURL: e2eEnv.apiBaseUrl`（后端直连），相对路径不带 `/api` 是对的——别混淆。

### 7.2 账号统一用 `testUsername`

`dev-global-setup` 实际登录/注册的是 `e2eEnv.testUsername`（本地 dev 通常是你自己的首个超级用户）。`e2eEnv.adminUser` 默认 `e2e-admin`，既有库里通常不存在 → 登录 401。所有 spec 的登录/注册都用 `testUsername`/`testPassword`。

### 7.3 `TS_TEST_KEEP_SERVICES=true` 的清理守卫

「测后保留数据查看现场」由**两条独立路径**实现，**都要**看 `keepServices`：
- `99-teardown.spec.ts`：`test.skip(e2eEnv.keepServices, ...)`。
- `playwright/global-teardown.ts`：顶部 `if (e2eEnv.keepServices) return`。

漏掉任一条都会清数据。`globalTeardown` 是框架级、可靠执行；`99-teardown` 是 `99-` 前缀约定排最后的普通 test。两者都调 `cleanupPreparedPhotoFixtures`，后者还会删账号 + storageState。

> ⚠️ `99-teardown` 在 `KEEP_SERVICES=false` 时会删除 `testUsername` 账号。本地 dev 指向真实账号（如 `zhousk`）时危险——保持 `KEEP_SERVICES=true`，或把删账号逻辑改成仅 `e2e-` 前缀账号才删。

### 7.4 `TS_TEST_RESET_DB=true` 的夹具缓存

`photo-fixtures` 把「已就绪」状态落盘，跨轮复用。但 `RESET_DB=true` 每轮清空库，缓存会变陈旧（上轮 `ok:true` → 本轮跳过扫描 → 空库无照片）。`run-tests.ps1` 在 `RESET_DB=true` 时给本轮注入唯一 `TS_E2E_PREP_RUN_ID`，让指纹失效、强制重扫；同轮内 globalSetup 与 00-setup 共享该 id，仍去重避免重复扫描。

### 7.5 双重扫描 → 照片翻倍

`POST /settings/directories` 添加目录时会**自动触发**一次 `SCAN_FOLDER`（扫所有 external 目录）。夹具只等这次扫描，**不要**再 `triggerScanAndWait` 建第二个任务——两个 scope 重叠的扫描会被 IO consumer 并发执行，而扫描去重仅靠查库内 `file_path`（无唯一约束），并发时双方都查到「不存在」→ 同一文件各插一条 Photo → 相册翻倍。

### 7.6 SPA 不要用 `networkidle`

首页有 SSE / 轮询 / 图表动画等持续网络活动，`waitUntil: 'networkidle'` 永不满足 → 超时。用 `domcontentloaded` + 等具体元素。同理 `waitForLoadState('networkidle')` 也别用（或 `.catch(() => {})` 兜底）。

### 7.7 `ElMessage` toast 堆叠 → strict mode 违规

`ElMessage` 默认 3s 自动消失，连续操作时多条共存 → `locator('.el-message', { hasText })` 命中多条报错。处理：`.last()` 锁最新一条做断言，再 `toHaveCount(0)` 等它消失再返回，保证下一次操作画面干净。

### 7.8 ESM 文件别用 `require`

e2e 文件是 ESM（`import fs from 'node:fs'`），`require('path')` 会抛 `ReferenceError`。统一 `import xxx from 'node:xxx'`。

### 7.9 `el-switch` 的 `aria-checked`

Element Plus 的 `aria-checked` 在内部 `<input role="switch">` 上（不是 `.el-switch` 容器）。读状态用 `sw.locator('input').getAttribute('aria-checked')`，驱动用 `sw.click()` 后 `toHaveAttribute('aria-checked', ...)`。

---

## 8. 测试流程速查

```
改代码
  ↓
unit（秒级，必跑）           .\run-tests.ps1 -Layer unit
  ↓
integration（需 DB）          .\run-tests.ps1 -Layer integration
  ↓
e2e smoke（页面能打开）       .\run-tests.ps1 -Layer e2e -Level smoke
  ↓
e2e full（全量功能）          .\run-tests.ps1 -Layer e2e -Level full
  ↓
提 PR（CONTRIBUTING.md 流程，CLA 必填）
```

调试单文件：

```powershell
cd package\website
pnpm test:e2e --grep "@login"              # 按 grep 跑
pnpm test:e2e:ui                            # Playwright UI 模式
pnpm test:e2e:headed                       # 可见浏览器
```

---

## 9. CI（GitHub Actions）

`.github/workflows/tests.yml` 是 CI 与本地的**同一套脚本**，没有第二条路径。

| Job | 命令 | 说明 |
|---|---|---|
| CLI unit | `uv run pytest tests/ --ignore=tests/integration` | 纯单元，不起服务 |
| Server unit | `uv run python -m pytest tests/unit` | `python -m` 把 cwd 加进 sys.path，使 `from app...` 可导入 |
| AI unit | `uv run python -m pytest tests/` | router 测试 mock 模型，不下载权重 |
| Server integration | service container pgvector(55432) + uvicorn(58000) + `pytest tests/integration` | HTTP 级集成 |
| E2E | `run-tests.ps1 -Layer e2e -Level <level> -Mode docker` | 本地 `-Mode docker` 同路径 |

**E2E level 选择**：PR / push master → `p0`；nightly cron → `full`；手动 dispatch → 可选。同一 PR 多次推送用 `concurrency` 取消旧 run；nightly 与 push 落在不同 group，互不打断。

**AI 模型权重缓存**：e2e 栈的 ai 容器把 `tests/.cache/ai-models` bind-mount 进去；CI 用 `actions/cache`（key `ai-models-v1`）跨 run 持久化。首次 run 下载数百 MB（modelscope），后续秒级恢复。`services-up` 的 AI 预热轮询 `POST /embedding/text` 到 200 确认模型就绪。

**镜像来源**：server/frontend 用本地 `docker build :ci`（测当前代码）；ai 直接 `docker pull siyuan044/trailsnap-ai:master`（由 `构建ai` 关键字推送，省掉 insightface/torch 重编译）。改了 `package/ai/` 后记得先走一次带 `构建ai` 的提交再跑 e2e，避免 ai 镜像版本漂移。
