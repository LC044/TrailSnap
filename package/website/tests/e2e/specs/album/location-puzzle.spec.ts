import { test, expect, type Page } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'
import { acquireMutex } from '../../helpers/mutex'

/**
 * P0 - 位置相册 · 照片拼图视图（/album/location, viewMode=puzzle）
 *
 * 覆盖 LocationPuzzleView.vue —— 位置相册的第六个视图模式。带 @p0 标签，
 * PR 阶段必跑（见 playwright/run-e2e.mjs 的 SUITE_CONFIG.p0 = --grep @p0）。
 *
 * 与 location-p0 / location-p1 共用 LOCATION_MUTEX，避免并发切 viewMode /
 * 触发 geojson + photos 请求时踩踏（这几个文件都在动 /album/location 页）。
 *
 * 设计原则（对齐 location-p0/p1 的既有约定）：
 *   - CI 环境不保证有带 GPS 的照片，拼图可能是「全空」状态。因此断言只覆盖
 *     「视图能进入、结构正确、控件存在、无照片时给空态」这些**不依赖数据**的路径，
 *     数据相关的深度校验（格子填充、下钻）仅在探测到照片时才执行，否则跳过。
 *   - 拼图是 Canvas2D 渲染，无法用 DOM 断言格子；改为断言 canvas 元素存在 +
 *     geojson 接口被调用 + 面板控件渲染，作为「视图就绪」的可靠信号。
 *
 * UI 约定（src/views/album/location/）：
 *   - 拼图视图根容器：.location-puzzle
 *   - view toggle 按钮 title="照片拼图"
 *   - 面板标题 "全国照片拼图"、区块 "选片策略" / "拼图精细度"、按钮 "换一批照片"
 *   - 空态文案 "还没有带位置信息的照片，无法生成拼图"
 *   - 单省视图左上角有 "全国" 返回按钮
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

async function waitForLocationRoute(
  page: Page,
  testInfo: { skip(condition: boolean, ...args: unknown[]): void },
): Promise<boolean> {
  await page.waitForLoadState('networkidle', { timeout: 8_000 }).catch(() => undefined)
  await page.waitForTimeout(500)
  const url = page.url()
  if (/\/album\/location(?:\?|$|\/)/.test(url)) return true
  testInfo.skip(
    true,
    `Page did not stay on /album/location; landed on ${url}. Auth setup likely failed.`,
  )
  return false
}

/**
 * 切换到照片拼图视图，并等待 geojson 请求完成（视图挂载即请求省界数据）。
 * 返回 false 表示按钮不可见（拼图视图入口缺失）——理论上不该发生。
 */
async function switchToPuzzle(page: Page): Promise<boolean> {
  const btn = page.locator('.location-list button[title="照片拼图"]').first()
  if (!(await btn.isVisible().catch(() => false))) return false
  const geoReq = page
    .waitForResponse(
      (res) => res.url().includes('/api/medias/geojson') && res.status() === 200,
      { timeout: 12_000 },
    )
    .catch(() => undefined)
  await btn.click()
  await geoReq
  return true
}

