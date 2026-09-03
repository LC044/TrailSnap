import { expect, test, type Page, type Route } from "@playwright/test"

// Self-contained suite: inject a fake auth token via addInitScript, then mock
// every /api/tokens + /api/system/* call with page.route. No real backend is
// required, so the suite works in any environment that can run `pnpm dev`.
// This mirrors the convention used by views-deeper-p3/p5/p7.

test.describe.configure({ mode: "serial" })

const ok = (data: unknown) => ({ code: 0, message: "success", data })

async function injectFakeAuth(page: Page) {
  await page.addInitScript(() => {
    try {
      localStorage.setItem("user_token", "fake-e2e-token")
      localStorage.setItem("username", "e2e-mock")
      localStorage.setItem(
        "user_info",
        JSON.stringify({ id: "u-e2e", username: "e2e-mock", is_active: true, is_superuser: true }),
      )
    } catch {
      /* ignore */
    }
  })
}

async function stubAuthMe(page: Page) {
  await page.route("**/api/auth/me**", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: "u-e2e", username: "e2e-mock", is_active: true, is_superuser: true }),
    })
  })
}

/** GET /api/system/version + GET /api/system/update-check 的最小桩 */
async function stubSystemApis(page: Page) {
  await page.route("**/api/system/version**", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(ok({ version: "0.0.0-e2e" })),
    })
  })
  await page.route("**/api/system/update-check**", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(ok({ has_update: false, latest_version: "0.0.0-e2e", download_url: null })),
    })
  })
}

async function clickSettingTab(page: Page, key: string) {
  const anchor = page.locator(`[data-tab="${key}"]`).first()
  await anchor.scrollIntoViewIfNeeded()
  await anchor.click()
}

test.beforeEach(async ({ page }) => {
  await injectFakeAuth(page)
  await stubAuthMe(page)
  await stubSystemApis(page)
})

