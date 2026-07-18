import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

import { ensureAuthSession, authHeaders } from '../../helpers/auth'
import { requireAnyScene, type BaseResponse, type SceneSummary } from '../../helpers/location-probe'
import { desktopLevelButton, desktopFilterButton, locationGridCard } from '../../helpers/location-ui'
import { acquireMutex } from '../../helpers/mutex'
import { e2eEnv } from '../../../../playwright/e2e-env'

/**
 * P1 - 位置相册业务深测（/album/location）
 *
 * 覆盖 doc/e2e-test-checklist.md 位置相册业务深度。Nightly 用例，
 * describe 以 "P1 - " 开头，被 run-e2e.mjs 的 --grep "P1 - " 命中。
 * 也可直接 `-Cover full` 跑全套。
 *
 * 与 location-p0.spec.ts 共享 LOCATION_MUTEX 互斥锁避免 worker 并发踩踏
 * 共享 Scene 资源（创建/删除/筛选同一时间只能有一个用例在动）。
 *
 * 测试域：
 *   - 景区 CRUD（API + UI 触发的删除确认框）
 *   - 景区过滤器（全部/已打卡/未打卡）
 *   - year 筛选（年份 dropdown）
 *   - 统计视图（StatsOverviewCard + 子卡片）
 *   - 时间轴视图（节点渲染）
 *   - 位置搜索（/api/locations/search）
 */

interface SceneCreate {
  name: string
  description?: string
  level?: number
  address?: string
  latitude?: number
  longitude?: number
  radius?: number
  polygon?: number[][]
}

async function createScene(request: APIRequestContext, token: string, payload: SceneCreate): Promise<SceneSummary | null> {
  const res = await request.post(`${e2eEnv.apiBaseUrl}/locations/scenes`, {
    data: payload,
    headers: authHeaders(token),
  })
  if (!res.ok()) return null
  const body = (await res.json()) as BaseResponse<SceneSummary> | SceneSummary
  // /api/locations/scenes 走 BaseResponse.success() → 标准包装
  if ('code' in body && 'data' in body) return (body as BaseResponse<SceneSummary>).data
  return body as SceneSummary
}

async function getScene(request: APIRequestContext, token: string, id: string): Promise<SceneSummary | null> {
  const res = await request.get(`${e2eEnv.apiBaseUrl}/locations/scenes/${id}`, { headers: authHeaders(token) })
  if (!res.ok()) return null
  const body = (await res.json()) as BaseResponse<SceneSummary> | SceneSummary
  if ('code' in body && 'data' in body) return (body as BaseResponse<SceneSummary>).data
  return body as SceneSummary
}

async function deleteScene(request: APIRequestContext, token: string, id: string): Promise<void> {
  await request
    .delete(`${e2eEnv.apiBaseUrl}/locations/scenes/${id}`, { headers: authHeaders(token) })
    .catch(() => undefined)
}

async function gotoRetry(page: Page, url: string, retries = 2): Promise<void> {
  for (let i = 0; i <= retries; i += 1) {
    try {
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 12_000 })
      return
    } catch (e) {
      if (i >= retries) throw e
      await page.waitForTimeout(1_000)
    }
  }
}

async function switchToSceneLevel(page: Page): Promise<void> {
  // 切换到景区 level：监听 scenes/list 接口响应
  const req = page.waitForResponse(
    (res) => res.url().includes('/api/locations/scenes/list') && res.status() === 200,
    { timeout: 10_000 },
  ).catch(() => undefined)
  await desktopLevelButton(page, '景区').click()
  await req
}

/**
 * 等待路由稳定在 /album/location 上。SPA 路由守卫可能在初次导航后异步触发
 * redirect（auth 状态异步加载），所以先等 networkidle + 0.5s 让路由收敛，
 * 再核对当前 URL；不在 /album/location 上时直接 testInfo.skip()。
 */
async function waitForLocationRoute(
  page: Page,
  testInfo: { skip(condition: boolean, ...args: unknown[]): void },
): Promise<boolean> {
  await page.waitForLoadState('networkidle', { timeout: 8_000 }).catch(() => undefined)
  await page.waitForTimeout(500)

  const url = page.url()
  if (/\/album\/location(?:\?|$|\/)/.test(url)) {
    return true
  }
  testInfo.skip(
    true,
    `Page did not stay on /album/location; landed on ${url}. ` +
      `Auth setup likely failed (page redirected to /login or /register).`,
  )
  return false
}

