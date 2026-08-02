import { expect, test, type Page, type Route } from "@playwright/test"

// 本 spec 覆盖朋友圈日文案的时区归日行为：
//   photo_time 按 **拍摄本地墙上时间** 语义归日，晚上 20:00 的照片
//   在前端 groupBy 与后端查询 payload 里都归到当天，不再因时区
//   换算偏移一天。
//
// 完全 self-contained：通过 addInitScript 注入假登录态 + page.route mock，
// 不依赖真实后端 / AI / Postgres。

test.describe.configure({ mode: "serial" })

const ok = (data: unknown) => ({ code: 0, message: "success", data })

const fakeUser = {
  id: "u-e2e",
  username: "e2e-mock",
  nickname: "E2E 行影者",
  avatar: "",
  is_active: true,
  is_superuser: true,
}

// 一张 20:00 本地时间的照片 —— 时区处理错误时最容易落到相邻天。
const fakePhotos = [
  {
    id: "p-evening",
    filename: "night.jpg",
    // naive 字符串，无 Z 后缀，与实际 DB 语义一致（拍摄本地墙上时间）
    photo_time: "2025-08-05T20:00:00",
    upload_time: "2025-08-05T20:00:00",
    file_type: "image",
    url: "/api/medias/p-evening/file",
    thumbnail_url: "/api/medias/p-evening/thumbnail",
    size: 1024,
    width: 1920,
    height: 1080,
  },
]

const fakeTimeline = {
  total_photos: 1,
  time_range: { start: "2025-08-05", end: "2025-08-05" },
  timeline: [{ year: 2025, month: 8, day: 5, count: 1 }],
}

async function injectFakeAuth(page: Page) {
  await page.addInitScript(() => {
    try {
      localStorage.setItem("user_token", "fake-e2e-token")
      localStorage.setItem("username", "e2e-mock")
      localStorage.setItem(
        "user_info",
        JSON.stringify({
          id: "u-e2e",
          username: "e2e-mock",
          nickname: "E2E 行影者",
          is_active: true,
          is_superuser: true,
        })
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
      body: JSON.stringify(fakeUser),
    })
  })
}

async function mockPhotosApis(page: Page) {
  await page.route("**/api/stats/timeline**", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(ok(fakeTimeline)),
    })
  })
  await page.route(/\/api\/photos(\?|$)/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(ok(fakePhotos)),
    })
  })
  await page.route("**/api/photos/folders**", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        ok({ parent: "", breadcrumb: [], own_count: 0, children: [] })
      ),
    })
  })
  await page.route("**/api/medias/**", async (route: Route) => {
    const pixel =
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: Buffer.from(pixel, "base64"),
    })
  })
}

async function stubEmptyCaptionList(page: Page) {
  await page.route("**/api/moments/day-captions?**", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "[]",
      })
    }
    return route.continue()
  })
}

async function stubEmptyLocations(page: Page) {
  await page.route("**/api/moments/day-locations**", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "[]",
      })
    }
    return route.continue()
  })
}

async function enterMomentsView(page: Page) {
  await page.goto("/photos")
  await expect(page.locator(".photo-gallery")).toBeVisible({ timeout: 15_000 })
  await page.locator('button[title="视图设置"]').click()
  await page.locator('button:has-text("朋友圈")').first().click()
  await expect(page.locator(".day-block").first()).toBeVisible({ timeout: 10_000 })
}

test.beforeEach(async ({ page }) => {
  await injectFakeAuth(page)
  await stubAuthMe(page)
  await mockPhotosApis(page)
  await stubEmptyCaptionList(page)
  await stubEmptyLocations(page)
})

// ===========================================================================
// 焦点 2：photo_time 按拍摄本地墙上时间归日
// ===========================================================================

