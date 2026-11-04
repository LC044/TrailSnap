import { expect, test, type Page, type Route } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

/**
 * Nightly view coverage —— ticket statistics view.
 *
 * Covers the three 2026-11-04 frontend blind spots:
 * - StatisticsChart
 * - TicketRouteExplorer
 * - TicketStatisticsFilters
 */

const TICKET = {
  key: 'train:nightly-stat-1',
  id: 'nightly-stat-1',
  type: 'train',
  title: '夜间统计',
  code: 'G1',
  from: '北京南',
  to: '上海虹桥',
  date_time: '2026-11-01T08:00:00',
  price: 553,
  name: '张三',
  photo_id: null,
  distance: 1318,
  duration: 300,
  comments: '',
  albums: [],
  memories: [],
  candidates: [],
}

function ok(data: unknown) {
  return {
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ code: 0, msg: 'success', data }),
  }
}

async function stubStatisticsPage(page: Page) {
  await page.route('**/api/ticket-wallet?**', (route: Route) =>
    route.fulfill(ok({ items: [TICKET], total: 1 })),
  )
  await page.route('**/api/railway/stats/batch', (route: Route) =>
    route.fulfill(
      ok([
        {
          id: 'nightly-stat-1',
          distance_km: 1318,
          duration_minutes: 300,
        },
      ]),
    ),
  )
  await page.route('**/api/railway/stations**', (route: Route) =>
    route.fulfill(
      ok({
        list: [{ station_name: '北京南', city: '北京' }],
        total: 1,
      }),
    ),
  )
  await page.route('**/api/medias/geojson**', (route: Route) =>
    route.fulfill(
      ok({
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            properties: {
              name: '北京',
              center: [116.407, 39.904],
            },
            geometry: { type: 'Point', coordinates: [116.407, 39.904] },
          },
        ],
      }),
    ),
  )
}

test.describe('Nightly view coverage —— ticket statistics @views-coverage', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo))) return
    await stubStatisticsPage(page)
  })

  test('StatisticsChart renders trend and transport charts', async ({ page }) => {
    await page.goto('/statistics')

    await expect(page.getByRole('heading', { name: '出行概览', exact: true })).toBeVisible({ timeout: 20_000 })
    await expect(page.getByRole('heading', { name: '出行趋势', exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: '交通方式', exact: true })).toBeVisible()
    await expect(page.getByLabel('月度出行趋势')).toBeVisible()
    await expect(page.getByLabel('交通方式分布')).toBeVisible()
  })

  test('TicketRouteExplorer renders map tabs and route summary', async ({ page }) => {
    await page.goto('/statistics')

    await expect(page.getByRole('heading', { name: '出行路线', exact: true })).toBeVisible({ timeout: 20_000 })
    await expect(page.locator('[aria-label="地图视图"]')).toBeVisible()
    await expect(page.getByRole('button', { name: '路线', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: '城市', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: '放大地图', exact: true })).toBeVisible()
    await expect(page.getByText('北京 ↔ 上海')).toBeVisible()
  })

  test('TicketStatisticsFilters exposes filters and refreshes wallet data', async ({ page }) => {
    let walletCalls = 0
    await page.route('**/api/ticket-wallet?**', async (route: Route) => {
      walletCalls += 1
      return route.fulfill(ok({ items: [TICKET], total: 1 }))
    })

    await page.goto('/statistics')
    await expect(page.getByRole('combobox', { name: '时间范围' })).toBeVisible({ timeout: 20_000 })
    await expect(page.getByRole('combobox', { name: '乘车人' })).toBeVisible()
    await expect(page.getByRole('combobox', { name: '交通方式' })).toBeVisible()
    await expect(page.getByRole('button', { name: '刷新统计', exact: true })).toBeVisible()

    const before = walletCalls
    await page.getByRole('button', { name: '刷新统计', exact: true }).click()
    await expect.poll(() => walletCalls).toBeGreaterThan(before)
  })
})