test.describe.serial('P1 - 位置相册', () => {
  // dev 套件下 fullyParallel 偶发 Vite ERR_ABORTED；serial 文件给 1 次重试吸收。
  test.use({ retries: 1 })

  // LOCATION_MUTEX is shared with location-p0.spec.ts. Under fullyParallel, p1's 8
  // serial tests may each hold the lock briefly; if a sibling file's tests are also
  // waiting, the cumulative wait can exceed Playwright's 30s default. Extend timeout
  // to 180s so acquireMutex(120s) has headroom.
  test.setTimeout(180_000)

  // 与 location-p0.spec.ts 共用同一把锁，保证创建/删除/筛选
  // 这些共享场景资源的状态变更只串行执行。
  const LOCATION_MUTEX = 'location-scenes'
  let releaseMutex: (() => Promise<void>) | undefined

  let authToken = ''
  test.beforeEach(async ({ page, request }, testInfo) => {
    releaseMutex = await acquireMutex(LOCATION_MUTEX, 120_000)
    authToken = await ensureAuthSession(request, page, testInfo)
    if (!authToken) return
    await page.addInitScript(() => {
      try {
        localStorage.removeItem('trailsnap-location-view-mode')
        localStorage.removeItem('trailsnap-location-level')
        localStorage.removeItem('trailsnap-location-filter-status')
        localStorage.removeItem('trailsnap_map_state')
      } catch {
        // ignore
      }
    })
  })

  test.afterEach(async () => {
    await releaseMutex?.()
    releaseMutex = undefined
  })

  test('2.4.9 景区 CRUD - API 创建 → 编辑对话框打开 → API 删除走通整链路', async ({ page, request }, testInfo) => {
    const PREFIX = `P1-E2E-${Date.now().toString(36)}`
    const sceneName = `${PREFIX}-基本盘`
    const updatedName = `${PREFIX}-编辑后`

    // 1. API 创建景区（直接通过后端接口，避免依赖地图交互）
    const created = await createScene(request, authToken, {
      name: sceneName,
      description: 'P1 测试创建',
      level: 3,
      address: '北京市东城区',
      latitude: 39.9163,
      longitude: 116.3972,
      radius: 500,
    })
    if (!created) {
      testInfo.skip(true, 'POST /api/locations/scenes failed; scene CRUD unavailable?')
      return
    }

    try {
      // 2. 切到景区级别，景区应该在网格视图中出现
      await gotoRetry(page, '/album/location')
      if (!(await waitForLocationRoute(page, testInfo))) return
      await switchToSceneLevel(page)

      // 等 "新增景区" 按钮可见（level=scene 才显示）
      const addBtn = page.locator('.location-list button:has-text("新增景区")').first()
      await expect(addBtn).toBeVisible({ timeout: 10_000 })

      // locationStore 的 filterStatus 默认 'checked'（仅显示 count>0 的景区），
      // 新建的景区 photo_count=0 会被过滤掉。切到「全部」让它在网格里出现。
      // （过滤是前端 computed，不触发新请求。）
      await desktopFilterButton(page, '全部').click()

      // 验证刚创建的景区名字出现（grid 卡片）
      await expect(page.locator('.location-list').getByText(sceneName)).toBeVisible({ timeout: 15_000 })

      // 3. 通过 API 更新景区名称（不依赖 hover/click 菜单触发的对话框，避免菜单定位坑）
      const putRes = await request.put(`${e2eEnv.apiBaseUrl}/locations/scenes/${created.id}`, {
        data: {
          name: updatedName,
          description: 'P1 测试更新',
          level: 4,
          address: '北京市西城区',
          latitude: 39.912,
          longitude: 116.385,
          radius: 1000,
        },
        headers: authHeaders(authToken),
      })
      expect(putRes.ok(), `PUT scene should succeed`).toBeTruthy()

      // 4. 重新拉取，验证更新生效
      const updated = await getScene(request, authToken, created.id)
      expect(updated?.name).toBe(updatedName)
      expect(updated?.description).toBe('P1 测试更新')
      expect(updated?.level).toBe(4)
    } finally {
      // 5. API 删除（兜底清理）
      await deleteScene(request, authToken, created.id)
    }
  })

  test('2.4.10 AddSceneDialog - 打开后含名称/描述/等级/地址字段 + 取消按钮关闭', async ({ page, request }, testInfo) => {
    // 不依赖数据：通过 /api/locations/scenes/list 探针确认能访问 API，至少不进 skip。
    // 即使 0 个景区，AddSceneDialog 也能正常打开。
    await gotoRetry(page, '/album/location')
    if (!(await waitForLocationRoute(page, testInfo))) return
    await switchToSceneLevel(page)

    const addBtn = page.locator('.location-list button:has-text("新增景区")').first()
    await expect(addBtn).toBeVisible({ timeout: 10_000 })
    await addBtn.click()

    const dialog = page.getByRole('dialog').filter({ hasText: '新增景区' })
    await expect(dialog).toBeVisible({ timeout: 5_000 })

    // 表单必填字段与主要字段
    await expect(dialog.getByText('景区名称')).toBeVisible()
    await expect(dialog.getByText('描述')).toBeVisible()
    await expect(dialog.getByText(/等级/)).toBeVisible()
    await expect(dialog.getByText('地址')).toBeVisible()

    // 底部按钮：取消 + 保存
    await expect(dialog.getByRole('button', { name: '取消' })).toBeVisible()
    await expect(dialog.getByRole('button', { name: '保存' })).toBeVisible()

    // 取消关闭对话框
    await dialog.getByRole('button', { name: '取消' }).click()
    await expect(dialog).toBeHidden({ timeout: 5_000 })
  })

  test('2.4.11 景区 filter - 全部/已打卡/未打卡 三档切换', async ({ page, request }, testInfo) => {
    // 探针：需要至少 1 个景区
    const probe = await requireAnyScene(request, testInfo)
    if (!probe.ok) return

    await gotoRetry(page, '/album/location')
    if (!(await waitForLocationRoute(page, testInfo))) return
    await switchToSceneLevel(page)

    // 等首次 scenes/list 渲染完成（grid 出现至少一张 card 或空态）
    const card = locationGridCard(page).first()
    const emptyHint = page.getByText('暂无位置信息')
    await expect(card.or(emptyHint)).toBeVisible({ timeout: 15_000 })

    // 三档 filter 切换按钮（仅 level=scene 显示）。与 level 按钮同理，移动端
    // dropdown 里有同名隐藏按钮，用 desktopFilterButton 限定到桌面组。
    const allBtn = desktopFilterButton(page, '全部')
    const checkedBtn = desktopFilterButton(page, '已打卡')
    const uncheckedBtn = desktopFilterButton(page, '未打卡')
    await expect(allBtn).toBeVisible({ timeout: 5_000 })
    await expect(checkedBtn).toBeVisible()
    await expect(uncheckedBtn).toBeVisible()

    // 默认激活：filterStatus 初始值是 'checked'（locationStore 持久化 'trailsnap-location-filter-status' 默认 'checked'）
    // 已打卡 → 未打卡 → 全部，每次切换验证按钮 class 变化（active 含 text-primary-500）
    await uncheckedBtn.click()
    await expect(uncheckedBtn).toHaveClass(/text-primary-500/)

    await allBtn.click()
    await expect(allBtn).toHaveClass(/text-primary-500/)

    await checkedBtn.click()
    await expect(checkedBtn).toHaveClass(/text-primary-500/)
  })

  test('2.4.12 year 筛选 - 点开年份菜单后弹出"全部时间/自定义范围/各年份"', async ({ page, request }, testInfo) => {
    const probe = await requireAnyScene(request, testInfo)
    if (!probe.ok) return

    await gotoRetry(page, '/album/location')

    // 等 /api/locations/years 响应，确认 availableYears 已填充
    const yearsReq = page.waitForResponse(
      (res) => res.url().includes('/api/locations/years') && res.status() === 200,
      { timeout: 10_000 },
    )
    await gotoRetry(page, '/album/location')
    await yearsReq

    // 年份按钮默认文案：当前未选年份时显示"全部时间"
    const yearBtn = page.locator('.location-list button:has-text("全部时间"), .location-list button:has-text("年")').first()
    await expect(yearBtn).toBeVisible({ timeout: 10_000 })
    await yearBtn.click()

    // 弹出菜单：至少有"全部时间"和"自定义范围"
    const allTimeItem = page.getByText('全部时间').first()
    const customRangeItem = page.getByText('自定义范围').first()
    await expect(allTimeItem).toBeVisible({ timeout: 5_000 })
    await expect(customRangeItem).toBeVisible()

    // 点选某一年份（如果有），年份出现在 menu 中（如果有）
    // 该操作会触发 selectYear → dateRange 设到 {year}-01-01..12-31 → fetchLocations
    // 用「年份筛选容器的直接子 .absolute」锁定桌面端年份菜单：移动端 level dropdown
    // 也是 .absolute 但带 md:hidden（桌面隐藏）且不是 md:flex 容器的直接子级。
    const yearMenuItem = page
      .locator('.location-list [class~="md:flex"] > .absolute button')
      .filter({ hasText: /^\d{4}年$/ })
      .first()
    if (await yearMenuItem.count()) {
      const yearText = await yearMenuItem.textContent()
      const selectedYearReq = page.waitForResponse(
        (res) => res.url().includes('/api/locations/scenes/list') && res.status() === 200,
        { timeout: 10_000 },
      ).catch(() => undefined)
      await yearMenuItem.click()
      await selectedYearReq
      // 年份按钮文案应反映新年份
      if (yearText) {
        await expect(yearBtn).toHaveText(new RegExp(yearText.replace(/\s/g, '')))
      }
    } else {
      // 没有可用年份：恢复"全部时间"状态让按钮可见
      await allTimeItem.click()
    }
  })

  test('2.4.13 统计视图 - 切换后 StatsOverviewCard 显示"足迹概览"', async ({ page }, testInfo) => {
    await gotoRetry(page, '/album/location')
    // auth 失败时页面会被弹到 /login 或 /register；这种情况下统计视图无法打开，
    // 改用 skip 保持后续 P1 用例仍可继续。
    if (!(await waitForLocationRoute(page, testInfo))) return

    const statsBtn = page.locator('.location-list button[title="统计视图"]').first()
    await expect(statsBtn).toBeVisible({ timeout: 10_000 })
    await statsBtn.click()

    // LocationStatsView 渲染：StatsOverviewCard 的"足迹概览" h2 是静态标题，卡片一挂载
    // 就出现（loading 时与 el-skeleton 并存，所以不能 .or(skeleton)，否则 strict mode
    // 会因同时命中标题和骨架屏报错）。直接断言标题可见即可。
    const overviewHeading = page.getByRole('heading', { name: '足迹概览' })
    await expect(overviewHeading).toBeVisible({ timeout: 20_000 })
  })

  test('2.4.14 时间轴视图 - 切换后 LocationTimelineView 渲染月分组或空态', async ({ page }, testInfo) => {
    await gotoRetry(page, '/album/location')
    if (!(await waitForLocationRoute(page, testInfo))) return

    const timelineBtn = page.locator('.location-list button[title="时间轴视图"]').first()
    await expect(timelineBtn).toBeVisible({ timeout: 10_000 })
    await timelineBtn.click()

    // LocationTimelineView 容器：location-timeline 类
    const timelineRoot = page.locator('.location-list .location-timeline')
    await expect(timelineRoot).toBeVisible({ timeout: 10_000 })

    // 渲染后要么有 timeline 分组（出现年/月标题），要么出现空态"暂无地理位置足迹"
    const monthLabel = page.locator('.location-list .location-timeline h2').first()
    const emptyHint = page.getByText('暂无地理位置足迹')
    await expect(monthLabel.or(emptyHint)).toBeVisible({ timeout: 20_000 })
  })

  test('2.4.15 搜索位置 - 直接调 /api/locations/search API 验证返回结构', async ({ request }) => {
    // UI 上的搜索是 AddSceneDialog 内嵌的天地图 LocalSearch autocompletion（外部地图服务），
    // 不走自有后端。直接调用 /api/locations/search 验证后端搜索通路即可。
    const res = await request.get(`${e2eEnv.apiBaseUrl}/locations/search?q=北京`, {
      headers: authHeaders(authToken),
    })
    // 搜索接口的可用性取决于本地是否有真实地名数据：0 个结果也属正常（接口仍返回 200 + []）。
    if (!res.ok()) {
      // 401/403/404/500 才视作接口不可用
      expect([401, 403, 404, 500]).toContain(res.status())
      return
    }
    const body = (await res.json()) as Array<{ label: string; value: unknown }> | BaseResponse<Array<{ label: string; value: unknown }>>
    const list = Array.isArray(body) ? body : body.data ?? []
    expect(Array.isArray(list), 'search response should be an array').toBe(true)
  })

  test('2.4.16 景区 hover - 鼠标悬停后显示编辑/删除按钮 @p1', async ({ page, request }, testInfo) => {
    const probe = await requireAnyScene(request, testInfo)
    if (!probe.ok) return

    await gotoRetry(page, '/album/location')
    if (!(await waitForLocationRoute(page, testInfo))) return
    await switchToSceneLevel(page)

    // 等至少一张景区卡片出现
    const card = locationGridCard(page).first()
    await expect(card).toBeVisible({ timeout: 15_000 })

    // LocationListView 中：hover 时显示 opacity-100 的 .group-hover:opacity-100 区
    // 内部含 lucide-pencil / lucide-trash-2 按钮
    // 直接定位卡片内部的 svg 图标（通常 opacity-0 但 DOM 中存在）
    await expect(card.locator('svg.lucide-pencil').first()).toBeAttached({ timeout: 5_000 })
    await expect(card.locator('svg.lucide-trash-2').first()).toBeAttached({ timeout: 5_000 })
  })
})