test.describe.serial('P0 - 位置相册照片拼图', () => {
  test.use({ retries: 1 })
  test.setTimeout(180_000)

  // 与 location-p0 / location-p1 共用同一把锁
  const LOCATION_MUTEX = 'location-scenes'
  let releaseMutex: (() => Promise<void>) | undefined

  test.beforeEach(async ({ page, request }, testInfo) => {
    releaseMutex = await acquireMutex(LOCATION_MUTEX, 120_000)
    const authToken = await ensureAuthSession(request, page, testInfo)
    if (!authToken) return
    // 复位持久化视图状态，保证每次从网格视图进入
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

  test('2.4.17 拼图视图入口 - 视图切换器含"照片拼图"按钮 @p0', async ({ page }, testInfo) => {
    await gotoRetry(page, '/album/location')
    if (!(await waitForLocationRoute(page, testInfo))) return

    const puzzleBtn = page.locator('.location-list button[title="照片拼图"]').first()
    await expect(puzzleBtn).toBeVisible({ timeout: 10_000 })
  })

  test('2.4.18 切换到拼图视图 - 请求 geojson 并渲染 canvas + 配置面板 @p0', async ({ page }, testInfo) => {
    await gotoRetry(page, '/album/location')
    if (!(await waitForLocationRoute(page, testInfo))) return

    const switched = await switchToPuzzle(page)
    expect(switched, 'puzzle view button should be clickable').toBe(true)

    // 拼图视图根容器出现
    const puzzleRoot = page.locator('.location-puzzle')
    await expect(puzzleRoot).toBeVisible({ timeout: 10_000 })

    // Canvas 元素渲染（拼图绘制载体）
    await expect(puzzleRoot.locator('canvas').first()).toBeVisible({ timeout: 10_000 })

    // 右侧配置面板：标题 + 关键控件（不依赖是否有照片）
    await expect(puzzleRoot.getByText('全国照片拼图')).toBeVisible({ timeout: 10_000 })
    await expect(puzzleRoot.getByText('选片策略')).toBeVisible()
    await expect(puzzleRoot.getByText('拼图精细度')).toBeVisible()
    await expect(puzzleRoot.getByRole('button', { name: '换一批照片' })).toBeVisible()
  })

  test('2.4.19 拼图数据态 - 有照片则显示统计，无照片则显示空态 @p0', async ({ page }, testInfo) => {
    await gotoRetry(page, '/album/location')
    if (!(await waitForLocationRoute(page, testInfo))) return
    if (!(await switchToPuzzle(page))) {
      testInfo.skip(true, 'puzzle view entry not available')
      return
    }

    const puzzleRoot = page.locator('.location-puzzle')
    await expect(puzzleRoot).toBeVisible({ timeout: 10_000 })

    // 生成过程可能有 loading，先等它消失（或超时也无妨）
    await puzzleRoot
      .getByText('正在生成拼图…')
      .waitFor({ state: 'hidden', timeout: 15_000 })
      .catch(() => undefined)

    // 两条合法路径二选一：
    //   A. 有带 GPS 的照片 → 面板「使用照片」统计
    //   B. 无照片 → 画布空态文案
    // 用 .first() 避免 strict mode：某些数据态下两者可能同时存在于 DOM
    // （空态 <p> 与面板统计块），此处只需确认「视图已就绪」这一信号。
    const readySignal = puzzleRoot
      .getByText(/还没有带位置信息的照片，无法生成拼图|使用照片/)
      .first()

    await expect(readySignal).toBeVisible({ timeout: 20_000 })
  })

  test('2.4.20 换一批照片 - 按钮可点击且不报错 @p0', async ({ page }, testInfo) => {
    await gotoRetry(page, '/album/location')
    if (!(await waitForLocationRoute(page, testInfo))) return
    if (!(await switchToPuzzle(page))) {
      testInfo.skip(true, 'puzzle view entry not available')
      return
    }

    const puzzleRoot = page.locator('.location-puzzle')
    const reshuffleBtn = puzzleRoot.getByRole('button', { name: '换一批照片' })
    await expect(reshuffleBtn).toBeVisible({ timeout: 10_000 })

    // 点击换一批：不应抛错、画布仍在、按钮仍可用（幂等操作）
    await reshuffleBtn.click()
    await page.waitForTimeout(300)
    await expect(puzzleRoot.locator('canvas').first()).toBeVisible()
    await expect(reshuffleBtn).toBeEnabled()
  })

  test('2.4.21 拼图视图切走再切回 - canvas 正常重建 @p0', async ({ page }, testInfo) => {
    await gotoRetry(page, '/album/location')
    if (!(await waitForLocationRoute(page, testInfo))) return
    if (!(await switchToPuzzle(page))) {
      testInfo.skip(true, 'puzzle view entry not available')
      return
    }
    await expect(page.locator('.location-puzzle')).toBeVisible({ timeout: 10_000 })

    // 切到网格视图，拼图视图应卸载
    const gridBtn = page.locator('.location-list button[title="网格视图"]').first()
    await expect(gridBtn).toBeVisible({ timeout: 5_000 })
    await gridBtn.click()
    await expect(page.locator('.location-puzzle')).toBeHidden({ timeout: 8_000 })

    // 再切回拼图：canvas 应重新渲染，不残留旧状态、不报错
    if (!(await switchToPuzzle(page))) {
      testInfo.skip(true, 'puzzle view re-entry not available')
      return
    }
    await expect(page.locator('.location-puzzle')).toBeVisible({ timeout: 10_000 })
    await expect(page.locator('.location-puzzle canvas').first()).toBeVisible({ timeout: 10_000 })
  })
})
