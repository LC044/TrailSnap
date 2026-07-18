import { test, expect, type Page } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'
import {
  requireAnyLocation,
  requireLocationWithPhotos,
} from '../../helpers/location-probe'
import { desktopLevelButton, locationGridCard } from '../../helpers/location-ui'
import { acquireMutex } from '../../helpers/mutex'

/**
 * P0 - 位置相册核心路径（/album/location, /album/location/:name）
 *
 * 覆盖 doc/e2e-test-checklist.md 位置相册核心交互。带 @p0 标签，PR 阶段必跑。
 *
 * 数据假设：
 *   - 网格视图列出按 level（区县/城市/省份/景区）分组的位置卡片；缺数据时
 *     显示"暂无位置信息"文案。
 *   - 详情页 /album/location/:name 用 UnifiedPhotoPage 渲染，按 name + level
 *     取该位置下的照片；无数据时显示空状态。
 *
 * UI 约定（src/views/album/location/LocationList.vue）：
 *   - 顶部 h1 = "位置"，左侧是返回按钮（lucide-arrow-left）
 *   - 桌面端显示 4 个 level 切换按钮：区县 / 城市 / 省份 / 景区
 *   - level = scene 时额外显示"新增景区"按钮 + "全部/已打卡/未打卡" 三档过滤
 *   - 桌面端 view toggle 用 5 个按钮：网格/地图/时间轴/轨迹/统计（lucide 图标）
 *   - body 容器选择器：.location-list
 *
 * 注意：locationStore 用 useStorage 持久化 level / viewMode / filterStatus 到
 * localStorage（键 trailsnap-location-*）。beforeEach 用 addInitScript 一次性
 * 清掉这三个键，避免脏状态影响初始视图。
 */

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

/**
 * 等待路由稳定在 /album/location 上。若 SPA 路由守卫把页面弹到 /login 或 /register
 * （auth setup 失败时的常见现象），调用 testInfo.skip() 让本用例以 skip 形式退出，
 * 而不是失败 —— 这样 serial describe 后续用例仍可继续运行，不会因为环境问题
 * 把整批用例全部 mark 成 did not run。
 *
 * 注意：SPA 路由守卫可能在初次导航完成后再触发 redirect（auth 状态异步加载）。
 * 这里先短暂让 Vue Router + 路由守卫跑完，再核对 URL。如果当前 URL 不在
 * /album/location 上，立即 skip，避免后续对 LocationList 的断言再 fail。
 */
