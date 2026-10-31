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
  await page.route("**/api/location-stats/top-person-places**", route => route.fulfill({status:200, contentType:"application/json", body:JSON.stringify(ok([]))}))
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

test.describe("足迹统计 @views-coverage", () => {
  test("显示明确指标、时间趋势、地点排名和拍摄日历", async ({ page }) => {
    await page.goto("/album/location")
    await expect(page.getByRole("heading", { name: "足迹统计" })).toBeVisible()
    await expect(page.getByRole("region", { name: "足迹概览" })).toBeVisible()
    for (const name of ["足迹随时间变化", "留下最多照片的地方", "多日记录的地方", "拍摄日历", "人物足迹"]) {
      await expect(page.getByRole("heading", { name })).toBeVisible()
    }
    await expect(page.getByText("移动距离", { exact: true })).toBeVisible()
    await expect(page.getByRole("button", { name: "下载趋势图" })).toBeVisible()
  })
  test("自动展示照片最多人物及地点并保留照片下钻", async ({ page }) => {
    await page.route('**/api/location-stats/top-person-places**', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ok([
      { person_id: '11111111-1111-1111-1111-111111111111', person_name: '小周', cover_photo_id: null, total_places: 1, total_photos: 12, total_days: 3, places: [{ name: '杭州', level: 'city', place_key: 'place:region:city:2:中国2:浙江2:杭州', scene_id: null, parent_label: '浙江', photo_count: 12, record_days: 3, first_date: '2024-02-01', last_date: '2024-02-29' }] },
      { person_id: '22222222-2222-2222-2222-222222222222', person_name: '小李', cover_photo_id: null, total_places: 1, total_photos: 5, total_days: 1, places: [{ name: '上海', level: 'city', place_key: 'place:region:city:2:中国2:上海2:上海', scene_id: null, parent_label: '上海', photo_count: 5, record_days: 1, first_date: '2024-03-01', last_date: '2024-03-01' }] },
    ])) }))
    await page.goto('/album/location')
    await expect(page.getByRole('region', { name: '小周的足迹' })).toBeVisible()
    await expect(page.getByRole('region', { name: '小李的足迹' })).toBeVisible()
    await expect(page.getByRole('combobox', { name: '选择统计人物' })).toHaveCount(0)
    await expect(page.getByText('1 个城市 · 12 张照片 · 3 个记录日')).toBeVisible()
    await page.getByRole('button', { name: '查看小周在杭州的 12 张照片' }).click()
    await expect(page).toHaveURL(/personId=11111111-1111-1111-1111-111111111111/)
    await expect(page).toHaveURL(/place_key=/)
  })
  test("切换指标及月份，月度选择显示具体年份", async ({ page }) => {
    await page.goto("/album/location")
    await page.getByRole("button", { name: "记录天数", exact: true }).click()
    await expect(page.getByRole("img", { name: "年度记录天数柱状图" })).toBeVisible()
    await page.getByRole("button", { name: "按月", exact: true }).click()
    await expect(page.getByLabel("趋势年份")).toBeVisible()
    await expect(page.getByRole("img", { name: "月度记录天数柱状图" })).toBeVisible()
  })
  test("地点排名显示照片单位和查看入口", async ({ page }) => {
    await page.goto("/album/location")
    await expect(page.getByRole("button", { name: /上海，.*张照片，查看照片/ })).toBeVisible()
    await expect(page.getByRole("button", { name: /北京，.*张照片，查看照片/ })).toBeVisible()
    await expect(page.getByText(/不代表独立到访次数/)).toBeVisible()
  })
  test("日历单元格可下钻，日期筛选展示正确", async ({ page }) => {
    await page.goto("/album/location")
    const cell = page.locator(".calendar-cell[aria-label]").first()
    await expect(cell).toBeVisible()
    await cell.click()
    await expect(page).toHaveURL(/\/album\/location/)
    await expect(page.getByRole("heading", { name: "拍摄日历" })).not.toBeVisible()
  })
  test("时间数据失败可重试", async ({ page }) => {
    await page.route("**/api/location-stats/heatmap**", route => route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ code: 500, msg: "boom", data: null }) }))
    await page.goto("/album/location")
    await expect(page.getByText("拍摄日历加载失败", { exact: true })).toBeVisible()
    await page.getByRole("button", { name: "重试", exact: true }).first().click()
    await expect(page.getByText("时间统计加载失败", { exact: true })).toBeVisible()
  })
  test("无拍摄数据时显示明确空状态", async ({ page }) => {
    await page.route("**/api/location-stats/heatmap**", route => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ok({ total_photos: 0, total_days: 0, data: [] })) }))
    await page.goto("/album/location")
    await expect(page.getByText("这段时间还没有拍摄记录").first()).toBeVisible()
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


