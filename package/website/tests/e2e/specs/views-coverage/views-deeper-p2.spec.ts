import { expect, test, type Page, type Route } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

test.describe.configure({ mode: 'serial' })

const ok = (data: unknown) => ({ code: 0, message: 'success', data })

async function mockTicketApis(page: Page, tickets: (typeof trainTicket)[]) {
  const items = tickets.map(ticket => ({
    type: 'train', id: ticket.id, key: `train:${ticket.id}`,
    title: `${ticket.departure_station} → ${ticket.arrival_station}`, code: ticket.train_code,
    from: ticket.departure_station, to: ticket.arrival_station, date_time: ticket.date_time,
    name: ticket.name, price: ticket.price, distance: ticket.total_mileage,
    duration: ticket.total_running_time, comments: ticket.comments, photo_id: null,
    albums: [], memories: [], candidates: [],
  }))
  await page.route('**/api/ticket-wallet?**', route => route.fulfill({ json: ok({ items, total: items.length }) }))
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
  await expect(page.locator('h1', { hasText: '欢迎回来' })).toBeVisible({ timeout: 10_000 })
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

test.describe('票夹交通统计 / 纪念票面 @views-coverage', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return
  })

  test('更多菜单交通统计 -> 旅行足迹报告显示票据里程和城市数量', async ({ page }) => {
    await mockTicketApis(page, [trainTicket])
    await page.goto('/ticket')
    await expect(page.locator('main article')).toHaveCount(1)
    await page.getByRole('button', { name: '更多票夹操作', exact: true }).click()
    await page.getByRole('button', { name: '交通统计', exact: true }).click()
    await expect(page).toHaveURL(/\/statistics/)
    await expect(page.getByRole('heading', { name: '旅行足迹报告', exact: true })).toBeVisible()
    await expect(page.getByText('年度总里程', { exact: true }).locator('..').locator('..')).toContainText('1,318')
    await expect(page.getByText('点亮城市', { exact: true }).locator('..').locator('..').locator('.text-4xl')).toHaveText('2')
  })

  test('票据详情 -> 纪念票面打开并可切换票面样式', async ({ page }) => {
    await mockTicketApis(page, [trainTicket])
    await page.goto('/ticket')
    await expect(page.locator('main article')).toHaveCount(1)
    await page.locator('main article').getByRole('button').first().click()
    const detail = page.getByRole('dialog', { name: '火车票详情', exact: true })
    await detail.getByRole('button', { name: '更多票据操作', exact: true }).click()
    await detail.getByRole('button', { name: '纪念票面', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: '纪念票面', exact: true })
    await expect(dialog).toBeVisible()
    const style = dialog.getByRole('combobox', { name: '票面样式', exact: true })
    await expect(style).toHaveValue('blue')
    await style.selectOption('red')
    await expect(style).toHaveValue('red')
    await expect(dialog.getByText('G123', { exact: true })).toBeVisible()
  })
})