test.describe("Tokens 令牌管理 @views-coverage", () => {
  test("列表渲染：脱敏、状态标签、复制按钮均可见", async ({ page }) => {
    const fixedNow = Date.now()
    const oneDay = 24 * 60 * 60 * 1000
    await page.route("**/api/tokens**", async (route: Route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(ok([
            {
              id: "t-active",
              user_id: "u-e2e",
              name: "Claude Code",
              token: "tsnap_active_abcdefghijklmnop",
              created_at: new Date(fixedNow - 7 * oneDay).toISOString(),
              expires_at: new Date(fixedNow + 30 * oneDay).toISOString(),
              is_deleted: false,
            },
            {
              id: "t-expired",
              user_id: "u-e2e",
              name: "OldToken",
              token: "tsnap_expired_xxxxxxxxxxxxxxx",
              created_at: new Date(fixedNow - 90 * oneDay).toISOString(),
              expires_at: new Date(fixedNow - 1 * oneDay).toISOString(),
              is_deleted: false,
            },
          ])),
        })
        return
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ok({})) })
    })

    await page.goto("/settings")
    await clickSettingTab(page, "tokens")
    await expect(page.locator("h1", { hasText: "令牌管理" })).toBeVisible({ timeout: 15_000 })

    // 两条记录都渲染；按 token 长度 > 10 走脱敏逻辑（前 4 + ...* + 后 4）
    const table = page.locator(".tokens-table")
    await expect(table.getByText("Claude Code")).toBeVisible()
    await expect(table.getByText("OldToken")).toBeVisible()
    await expect(table.locator(".el-tag", { hasText: "有效" })).toBeVisible()
    await expect(table.locator(".el-tag", { hasText: "已过期" })).toBeVisible()

    // 原值不应出现在 DOM（被 maskToken 替换成前 4 + 后 4 + 填充星号）
    await expect(page.locator("body")).not.toContainText("tsnap_active_abcdefghijklmnop")
  })

  test("空列表 -> 显示「暂无令牌」+ 创建按钮", async ({ page }) => {
    await page.route("**/api/tokens**", async (route: Route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ok([])) })
    })

    await page.goto("/settings")
    await clickSettingTab(page, "tokens")
    // 桌面表格 loading=false 后空数组：表格数据为空，desktop table view 仍可见。
    // 这里额外把窗口调成 mobile 宽度以覆盖 md:hidden 空态分支
    await page.setViewportSize({ width: 390, height: 844 })
    await page.reload()
    // 多级设置在窄屏刷新后会根据 #tokens 直接恢复令牌详情页，
    // 不再渲染旧版顶部 Tab，因此无需重复点击入口。
    await expect(page).toHaveURL(/\/settings#tokens$/)

    await expect(page.getByText("暂无令牌")).toBeVisible({ timeout: 15_000 })
    const createBtn = page.getByRole("button", { name: "创建第一个令牌" })
    await expect(createBtn).toBeVisible()
    await createBtn.click()
    await expect(page.locator(".el-dialog__title", { hasText: "新增令牌" })).toBeVisible({ timeout: 5_000 })
  })

  test("创建弹窗 -> POST /api/tokens -> 成功 toast + 重新拉取", async ({ page }) => {
    const getCalls: string[] = []
    const postBodies: unknown[] = []
    await page.route("**/api/tokens**", async (route: Route) => {
      const method = route.request().method()
      if (method === "GET") {
        getCalls.push(route.request().url())
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ok([])) })
        return
      }
      if (method === "POST") {
        try {
          postBodies.push(JSON.parse(route.request().postData() || "{}"))
        } catch {
          postBodies.push(null)
        }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(ok({
            id: "t-new",
            user_id: "u-e2e",
            name: "OpenClaw",
            token: "tsnap_new_abcdefghijklmnop",
            created_at: new Date().toISOString(),
            expires_at: new Date(Date.now() + 30 * 24 * 3600 * 1000).toISOString(),
            is_deleted: false,
          })),
        })
        return
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ok({})) })
    })

    await page.goto("/settings")
    await clickSettingTab(page, "tokens")
    await expect(page.locator("h1", { hasText: "令牌管理" })).toBeVisible({ timeout: 15_000 })
    // 初始 GET 至少一次
    await expect.poll(() => getCalls.length, { timeout: 5_000 }).toBeGreaterThan(0)

    await page.getByRole("button", { name: "新增令牌" }).first().click()
    await expect(page.locator(".el-dialog__title", { hasText: "新增令牌" })).toBeVisible({ timeout: 5_000 })

    // Element Plus form-item 的 label 渲染为 div；用 getByLabel 命中 input
    await page.getByLabel("令牌名称").fill("OpenClaw")
    await page.getByLabel("验证密码").fill("hunter2")

    // el-date-picker 直接写 ISO 字符串不生效，这里通过 el-date-picker 的 input
    // 写入一个可被 Date 解析的本地时间并触发 change
    const dateInput = page.locator('.el-dialog input[placeholder="选择过期时间"]').first()
    await dateInput.fill("2099-12-31 23:59:59")
    await dateInput.press("Enter")

    await page.locator(".el-dialog").getByRole("button", { name: "确定" }).click()

    await expect.poll(() => postBodies.length, { timeout: 5_000 }).toBeGreaterThan(0)
    const body = postBodies[0] as Record<string, unknown>
    expect(body).toMatchObject({ name: "OpenClaw", password: "hunter2" })
    expect(typeof body.expires_at).toBe("string")
    // 成功 toast
    await expect(page.locator(".el-message", { hasText: "令牌创建成功" })).toBeVisible({ timeout: 5_000 })
    // 弹窗关闭
    await expect(page.locator(".el-dialog__title", { hasText: "新增令牌" })).not.toBeVisible({ timeout: 5_000 })
    // 创建成功后应再次拉取列表（getCalls 增长）
    await expect.poll(() => getCalls.length, { timeout: 5_000 }).toBeGreaterThan(1)
  })

  test("popconfirm 删除 -> DELETE /api/tokens/:id -> 成功 toast", async ({ page }) => {
    const getCalls: string[] = []
    const deleteCalls: string[] = []
    await page.route("**/api/tokens**", async (route: Route) => {
      const method = route.request().method()
      const url = route.request().url()
      if (method === "GET") {
        getCalls.push(url)
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(ok([
            {
              id: "t-del-1",
              user_id: "u-e2e",
              name: "Removable",
              token: "tsnap_del_abcdefghijklmnop",
              created_at: new Date().toISOString(),
              expires_at: new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString(),
              is_deleted: false,
            },
          ])),
        })
        return
      }
      if (method === "DELETE") {
        deleteCalls.push(url)
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ok({})) })
        return
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ok({})) })
    })

    await page.goto("/settings")
    await clickSettingTab(page, "tokens")
    await expect(page.locator("h1", { hasText: "令牌管理" })).toBeVisible({ timeout: 15_000 })
    await expect(page.locator(".tokens-table").getByText("Removable")).toBeVisible({ timeout: 5_000 })

    // 点击桌面表格行内的删除按钮（type=danger, lucide-trash-2 图标）；触发 el-popconfirm popper
    const deleteBtn = page.locator(".tokens-table .el-button--danger").first()
    await expect(deleteBtn).toBeVisible({ timeout: 5_000 })
    await deleteBtn.click()
    // 等待 popper 中可见的 popconfirm 出现（el-popconfirm__action 内的 primary 按钮）
    const confirmBtn = page.locator(".el-popconfirm__action button.el-button--primary:visible").first()
    await expect(confirmBtn).toBeVisible({ timeout: 5_000 })
    await confirmBtn.click()
    await expect.poll(() => deleteCalls.length, { timeout: 5_000 }).toBeGreaterThan(0)
    expect(deleteCalls[0]).toContain('/api/tokens/t-del-1')
    await expect(page.locator(".el-message", { hasText: "令牌已删除" })).toBeVisible({ timeout: 5_000 })
    // 删除后刷新列表（getCalls 计数增长）
    await expect.poll(() => getCalls.length, { timeout: 5_000 }).toBeGreaterThan(1)
  })
})

