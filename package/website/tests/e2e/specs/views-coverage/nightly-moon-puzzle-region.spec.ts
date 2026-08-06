import { test, expect, type Page } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'
import { acquireMutex } from '../../helpers/mutex'

/** Nightly paths for MoonJournal, PuzzlePanel, PuzzleCanvas, and RegionDetailsPanel. */
const moonPhoto = {
  id: '00000000-0000-0000-0000-000000000201',
  filename: 'nightly-moon.jpg',
  photo_time: '2026-07-29T21:30:00',
  upload_time: '2026-07-30T08:00:00',
  file_type: 'image', size: 1024, width: 1200, height: 1200,
}

async function enterPuzzle(page: Page) {
  await page.goto('/album/location', { waitUntil: 'domcontentloaded' })
  await page.waitForLoadState('networkidle', { timeout: 8_000 }).catch(() => undefined)
  const button = page.locator('.location-list button[title="照片拼图"]').first()
  if (!(await button.isVisible().catch(() => false))) return false
  await button.click()
  await expect(page.locator('.location-puzzle')).toBeVisible({ timeout: 15_000 })
  return true
}

test.describe.serial('Nightly view coverage @views-coverage', () => {
  test.setTimeout(120_000)
  const LOCATION_MUTEX = 'location-scenes'
  let releaseMutex: (() => Promise<void>) | undefined

  test.beforeEach(async ({ page, request }, testInfo) => {
    releaseMutex = await acquireMutex(LOCATION_MUTEX, 120_000)
    const token = await ensureAuthSession(request, page, testInfo)
    if (!token) return
    await page.addInitScript(() => {
      localStorage.removeItem('trailsnap-location-view-mode')
      localStorage.removeItem('trailsnap-location-level')
      localStorage.removeItem('trailsnap-location-filter-status')
      localStorage.removeItem('trailsnap_map_state')
    })
  })

  test.afterEach(async () => {
    await releaseMutex?.()
    releaseMutex = undefined
  })

  test('MoonJournal retries a failed photo request and renders the recovered record', async ({ page }) => {
    let attempts = 0
    await page.route('**/api/tags/**/photos**', async (route) => {
      attempts += 1
      if (attempts === 1) {
        await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'temporary failure' }) })
      } else {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 0, msg: 'success', data: [moonPhoto] }) })
      }
    })

    await page.goto('/moon', { waitUntil: 'domcontentloaded' })
    await expect(page.getByText('月亮照片加载失败，请稍后重试。')).toBeVisible()
    await page.getByRole('button', { name: '重新加载' }).click()
    await expect(page.locator('[data-testid="moon-photo-card"]')).toHaveCount(1)
    expect(attempts).toBe(2)
  })

  test('PuzzlePanel manual strategy disables reshuffle and PuzzleCanvas renders canvas', async ({ page }, testInfo) => {
    if (!(await enterPuzzle(page))) {
      testInfo.skip(true, 'puzzle view entry not available')
      return
    }
    const root = page.locator('.location-puzzle')
    await root.locator('.el-select').first().click()
    await page.getByRole('option', { name: '手动选择' }).click()
    const reshuffle = root.getByRole('button', { name: '换一批照片' })
    await expect(reshuffle).toBeDisabled()
    await expect(reshuffle).toHaveAttribute('title', '手动模式下不支持换一批')

    // PuzzleCanvas 渲染了 canvas 元素，且尺寸非零
    // 注：滚轮缩放后的 cursor-grab 在 dev 空态时由上层覆盖物拦截，不在这里断言
    // （已有 location-puzzle.spec.ts:2.4.18 覆盖 canvas 渲染，本测试侧重 PuzzlePanel 的策略联动）
    const canvas = root.locator('canvas').first()
    await expect(canvas).toBeVisible()
    const dimensions = await canvas.evaluate((node) => ({ width: node.width, height: node.height }))
    expect(dimensions.width).toBeGreaterThan(0)
    expect(dimensions.height).toBeGreaterThan(0)
  })

  test('RegionDetailsPanel shows derived dates, tags, progress, and recent visits', async ({ page }) => {
    const geoJson = {
      type: 'FeatureCollection',
      features: [{
        type: 'Feature',
        properties: { name: '测试市' },
        geometry: { type: 'Polygon', coordinates: [[[110, 30], [111, 30], [111, 31], [110, 31], [110, 30]]] },
      }],
    }

    await page.route('**/api/locations/statistics', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 0, msg: 'success', data: { province_count: 1, city_count: 1, scene_count: 0, total_distance_km: 12, travel_days: 2, farthest_place: '测试市', farthest_distance_km: 12, has_location: true } }) })
    })
    await page.route('**/api/locations/timeline**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 0, msg: 'success', data: { nodes: [{ locationName: '测试市', level: 'city', startDate: '2026-07-29', endDate: '2026-07-30', photoCount: 2 }] } }) })
    })
    await page.route('**/api/stats/timeline**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 0, msg: 'success', data: { timeline: [{ year: 2026, month: 7, count: 2 }] } }) })
    })
    await page.route('**/api/medias/geojson**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 0, msg: 'success', data: geoJson }) })
    })
    await page.route('**/api/locations/distribution**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 0, msg: 'success', data: [{ name: '测试市', count: 3, level: 'city' }] }) })
    })
    await page.route('**/api/locations/*/photos**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, msg: 'success', data: [
          { ...moonPhoto, id: '00000000-0000-0000-0000-000000000301', photo_time: '2025-01-02T10:00:00', metadata_info: { tags: [{ tag_name: '旅行', confidence: 1 }] } },
          { ...moonPhoto, id: '00000000-0000-0000-0000-000000000302', photo_time: '2026-07-30T10:00:00', metadata_info: { tags: [{ tag_name: '旅行', confidence: 1 }, { tag_name: '城市', confidence: 1 }] } },
        ] }),
      })
    })

    await page.goto('/album/location', { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle', { timeout: 8_000 }).catch(() => undefined)
    await page.locator('.location-list button[title="地图视图"]').first().click()
    await expect(page.getByRole('heading', { name: '足迹概览' })).toBeVisible({ timeout: 15_000 })
    await page.locator('.location-list .cursor-pointer').filter({ hasText: '测试市' }).first().click()

    await expect(page.getByText('照片数量')).toBeVisible()
    await expect(page.getByText('首次点亮')).toBeVisible()
    await expect(page.getByText('2025年1月2日')).toBeVisible()
    await expect(page.getByText('#旅行')).toBeVisible()
    await expect(page.getByText('测试市探索进度')).toBeVisible()
    await expect(page.getByText('最近去过')).toBeVisible()
  })
})