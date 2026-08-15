import { expect, test, type Page, type Route } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

test.describe.configure({ mode: 'serial' })

const ok = (data: unknown) => ({ code: 0, message: 'success', data })

async function mockTicketApis(page: Page, tickets: unknown[]) {
  await page.route('**/api/train-ticket**', async (route: Route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ok({ items: tickets, total: tickets.length })) })
      return
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ok({})) })
  })
  await page.route('**/api/flight-ticket**', async (route: Route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ok({ items: [], total: 0 })) })
  })
  await page.route('**/api/railway/stats/batch**', async (route: Route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ok([])) })
  })
}

const trainTicket = {
  id: 'ticket-e2e-1',
  train_code: 'G123',
  departure_station: '北京南',
  arrival_station: '上海虹桥',
  date_time: '2026-07-20 09:30:00',
  carriage: '05',
  seat_num: '12A',
  berth_type: '无',
  price: 553,
  seat_type: '二等座',
  name: '测试用户',
  total_running_time: 300,
  total_mileage: 1318,
  comments: '',
}

test('登录页渲染 LoginCharacters 角色组 @views-coverage', async ({ page }) => {
  // The dev project injects an authenticated storageState globally; this case
  // specifically exercises the public login page, so start without that token.
  await page.addInitScript(() => localStorage.removeItem('user_token'))
  await page.goto('/login')
  await expect(page.locator('h2', { hasText: '登录 行影集' })).toBeVisible({ timeout: 10_000 })
  const characterCanvas = page.locator('div.relative.w-\\[400px\\].h-\\[400px\\]')
  await expect(characterCanvas).toBeVisible()
  await expect(characterCanvas.locator('div.bg-\\[\\#6366F1\\]')).toBeVisible()
  await expect(characterCanvas.locator('div.bg-\\[\\#F97316\\]')).toBeVisible()
  await expect(characterCanvas.locator('div.bg-\\[\\#FACC15\\]')).toBeVisible()
})

test.describe('LocationTrajectoryView 轨迹视图 @views-coverage', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return
  })

  test('切换轨迹视图 -> 请求时间轴数据并显示空态', async ({ page }) => {
    const timelineCalls: string[] = []
    await page.route('**/api/locations/**', async (route: Route) => {
      const url = route.request().url()
      if (url.includes('/timeline')) timelineCalls.push(url)
      const path = new URL(url).pathname
      const data = path.endsWith('/years')
        ? []
        : path.endsWith('/statistics')
          ? { province_count: 0, city_count: 0, scene_count: 0, photo_count: 0 }
          : path.endsWith('/timeline')
            ? { nodes: [] }
            : []
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ok(data)) })
    })
    await page.goto('/album/location')
    await page.locator('button[title="轨迹视图"]').click()
    await expect(page.locator('#trajectory-map')).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText('暂无轨迹数据')).toBeVisible({ timeout: 10_000 })
    await expect.poll(() => timelineCalls.length, { timeout: 5_000 }).toBeGreaterThan(0)
  })
})

test.describe('TicketCityStatsModal / TicketPaperModal 车票弹窗 @views-coverage', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return
  })

  test('足迹统计卡 -> TicketCityStatsModal 显示城市列表', async ({ page }) => {
    await mockTicketApis(page, [trainTicket])
    await page.goto('/ticket')
    await expect(page.getByText('点击查看足迹地图')).toBeVisible({ timeout: 15_000 })
    await page.getByText('点击查看足迹地图').click()
    await expect(page.getByRole('heading', { name: '足迹地图' })).toBeVisible({ timeout: 5_000 })
    const cityModal = page.getByText('足迹地图').locator('xpath=ancestor::div[contains(@class,"fixed")][1]')
    await expect(cityModal).toBeVisible()
    await expect(cityModal.getByText('北京南', { exact: true })).toBeVisible()
    await expect(cityModal.getByText('上海虹桥', { exact: true })).toBeVisible()
  })

  test('车票卡片纸票按钮 -> TicketPaperModal 打开并可切换票面样式', async ({ page }) => {
    await mockTicketApis(page, [trainTicket])
    await page.goto('/ticket')
    await expect(page.locator('button[title="查看仿真纸质车票"]')).toBeVisible({ timeout: 15_000 })
    await page.locator('button[title="查看仿真纸质车票"]').click()
    const dialog = page.locator('.paper-ticket-dialog')
    await expect(dialog).toBeVisible({ timeout: 5_000 })
    await expect(dialog.getByText('仿真纸质车票')).toBeVisible()
    await dialog.getByText('红票').click()
    await expect(dialog.getByText('红票')).toBeVisible()
  })
})