test.describe("NotFound 404 路由 @views-coverage", () => {
  test("访问未定义路由 -> 渲染 404 页面并提示「页面未找到」", async ({ page }) => {
    await page.goto("/this-route-does-not-exist-xyz")
    await expect(page.locator("h1", { hasText: "404" })).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText("页面未找到")).toBeVisible()
  })

  test("从 404 点击「返回首页」-> 跳到 /", async ({ page }) => {
    await page.goto("/totally-unknown")
    await expect(page.locator("h1", { hasText: "404" })).toBeVisible({ timeout: 10_000 })
    await page.getByRole("link", { name: "返回首页" }).click()
    await expect(page).toHaveURL(/\/$/)
  })
})

test.describe("FeedbackPage 问题反馈 + AboutPage 检查更新 @views-coverage", () => {
  test("FeedbackPage 渲染 3 个 GitHub Issues 链接，href 指向 LC044/TrailSnap", async ({ page }) => {
    await page.goto("/settings")
    await clickSettingTab(page, "feedback")
    await expect(page.locator("h2", { hasText: "问题反馈" })).toBeVisible({ timeout: 10_000 })

    const bugLink = page.locator('a[href*="bug_report.yml"]').first()
    const featureLink = page.locator('a[href*="feature_request.yml"]').first()
    const issuesLink = page.locator('a[href*="/issues"]').first()

    await expect(bugLink).toBeVisible()
    await expect(featureLink).toBeVisible()
    await expect(issuesLink).toBeVisible()

    for (const a of [bugLink, featureLink, issuesLink]) {
      const href = await a.getAttribute("href")
      expect(href).toMatch(/^https:\/\/github\.com\/LC044\/TrailSnap\//)
      const target = await a.getAttribute("target")
      expect(target).toBe("_blank")
    }
  })

  test("AboutPage 检查更新 -> GET /api/system/update-check -> 显示「已是最新」", async ({ page }) => {
    let updateCheckCalled = false
    await page.unroute("**/api/system/update-check**").catch(() => {})
    await page.route("**/api/system/update-check**", async (route: Route) => {
      updateCheckCalled = true
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(ok({ has_update: false, latest_version: "0.0.0-e2e", download_url: null })),
      })
    })

    await page.goto("/settings")
    await clickSettingTab(page, "about")
    await expect(page.locator("h1", { hasText: "关于行影集" })).toBeVisible({ timeout: 10_000 })

    const checkBtn = page.getByRole("button", { name: "检查更新" }).first()
    await expect(checkBtn).toBeVisible()
    await checkBtn.click()

    await expect.poll(() => updateCheckCalled, { timeout: 5_000 }).toBeTruthy()
    await expect(page.locator(".el-message", { hasText: "当前已是最新版本" }).first()).toBeVisible({ timeout: 5_000 })
  })

  test("AboutPage 检查更新发现新版本 -> 显示升级提示", async ({ page }) => {
    // AboutPage onMounted 会自动调用 checkUpdate()；用 mutable state 控制响应：
    // 首次（mount）返回 has_update=false 只弹 toast，二次（按钮点击）返回 has_update=true 弹 ElMessageBox。
    let callCount = 0
    await page.unroute("**/api/system/update-check**").catch(() => {})
    await page.route("**/api/system/update-check**", async (route: Route) => {
      callCount += 1
      const hasUpdate = callCount >= 2
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(ok({ has_update: hasUpdate, latest_version: "9.9.9", download_url: "https://example.com/release.zip" })),
      })
    })

    await page.goto("/settings")
    await clickSettingTab(page, "about")
    await expect(page.locator("h1", { hasText: "关于行影集" })).toBeVisible({ timeout: 10_000 })

    // mount 触发的 checkUpdate() 返回 has_update=false，只弹 toast，无 message box 拦截
    await page.getByRole("button", { name: "检查更新" }).first().click()
    const msgBox = page.locator(".el-message-box").first()
    await expect(msgBox).toBeVisible({ timeout: 5_000 })
    await expect(msgBox).toContainText("9.9.9")
    await msgBox.getByRole("button", { name: "暂不更新" }).click()
  })
})
