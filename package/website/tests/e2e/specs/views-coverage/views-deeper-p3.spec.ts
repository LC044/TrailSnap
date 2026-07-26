import { expect, test, type Page, type Route } from "@playwright/test"

// Specs are self-contained: inject a fake auth token via addInitScript, then mock
// every /api/locations/* and /api/location-stats/* call with page.route. No real
// backend or AI service is required, so the suite works in any environment that
// can run `pnpm dev`.

test.describe.configure({ mode: "serial" })

const ok = (data: unknown) => ({ code: 0, message: "success", data })

// 必须命中 OverviewStats 真实形状，has_location=true 才能避免空状态。
const fakeOverview = {
  total_distance_km: 12345.6,
  province_count: 3,
  city_count: 8,
  scene_count: 12,
  travel_days: 42,
  farthest_place: "三亚",
  farthest_distance_km: 2780,
  has_location: true,
}

const fakeAnnualTrend = [
  { year: 2024, photo_count: 100, distance_km: 1000 },
  { year: 2025, photo_count: 220, distance_km: 2400 },
]

// 必须使用 activity_score 而不是 score；maxScore 必须 > 0 才渲染月份按钮。
const fakeMonthlyRadar = Array.from({ length: 12 }, (_, i) => ({
  month: i + 1,
  photo_count: 10 + i,
  activity_score: i + 1,
}))

const fakeTopPlaces = [
  { name: "上海", level: "city", photo_count: 100, first_date: "2024-01-01", last_date: "2025-12-31", visit_count: 3, visit_dates: ["2024-01-01", "2024-08-01", "2025-08-01"] },
  { name: "北京", level: "city", photo_count: 80, first_date: "2024-03-01", last_date: "2025-11-30", visit_count: 2, visit_dates: ["2024-03-01", "2025-11-30"] },
]

const fakeRevisits = [
  { name: "上海", level: "city", photo_count: 100, first_date: "2024-01-01", last_date: "2025-08-01", visit_count: 3, visit_dates: ["2024-01-01", "2024-08-01", "2025-08-01"] },
]

const fakeHeatmap = {
  total_photos: 200,
  total_days: 6,
  data: [
    { date: "2025-01-01", count: 5 },
    { date: "2025-01-15", count: 10 },
    { date: "2025-02-02", count: 3 },
  ],
}

async function injectFakeAuth(page: Page) {
  await page.addInitScript(() => {
    try {
      localStorage.setItem("user_token", "fake-e2e-token")
      localStorage.setItem("username", "e2e-mock")
      localStorage.setItem("user_info", JSON.stringify({ id: "u-e2e", username: "e2e-mock", is_active: true, is_superuser: true }))
      // 直接把 viewMode 持久化到 statistics，避免默认 grid 时需要点击切换且减少 DOM race
      localStorage.setItem("trailsnap-location-view-mode", "statistics")
      localStorage.setItem("trailsnap-location-level", "city")
    } catch { /* ignore */ }
  })
}

async function stubAuthMe(page: Page) {
  await page.route("**/api/auth/me**", async (route: Route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ id: "u-e2e", username: "e2e-mock", is_active: true, is_superuser: true }) })
  })
}

async function mockLocationStatsApis(page: Page) {
  await page.route("**/api/location-stats/overview**", async (route: Route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ok(fakeOverview)) })
  })
  await page.route("**/api/location-stats/annual-trend**", async (route: Route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ok(fakeAnnualTrend)) })
  })
  await page.route("**/api/location-stats/monthly-radar**", async (route: Route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ok(fakeMonthlyRadar)) })
  })
  await page.route("**/api/location-stats/places**", async (route: Route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ok({ top_places: fakeTopPlaces, revisits: fakeRevisits })) })
  })
  await page.route("**/api/location-stats/heatmap**", async (route: Route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ok(fakeHeatmap)) })
  })
}