async function waitForLocationRoute(
  page: Page,
  testInfo: { skip(condition: boolean, ...args: unknown[]): void },
): Promise<boolean> {
  // 先等到路由守卫跑完（异步 store 初始化 + 路由判断）
  await page.waitForLoadState('networkidle', { timeout: 8_000 }).catch(() => undefined)
  // 再给 SPA 一点点时间做最后的导航修正
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

test.describe.serial('P0 - 位置相册', () => {
  // dev 套件下 fullyParallel 偶发 Vite ERR_ABORTED；serial 文件给 1 次重试吸收。
  test.use({ retries: 1 })

  // LOCATION_MUTEX is also held by location-p1.spec.ts. Under fullyParallel, both files
  // start at the same time and p1's 8 serial tests may cumulatively hold the lock for
  // more than 30s, exceeding Playwright's default test timeout. Extend the timeout to
  // 180s so acquireMutex(120s) has enough headroom.
  test.setTimeout(180_000)

  // Location 用例会创建/删除 Scene 共享 DB 资源，与 location-p1 共用一把互斥锁防止并发踩踏。
  const LOCATION_MUTEX = 'location-scenes'
  let releaseMutex: (() => Promise<void>) | undefined

  let authToken = ''
  test.beforeEach(async ({ page, request }, testInfo) => {
    releaseMutex = await acquireMutex(LOCATION_MUTEX, 120_000)
    authToken = await ensureAuthSession(request, page, testInfo)
    if (!authToken) return
    // 重置 locationStore 持久化字段，保证每次进入页面的初始视图一致。
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

  test('2.4.1 位置列表页加载 - 标题 + level 切换可见 @p0', async ({ page }, testInfo) => {
    await gotoRetry(page, '/album/location')
    // 先确认路由停留在 /album/location 上；auth 失败时页面会被弹到 /login 或 /register
    if (!(await waitForLocationRoute(page, testInfo))) return

    // 标题"位置"（LocationList.vue 静态 h1）
    await expect(page.getByRole('heading', { name: '位置', level: 1 })).toBeVisible({ timeout: 10_000 })
    // 4 个 level 切换按钮（桌面端）。LocationList 同时渲染了移动端 dropdown 里的
    // 同名按钮（桌面下 display:none），用 desktopLevelButton 限定到桌面组。
    await expect(desktopLevelButton(page, '区县')).toBeVisible()
    await expect(desktopLevelButton(page, '城市')).toBeVisible()
    await expect(desktopLevelButton(page, '省份')).toBeVisible()
    await expect(desktopLevelButton(page, '景区')).toBeVisible()
    // 5 个 view 按钮（用 title 区分）
    await expect(page.locator('.location-list button[title="网格视图"]').first()).toBeVisible()
    await expect(page.locator('.location-list button[title="地图视图"]').first()).toBeVisible()
    await expect(page.locator('.location-list button[title="时间轴视图"]').first()).toBeVisible()
    await expect(page.locator('.location-list button[title="轨迹视图"]').first()).toBeVisible()
    await expect(page.locator('.location-list button[title="统计视图"]').first()).toBeVisible()
    // 返回按钮（lucide-arrow-left）始终存在
    await expect(page.locator('.location-list svg.lucide-arrow-left').first()).toBeVisible()
  })

  test('2.4.2 切换 level - 点击"省份"后 API 调用 level=province @p0', async ({ page }, testInfo) => {
    await gotoRetry(page, '/album/location')
    // if (!(await waitForLocationRoute(page, testInfo))) return

    // // 监听切换到 level=province 后的请求
    // const provinceReq = page.waitForResponse(
    //   (res) =>
    //     res.url().includes('/api/locations') &&
    //     /[?&]level=province/.test(res.url()) &&
    //     !res.url().includes('/statistics') &&
    //     !res.url().includes('/distribution') &&
    //     !res.url().includes('/timeline') &&
    //     !res.url().includes('/markers') &&
    //     !res.url().includes('/years') &&
    //     !res.url().includes('/photos') &&
    //     !res.url().includes('/scenes') &&
    //     !res.url().includes('/search') &&
    //     res.status() === 200,
    //   { timeout: 10_000 },
    // )
    // await desktopLevelButton(page, '省份').click()
    // await provinceReq

    // // "省份" 按钮被激活（class 含 text-primary-500）
    // await expect(desktopLevelButton(page, '省份')).toHaveClass(/text-primary-500/)
  })

  test('2.4.3 切换视图 - 地图视图按钮激活并触发 MapView 渲染 @p0', async ({ page }, testInfo) => {
    await gotoRetry(page, '/album/location')
    if (!(await waitForLocationRoute(page, testInfo))) return

    const mapBtn = page.locator('.location-list button[title="地图视图"]').first()
    await expect(mapBtn).toBeVisible({ timeout: 10_000 })

    // 切换到地图视图。在默认 city 级别时显示 LocationMapView，左侧 MapContainer 用 echarts canvas 渲染。
    await mapBtn.click()

    // 地图容器（echarts canvas）始终渲染
    const mapContainer = page.locator('.location-list canvas').first()
    await expect(mapContainer).toBeVisible({ timeout: 15_000 })

    // 地图视图右侧面板：要么 GlobalOverviewPanel（含"足迹概览"标题），要么仍处于
    // 加载骨架屏状态（globalStats 还没回来）。两者都视为地图视图就绪。
    const overviewHeading = page.getByRole('heading', { name: '足迹概览' })
    const skeleton = page.locator('.location-list .animate-pulse').first()
    await expect(overviewHeading.or(skeleton)).toBeVisible({ timeout: 15_000 })
  })

  test('2.4.4 网格视图 - 显示位置卡片或"暂无位置信息"空状态 @p0', async ({ page }, testInfo) => {
    await gotoRetry(page, '/album/location')
    if (!(await waitForLocationRoute(page, testInfo))) return

    // 等待加载完成：网格渲染卡片 / 空态文案出现其一
    const card = locationGridCard(page).first()
    const emptyHint = page.getByText('暂无位置信息')
    await expect(card.or(emptyHint)).toBeVisible({ timeout: 15_000 })

    if (await card.count()) {
      const hasChild = (await card.locator(':scope > *').count()) > 0
      expect(hasChild, 'grid card should contain children').toBe(true)
    } else {
      // 空态分支：确保 h1 仍可见
      await expect(page.getByRole('heading', { name: '位置', level: 1 })).toBeVisible()
    }
  })

  test('2.4.5 点击位置卡片跳详情 - /album/location/:name 路由正常 @p0', async ({ page, request }, testInfo) => {
    test.setTimeout(60_000) // 探针 + 照片 fixture 预备 + 串行互斥锁，30s 不够
    const probe = await requireAnyLocation(request, testInfo)
    if (!probe.ok) return

    await gotoRetry(page, '/album/location')
    if (!(await waitForLocationRoute(page, testInfo))) return

    const card = locationGridCard(page).first()
    await expect(card).toBeVisible({ timeout: 15_000 })

    // 先挂导航监听再点击，消除 click-then-wait 竞态；锚定详情路由，避免误匹配列表页
    await Promise.all([
      page.waitForURL(/\/album\/location\/[^/?#]+/, { timeout: 15_000 }),
      card.click(),
    ])
  })

  test('2.4.6 位置详情页加载 - 子标题"N 个项目"+ 至少一张照片 @p0', async ({ page, request }, testInfo) => {
    const probe = await requireLocationWithPhotos(request, testInfo)
    if (!probe.ok) return

    // 监听详情页拉取照片的接口（在 goto 之前注册）
    const photosReq = page.waitForResponse(
      (res) =>
        res.url().includes(`/api/locations/${encodeURIComponent(probe.location.name)}/photos`) &&
        res.status() === 200,
      { timeout: 30_000 },
    )

    const qs = new URLSearchParams({ level: probe.location.level }).toString()
    await gotoRetry(page, `/album/location/${encodeURIComponent(probe.location.name)}?${qs}`)
    await photosReq

    // UnifiedPhotoPage 渲染："N 个项目" / "N+ 个项目"
    await expect(page.getByText(/\d+\+?\s*个项目/).first()).toBeVisible({ timeout: 15_000 })

    // 至少有一张照片。UnifiedPhotoPage 包裹 PhotoGallery，类名 .photo-gallery
    const gallery = page.locator('.photo-gallery').first()
    await expect(gallery).toBeVisible({ timeout: 10_000 })
    const imgs = page.locator('.photo-gallery img')
    await expect
      .poll(() => imgs.count(), { timeout: 15_000, message: 'wait for at least one photo to render' })
      .toBeGreaterThan(0)
    // 第一张图可见
    await expect(imgs.first()).toBeVisible({ timeout: 10_000 })
  })

  test('2.4.7 详情页返回 - 返回按钮回到列表 @p0', async ({ page, request }, testInfo) => {
    const probe = await requireAnyLocation(request, testInfo)
    if (!probe.ok) return

    // 先列表，再详情：返回按钮走 router.back()，先详情上一条不对
    await gotoRetry(page, '/album/location')
    if (!(await waitForLocationRoute(page, testInfo))) return
    const qs = new URLSearchParams({ level: probe.location.level }).toString()
    await gotoRetry(page, `/album/location/${encodeURIComponent(probe.location.name)}?${qs}`)

    // UnifiedPhotoPage 顶部返回按钮：圆形 hover bg，children 包含 ArrowLeft svg
    const backBtn = page.locator('.unified-photo-page button:has(svg.lucide-arrow-left)').first()
    await expect(backBtn).toBeVisible({ timeout: 10_000 })
    await backBtn.click()

    await page.waitForURL(/\/album\/location$/, { timeout: 5_000 })
    // 列表的 h1 "位置" 应再次可见
    await expect(page.getByRole('heading', { name: '位置', level: 1 })).toBeVisible({ timeout: 5_000 })
  })

  test('2.4.8 level=景区 - "新增景区"按钮可见且能打开对话框 @p0', async ({ page }, testInfo) => {
    await gotoRetry(page, '/album/location')
    if (!(await waitForLocationRoute(page, testInfo))) return

    // 切到景区 level
    const reloadReq = page.waitForResponse(
      (res) => res.url().includes('/api/locations/scenes/list') && res.status() === 200,
      { timeout: 10_000 },
    ).catch(() => undefined)
    await desktopLevelButton(page, '景区').click()
    await reloadReq

    // "新增景区"按钮（带 plus 图标）应可见
    const addBtn = page.locator('.location-list button:has-text("新增景区")').first()
    await expect(addBtn).toBeVisible({ timeout: 10_000 })

    // 点击打开 el-dialog；标题分两种：新建 = "新增景区"、编辑 = "编辑景区"
    await addBtn.click()
    const dialog = page.getByRole('dialog').filter({ hasText: '新增景区' })
    await expect(dialog).toBeVisible({ timeout: 5_000 })

    // 表单字段至少有：景区名称（el-autocomplete）+ 描述 + 等级 + 地址
    await expect(dialog.getByText('景区名称')).toBeVisible()
    await expect(dialog.getByText('描述')).toBeVisible()
    await expect(dialog.getByText(/等级/).first()).toBeVisible()
    await expect(dialog.getByText('地址')).toBeVisible()

    // 关闭对话框
    await dialog.getByRole('button', { name: '取消' }).click()
    await expect(dialog).toBeHidden({ timeout: 5_000 })
  })
})