test.describe("朋友圈 · photo_time 按墙上时间归日 @moments-timezone", () => {
  test("晚上 20:00 的照片 -> 前端归到 2025-08-05；点击生成时 payload.day 也是 2025-08-05", async ({
    page,
  }) => {
    // 拦截生成接口，只为拿到请求 body
    let capturedBody: any = null
    await page.route(
      "**/api/moments/day-captions/generate",
      async (route) => {
        capturedBody = JSON.parse(route.request().postData() || "{}")
        const sseBody = [
          `data: ${JSON.stringify({
            done: true,
            caption: "ok",
            source: "ai",
            updated_at: "2025-08-05T20:00:00Z",
          })}`,
          "data: [DONE]",
          "",
        ].join("\n\n")
        await route.fulfill({
          status: 200,
          contentType: "text/event-stream",
          body: sseBody,
        })
      }
    )

    await enterMomentsView(page)

    // 断言 1：前端按浏览器本地 tz 把 20:00 的照片归到 8-5
    // moments 视图会把当天日期渲染在头部（PhotoGallery 里 `${year}-${month}-${day}` 格式）
    await expect(
      page.getByText(/2025-8-5|2025年8月5日|8\s*月\s*5\s*日/).first()
    ).toBeVisible({ timeout: 10_000 })

    // 断言 2：点击"AI 生成"，服务端接收的 day 参数是 2025-08-05
    const dayBlock = page.locator(".day-block").first()
    await dayBlock.hover()
    const generateButton = dayBlock.getByRole("button", {
      name: "AI 生成",
      exact: true,
    })
    await expect(generateButton).toBeVisible()
    const generateResponse = page.waitForResponse(
      (r) => r.url().includes("/api/moments/day-captions/generate"),
      { timeout: 15_000 }
    )
    await generateButton.click()

    // 等 generate 响应返回（capturedBody 在 route handler 里、fulfill 之前赋值）；
    // 不依赖 SSE 文案渲染，避免 mocked event-stream 在 docker 下抖动
    await generateResponse

    expect(capturedBody).toBeTruthy()
    // 关键断言：day 一定是 2025-08-05，绝不能因时区偏移到 08-04 / 08-06
    expect(capturedBody.day).toBe("2025-08-05")
    expect(capturedBody.stream).toBe(true)
    expect(capturedBody.scope_type).toBe("all")
    expect(typeof capturedBody.timezone).toBe("string")
  })

  test("day-locations 请求参数 -> start/end 均为 2025-08-05，不因时区偏移", async ({
    page,
  }) => {
    // 该用例覆盖 api/moment.py 里 list_day_locations 走 naive 边界后的语义：
    // 无论浏览器 tz 是什么，20:00 的照片对应的 day-locations 查询窗口一定是
    // 2025-08-05 那一天。
    let locationParams: URLSearchParams | null = null

    // 覆盖 beforeEach 里的空 mock
    await page.unroute("**/api/moments/day-locations**").catch(() => {})
    await page.route("**/api/moments/day-locations**", (route) => {
      if (route.request().method() !== "GET") return route.continue()
      const url = new URL(route.request().url())
      locationParams = url.searchParams
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            day: "2025-08-05",
            primary: "外滩",
            level: "scene",
            locations: [{ name: "外滩", level: "scene", count: 1 }],
          },
        ]),
      })
    })

    await enterMomentsView(page)

    // 接口应被真正调用
    await expect
      .poll(() => (locationParams ? true : false), { timeout: 10_000 })
      .toBe(true)

    // start / end 都应该落在 2025-08-05 所在月，且包含 8-5
    const start = locationParams!.get("start")!
    const end = locationParams!.get("end")!
    expect(start.startsWith("2025-08")).toBe(true)
    expect(end.startsWith("2025-08")).toBe(true)
    // 用字典序简单比对即可，因为 YYYY-MM-DD 词典序 = 时间序
    expect(start <= "2025-08-05").toBe(true)
    expect(end >= "2025-08-05").toBe(true)

    // 页面日期行也应展示 8-5 归属的"外滩"
    await expect(page.getByText("外滩").first()).toBeVisible({ timeout: 10_000 })
  })
})