async function stubLocationCatalog(page: Page) {
  await page.route("**/api/locations**", async (route: Route) => {
    const url = route.request().url()
    if (url.includes("/years")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ok([2024, 2025])) })
      return
    }
    if (url.includes("/distribution")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ok([])) })
      return
    }
    if (url.includes("/statistics")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ok({ province_count: 3, city_count: 8, scene_count: 12, photo_count: 200 })) })
      return
    }
    if (url.includes("/timeline")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ok({ nodes: [] })) })
      return
    }
    if (url.includes("/markers")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ok([])) })
      return
    }
    if (/\/api\/locations\/[^\/]+\/photos/.test(url)) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ok([])) })
      return
    }
    // 默认 /api/locations（网格视图 / 顶层列表）
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ok([])) })
  })
}

test.beforeEach(async ({ page }) => {
  await injectFakeAuth(page)
  await stubAuthMe(page)
  await stubLocationCatalog(page)
  await mockLocationStatsApis(page)
})

test.describe("LocationStatsView 统计视图 @views-coverage", () => {
  test("统计视图渲染 6 张统计卡 (overview / annual / monthly / top-places / revisits / heatmap)", async ({ page }) => {
    await page.goto("/album/location")
    await expect(page.getByRole("heading", { name: "足迹概览" })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole("heading", { name: "年度旅行趋势" })).toBeVisible()
    await expect(page.getByRole("heading", { name: "月度出行雷达" })).toBeVisible()
    await expect(page.getByText(/最常去的\s*2\s*个地方/)).toBeVisible()
    await expect(page.getByRole("heading", { name: "重访清单" })).toBeVisible()
    await expect(page.getByRole("heading", { name: "旅行日历热力图" })).toBeVisible()
  })

  test("StatsAnnualTrendCard 提供下载为图片按钮", async ({ page }) => {
    await page.goto("/album/location")
    await expect(page.getByRole("heading", { name: "年度旅行趋势" })).toBeVisible({ timeout: 15_000 })
    await expect(page.locator("button[title=\u4e0b\u8f7d\u4e3a\u56fe\u7247]").first()).toBeVisible()
  })

  test("StatsTopPlacesCard 渲染地点列表 + 切换图表模式", async ({ page }) => {
    await page.goto("/album/location")
    await expect(page.getByText("上海").first()).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText("北京").first()).toBeVisible()
    const chartBtn = page.getByRole("button", { name: "图表" })
    await expect(chartBtn).toBeVisible()
    await chartBtn.click()
    await expect(chartBtn).toBeVisible()
    // 切回列表保证不影响后续 test 顺序
    await page.getByRole("button", { name: "列表" }).click()
  })

  test("StatsMonthlyRadarCard 1月、12月月份按钮可见", async ({ page }) => {
    await page.goto("/album/location")
    const monthLabel = page.getByRole("button", { name: "1月" }).first()
    await expect(monthLabel).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole("button", { name: "12月" }).first()).toBeVisible()
  })

  test("StatsRevisitsCard 显示 3 次重访 + 间隔天数", async ({ page }) => {
    await page.goto("/album/location")
    await expect(page.getByText("3 次").first()).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText(/间隔\s*\d+\s*天/).first()).toBeVisible()
  })
})


