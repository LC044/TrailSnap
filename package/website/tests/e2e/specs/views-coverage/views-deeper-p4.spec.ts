import { type Page, type Route } from "@playwright/test"
import { test, expect } from "../../fixtures/auth-page"

/**
 * 本文件所有用例都是 mock 型：page.route 拦截 /api/annual-report/**，不真连后端业务接口。
 * 改用 cleanPage（启动前 localStorage.clear，不带任何 token）后：
 *  - /annual-report 路由守卫对无 token 仍放行（to.path.startsWith('/annual-report')）；
 *  - blank layout 无任何启动期鉴权调用，App.vue 的 SSE 也因 token 为空不连接；
 *  - 视图只调被 mock 的 /api/annual-report/**。
 * 从而彻底脱钩全局共享 token——共享 token 在 CI 并发下会失效，失效后启动期某个接口
 * 401 → request.ts 拦截器 resetState() → /login，正是本文件此前首个用例偶发被踢的根因。
 */
test.describe.configure({ mode: "serial" })

const ok = (data: unknown) => ({ code: 0, message: "success", data })

const fakeUser = { nickname: "E2E 行影者", avatarUrl: "" }
const fakeTime = {
  totalPhotos: 366,
  accompanyDays: 100,
  firstPhotoDate: "2025-01-15",
  lastPhotoDate: "2025-12-20",
  lateNightPhotoCount: 12,
  photoDates: [
    "2025-01-15", "2025-02-03", "2025-03-22", "2025-04-18",
    "2025-05-07", "2025-06-11", "2025-07-29", "2025-08-05",
    "2025-09-14", "2025-10-26", "2025-11-09", "2025-12-20",
  ],
}
const fakeMemory = {
  categoryDistribution: [
    { name: "风景", value: 120 },
    { name: "人物", value: 90 },
    { name: "美食", value: 60 },
  ],
  topPersonName: "小明",
  topPersonCount: 28,
  topLocation: "上海",
  maxPhotoDay: "2025-08-05",
  maxPhotoDayCount: 18,
  topFeature: "夜景",
  topFeatureCount: 35,
  topMake: "Apple",
  topModel: "iPhone 15 Pro",
  topMakeModelCount: 80,
}
const fakeLocation = {
  lightenProvinceNum: 6,
  lightenCityNum: 14,
  topCities: [
    { cityName: "上海", photoCount: 80, provinceName: "上海" },
    { cityName: "北京", photoCount: 55, provinceName: "北京" },
    { cityName: "成都", photoCount: 40, provinceName: "四川" },
  ],
  locationPoints: [
    { lng: 121.47, lat: 31.23, name: "上海", count: 80 },
    { lng: 116.40, lat: 39.90, name: "北京", count: 55 },
  ],
  farthestCity: "三亚",
  farthestDistance: 2780,
  farthestCityPhotos: [],
}
const fakeSeason = {
  seasonList: [
    { seasonName: "春", photoCount: 80, topTag: "嫩芽", representativePhoto: "", highlight: "樱花季", shootMonth: "3-5月" },
    { seasonName: "夏", photoCount: 100, topTag: "蝉鸣", representativePhoto: "", highlight: "海岛游", shootMonth: "6-8月" },
    { seasonName: "秋", photoCount: 90, topTag: "晚风", representativePhoto: "", highlight: "银杏大道", shootMonth: "9-11月" },
    { seasonName: "冬", photoCount: 70, topTag: "暖意", representativePhoto: "", highlight: "雪夜围炉", shootMonth: "12-2月" },
  ],
}
const fakeEmotion = {
  livePhotos: 12,
  backupPhotos: 4,
  cameraPhotos: 350,
  totalVideoDuration: 320,
  emotionCarouselGroups: [
    { id: "g1", locationName: "上海", photos: [] },
  ],
}
const fakeEasterEgg = {
  bestPhotoUrl: "",
  bestPhotoDate: "2025-08-05",
  tags: {
    main: "夜行者",
    sub: ["星空摄影师", "深夜食堂", "雨夜漫步"],
  },
  description: "你的快门在夜色里开了 28 次。",
}
const fakeExpense = {
  totalAmount: 4567,
  totalCount: 12,
  averagePrice: 380,
  monthlyTrend: [
    { month: "2025-01", amount: 320 },
    { month: "2025-02", amount: 480 },
    { month: "2025-08", amount: 1200 },
  ],
  maxExpenseTicket: "G1",
  maxExpenseAmount: 1200,
}
const fakeTransport = {
  behavior: {
    monthlyFrequency: [
      { month: "2025-08", count: 4 },
      { month: "2025-10", count: 3 },
    ],
    topRoutes: [
      { route: "上海 → 北京", count: 5 },
      { route: "北京 → 上海", count: 4 },
    ],
    topDestinations: [
      { city: "上海", count: 6 },
      { city: "北京", count: 4 },
    ],
    tripTypeDistribution: { workday: 8, weekend: 12, holiday: 6 },
  },
  comprehensive: { totalMileage: 12345, costPerKm: 0.37 },
}

type MockOpts = { failAll?: boolean; includeEasterEgg?: boolean; includeExpense?: boolean }

