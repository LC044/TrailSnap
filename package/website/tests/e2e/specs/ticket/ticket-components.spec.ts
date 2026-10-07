import { test, expect, type Page } from '@playwright/test'
import { ensureAuthSession } from '../../helpers/auth'

test.describe.configure({ mode: 'serial' })
const summary = (type: 'train' | 'flight', id: string, title: string, code: string) => ({
  type, id, key: `${type}:${id}`, title, code, from: '上海', to: '成都', date_time: '2026-08-09T10:30:00',
  price: 680, name: '测试乘客', distance: 1700, duration: 180, comments: '', photo_id: null,
  albums: [], memories: [], candidates: [],
})
async function mockWallet(page: Page, items: ReturnType<typeof summary>[] = []) {
  await page.route('**/api/ticket-wallet?**', route => route.fulfill({ json: { code: 200, msg: 'success', data: { items, total: items.length } } }))
  await page.route('**/api/railway/stats/batch', route => route.fulfill({ json: { code: 200, msg: 'success', data: [] } }))
}
async function gotoTicketPage(page: Page) {
  await page.goto('/ticket')
  await expect(page.getByRole('heading', { name: '票夹', exact: true })).toBeVisible()
}

test.describe('P1 - 票夹组件 @ticket-components', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return
  })
  test('新增类型选择器只展示支持的火车票和机票', async ({ page }) => {
    await mockWallet(page); await gotoTicketPage(page)
    await page.locator('main header').getByRole('button', { name: '新增票据', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: '新增票据', exact: true })
    await expect(dialog.getByRole('button', { name: '火车票', exact: true })).toBeVisible()
    await expect(dialog.getByRole('button', { name: '机票', exact: true })).toBeVisible()
    await expect(dialog.getByRole('button', { name: '电影票', exact: true })).toHaveCount(0)
  })
  test('选择火车票后关闭类型选择器并打开编辑表单', async ({ page }) => {
    await mockWallet(page); await gotoTicketPage(page)
    await page.locator('main header').getByRole('button', { name: '新增票据', exact: true }).click()
    const selector = page.getByRole('dialog', { name: '新增票据', exact: true })
    await selector.getByRole('button', { name: '火车票', exact: true }).click()
    await expect(selector).toBeHidden()
    await expect(page.getByRole('dialog', { name: '新增火车票', exact: true }).getByRole('textbox', { name: '车次', exact: true })).toBeVisible()
  })
  test('更多菜单打开导出，空票夹不能导出纪念PNG', async ({ page }) => {
    await mockWallet(page); await gotoTicketPage(page)
    await page.getByRole('button', { name: '更多票夹操作', exact: true }).click()
    await page.getByRole('button', { name: '导出票据', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: '导出票据', exact: true })
    await expect(dialog.getByRole('button', { name: '票据备份（JSON）', exact: true })).toBeVisible()
    await expect(dialog.getByRole('button', { name: '表格数据（CSV）', exact: true })).toBeVisible()
    await expect(dialog.getByRole('button', { name: '火车票纪念票面（PNG）', exact: true })).toBeDisabled()
  })
  test('搜索实际筛掉不匹配票据', async ({ page }) => {
    await mockWallet(page, [summary('train', 'one', '北京 → 上海', 'G1234'), summary('flight', 'two', '上海 → 成都', 'MU1234')])
    await gotoTicketPage(page); await expect(page.locator('main article')).toHaveCount(2)
    await page.getByRole('button', { name: '搜索票据', exact: true }).click()
    await page.getByRole('searchbox', { name: '搜索票据', exact: true }).fill('北京')
    await expect(page.locator('main article')).toHaveCount(1)
    await expect(page.locator('main article')).toContainText('G1234')
  })
  test('类型筛选应用后只显示机票', async ({ page }) => {
    await mockWallet(page, [summary('train', 'one', '北京 → 上海', 'G1234'), summary('flight', 'two', '上海 → 成都', 'MU1234')])
    await gotoTicketPage(page); await expect(page.locator('main article')).toHaveCount(2)
    await page.getByRole('button', { name: /^筛选/ }).click()
    const dialog = page.getByRole('dialog', { name: '筛选与排序', exact: true })
    await dialog.getByRole('combobox', { name: '类型', exact: true }).selectOption('flight')
    await dialog.getByRole('button', { name: '应用', exact: true }).click()
    await expect(page.locator('main article')).toHaveCount(1)
    await expect(page.locator('main article')).toContainText('MU1234')
  })
  test('编辑机票提交真实PUT，刷新后的卡片显示新航班号', async ({ page }) => {
    const flight = { id: 'flight-ux-regression', flight_code: 'MU2393', departure_city: '上海', arrival_city: '成都', date_time: '2026-08-09T10:30:00', price: 680, name: '测试乘客', total_running_time: 180, total_mileage: 1700, comments: '' }
    const item = summary('flight', flight.id, '上海 → 成都', flight.flight_code)
    await mockWallet(page, [item]); await gotoTicketPage(page)
    await page.locator('main article').getByRole('button', { name: /的更多操作$/ }).click()
    await page.getByRole('button', { name: '编辑', exact: true }).click()
    const editor = page.getByRole('dialog', { name: '编辑机票', exact: true })
    await expect(editor).toBeVisible()
    let updatedPayload: Record<string, unknown> | null = null
    await page.route('**/api/flight-ticket/flight-ux-regression', async route => {
      expect(route.request().method()).toBe('PUT')
      updatedPayload = route.request().postDataJSON()
      item.code = String(updatedPayload!.flight_code)
      await route.fulfill({ json: { code: 200, msg: 'success', data: { ...flight, ...updatedPayload } } })
    })
    await editor.getByRole('textbox', { name: '航班号', exact: true }).fill('MU2393A')
    await editor.getByRole('button', { name: '保存票据', exact: true }).click()
    await expect.poll(() => updatedPayload?.flight_code).toBe('MU2393A')
    await expect(editor).toBeHidden()
    await expect(page.locator('main article')).toContainText('MU2393A')
    await expect(page.locator('.el-message', { hasText: '票据已保存' }).last()).toBeVisible()
  })
})