test.describe("StatsHeatmapCard \u70ed\u529b\u56fe\u5361 @views-coverage", () => {
  test("\u70ed\u529b\u56fe\u5361 \u5355\u5143\u683c\u53ef\u89c1 (\u9ed8\u8ba4 mock \u4e09\u6761\u6570\u636e)", async ({ page }) => {
    await page.goto("/album/location")
    await expect(page.getByRole("heading", { name: "\u65c5\u884c\u65e5\u5386\u70ed\u529b\u56fe" })).toBeVisible({ timeout: 15_000 })
    // count > 0 \u4f1a\u6e32\u67d3\u4e3a button\uff0c\u9ed8\u8ba4 mock \u91cc 5/10/3 \u90fd > 0\uff0c\u5e94\u8be5\u51fa\u73b0 3 \u4e2a\u53ef\u70b9\u51fb\u5355\u5143\u683c
    const cells = page.locator("button[title*=\u5f20\u7167\u7247]")
    await expect(cells).toHaveCount(3)
    // \u56fe\u4f8b\u6587\u6848\uff1a\u5c11 / \u591a \u6807\u7b7e\u53ef\u89c1
    await expect(page.getByText("\u5c11").first()).toBeVisible()
    await expect(page.getByText("\u591a").first()).toBeVisible()
  })

  test("\u70ed\u529b\u56fe\u5355\u5143\u683c \u70b9\u51fb\u540e \u70ed\u529b\u56fe\u672a\u62a5\u9519 (click \u4e0d\u5d29)", async ({ page }) => {
    await page.goto("/album/location")
    await expect(page.getByRole("heading", { name: "\u65c5\u884c\u65e5\u5386\u70ed\u529b\u56fe" })).toBeVisible({ timeout: 15_000 })
    // \u9a8c\u8bc1\u70b9\u51fb\u5355\u5143\u683c\u4e0d\u5d29\uff1a\u70b9\u51fb\u540e\u540c\u4e00\u4e2a\u70ed\u529b\u56fe\u5361\u4ecd\u53ef\u89c1\uff0c\u4e14 retry \u6309\u94ae\u4ecd\u4e0d\u51fa\u73b0
    const cells = page.locator("button[title*=\u5f20\u7167\u7247]")
    const count = await cells.count()
    if (count > 0) {
      await cells.first().click()
      await expect(page.getByRole("heading", { name: "\u65c5\u884c\u65e5\u5386\u70ed\u529b\u56fe" })).toBeVisible()
      await expect(page.getByText("\u7edf\u8ba1\u52a0\u8f7d\u5931\u8d25")).not.toBeVisible()
    }
  })

  test("\u70ed\u529b\u56fe\u52a0\u8f7d\u5931\u8d25 -> \u663e\u793a\u91cd\u8bd5\u6309\u94ae", async ({ page }) => {
    await page.unroute("**/api/location-stats/heatmap**").catch(() => {})
    await page.route("**/api/location-stats/heatmap**", async (route: Route) => {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ code: 500, message: "boom", data: null }),
      })
    })
    await page.goto("/album/location")
    await expect(page.getByText("\u7edf\u8ba1\u52a0\u8f7d\u5931\u8d25")).toBeVisible({ timeout: 15_000 })
    const retry = page.getByRole("button", { name: "\u91cd\u8bd5" })
    await expect(retry).toBeVisible()
    await retry.click()
  })

  test("\u70ed\u529b\u56fe\u7a7a\u6570\u636e -> \u663e\u793a\u201c\u6682\u65e0\u6570\u636e\u201d", async ({ page }) => {
    await page.unroute("**/api/location-stats/heatmap**").catch(() => {})
    await page.route("**/api/location-stats/heatmap**", async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(ok({ total_photos: 0, total_days: 0, data: [] })),
      })
    })
    await page.goto("/album/location")
    await expect(page.getByText("\u6682\u65e0\u6570\u636e").first()).toBeVisible({ timeout: 15_000 })
  })
})
test.describe("LocationDetail 位置详情 @views-coverage", () => {
  test("访问位置详情路由 -> 调用 /api/locations/<name>/photos", async ({ page }) => {
    const photosCalls: string[] = []
    await page.unroute("**/api/locations**").catch(() => {})
    await page.route("**/api/locations/**", async (route: Route) => {
      const url = route.request().url()
      if (/\/api\/locations\/[^\/]+\/photos/.test(url)) {
        photosCalls.push(url)
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ok([])) })
    })
    await page.goto("/album/location/上海")
    await expect.poll(() => photosCalls.length, { timeout: 15_000 }).toBeGreaterThan(0)
  })
})