async function mockAnnualReportApis(page: Page, opts: MockOpts = {}) {
  const wrapped = <T,>(d: T) => ({ status: 200, body: JSON.stringify(ok(d)) })
  const fail = { status: 500, body: JSON.stringify({ code: 500, message: "e2e forced failure" }) }
  const f = opts.failAll ? () => fail : wrapped
  const easterEggPayload = opts.includeEasterEgg === false ? undefined : fakeEasterEgg
  await page.route("**/api/annual-report/summary**", (route: Route) => route.fulfill(f({ user: fakeUser, time: fakeTime })))
  await page.route("**/api/annual-report/memory**", (route: Route) => route.fulfill(f(fakeMemory)))
  await page.route("**/api/annual-report/location**", (route: Route) => route.fulfill(f(fakeLocation)))
  await page.route("**/api/annual-report/season**", (route: Route) => route.fulfill(f(fakeSeason)))
  await page.route("**/api/annual-report/emotion**", (route: Route) => route.fulfill(f(fakeEmotion)))
  if (easterEggPayload) {
    await page.route("**/api/annual-report/easter-egg**", (route: Route) => route.fulfill(f(easterEggPayload)))
  } else {
    await page.route("**/api/annual-report/easter-egg**", (route: Route) =>
      route.fulfill({ status: 200, body: JSON.stringify(ok(undefined)) }),
    )
  }
  await page.route("**/api/annual-report/expenses**", (route: Route) => {
    if (opts.includeExpense === false) return route.fulfill(fail)
    if (opts.includeExpense === "null") return route.fulfill({ status: 200, body: JSON.stringify(ok(null)) })
    return route.fulfill(f(fakeExpense))
  })
  await page.route("**/api/annual-report/transport-analysis**", (route: Route) => route.fulfill(f(fakeTransport)))
}

test.beforeEach(async ({ cleanPage: page }) => {
  await mockAnnualReportApis(page)
})

test.describe("AnnualReport 时光报告 @views-coverage", () => {
  test("首次访问 -> 渲染「时光旅人」封面 + 用户昵称 + 向上滑动提示", async ({ cleanPage: page }) => {
    await page.goto("/annual-report")
    await expect(page.getByText("时光旅人").first()).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText("E2E 行影者").first()).toBeVisible()
    await expect(page.getByText("向上滑动，开启你的时光回忆录")).toBeVisible()
  })

  test("数据加载完成后 -> 时间/季节/位置/交通四大主板块标题全部出现", async ({ cleanPage: page }) => {
    await page.goto("/annual-report")
    await expect(page.getByText("时光旅人").first()).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText(/这一年，你用镜头收藏了\s*366\s*个珍贵瞬间/)).toBeVisible()
    await expect(page.getByText("四时之景 · 藏在季节里的岁岁欢喜")).toBeVisible()
    await expect(page.getByText("步履所至 · 年度足迹地图")).toBeVisible()
    await expect(page.getByText("交通出行年度分析")).toBeVisible()
  })

  test("数据加载完成后 -> 季节卡片渲染春/夏/秋/冬四张", async ({ cleanPage: page }) => {
    await page.goto("/annual-report")
    await expect(page.getByText("时光旅人").first()).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText("春 · 嫩芽").first()).toBeVisible()
    await expect(page.getByText("夏 · 蝉鸣").first()).toBeVisible()
    await expect(page.getByText("秋 · 晚风").first()).toBeVisible()
    await expect(page.getByText("冬 · 暖意").first()).toBeVisible()
  })

  test("Easter Egg 彩蛋数据存在 -> 渲染「夜行者」主标签 + 副标签", async ({ cleanPage: page }) => {
    await page.unroute("**/api/annual-report/easter-egg**").catch(() => {})
    await mockAnnualReportApis(page, { includeEasterEgg: true })
    await page.goto("/annual-report")
    await expect(page.getByText("时光旅人").first()).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText("夜行者").first()).toBeVisible()
    await expect(page.getByText("星空摄影师").first()).toBeVisible()
    await expect(page.getByText("深夜食堂").first()).toBeVisible()
  })

  test("Easter Egg 彩蛋数据缺失 (mock 返 null) -> 不渲染彩蛋主标签", async ({ cleanPage: page }) => {
    await page.unroute("**/api/annual-report/easter-egg**").catch(() => {})
    await mockAnnualReportApis(page, { includeEasterEgg: false })
    await page.goto("/annual-report")
    await expect(page.getByText("时光旅人").first()).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText("夜行者")).toHaveCount(0)
  })

  test("所有 /api/annual-report/* 返回 500 -> 渲染「时光数据加载失败」错误态", async ({ cleanPage: page }) => {
    await page.unroute("**/api/annual-report/**").catch(() => {})
    await mockAnnualReportApis(page, { failAll: true })
    await page.goto("/annual-report")
    await expect(page.getByText("时光数据加载失败，请刷新重试")).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText("正在开启时光信笺...")).toHaveCount(0)
  })

  test("Expense 接口返 null (无支出数据) -> 不渲染「交通费用年度分析」标题", async ({ cleanPage: page }) => {
    await page.unroute("**/api/annual-report/**").catch(() => {})
    await mockAnnualReportApis(page, { includeExpense: "null" })
    await page.goto("/annual-report")
    await expect(page.getByText("时光旅人").first()).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText("交通费用年度分析")).toHaveCount(0)
  })
})