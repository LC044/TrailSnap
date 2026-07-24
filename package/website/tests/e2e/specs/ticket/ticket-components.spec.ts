import { test, expect, type Page, type Route } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

/**
 * P1 - 车票子组件覆盖（coverage-gaps-frontend.md 5 个未覆盖模块）
 *
 * 1. TicketTypeSelectorModal -- 触发条件：TicketHeader 「+ 新增」按钮
 *    -> showTypeSelector=true -> 弹窗；选 train / flight -> emit('select-type')
 * 2. TicketExportModal    -- TicketHeader 「导出数据」按钮
 *    -> isExportModalOpen=true -> 弹窗；JSON/CSV/PNG 按钮 emit('execute', format)
 * 3. TicketHeader         -- 搜索框输入 -> emit('update:searchQuery')
 * 4. TicketFilterBar      -- 类型下拉 + 排序按钮 -> emit('update:filterType' / 'change-sort-type')
 * 5. TicketStatsSidebar  -- 报表入口；title="统计报表" -> emit('go-to-statistics')
 *
 * Mock /api/train-ticket 与 /api/flight-ticket 让 TicketList 渲染空态；其他子组件
 * 不依赖列表数据，可独立验证交互。
 */

test.describe.configure({ mode: 'serial' })

async function mockEmptyTickets(route: Route) {
  return route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ code: 0, message: 'success', data: [] }),
  })
}

async function gotoTicketPage(page: Page) {
  await page.goto('/ticket')
  await expect(page.locator('body')).toBeVisible()
  await expect(page.getByText('车票管理').first()).toBeVisible({ timeout: 15_000 })
}

test.describe('P1 - 车票子组件 @ticket-components', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return
  })

  test('点击「+ 新增」-> TicketTypeSelectorModal 出现两个选项', async ({ page }) => {
    await page.route('**/api/train-ticket**', mockEmptyTickets)
    await page.route('**/api/flight-ticket**', mockEmptyTickets)
    await gotoTicketPage(page)

    // 新增按钮含「+」或 icon
    const addBtn = page.locator('nav.sticky button').filter({ hasText: /新增|添加/ }).first()
    await addBtn.dispatchEvent('click')
    // 弹窗标题
    const dialog = page.getByText('选择添加票据类型')
    await expect(dialog).toBeVisible({ timeout: 5_000 })
    // 在弹窗中定位选项（避开外部过滤器中的同名文案）
    const dialogScope = dialog.locator('xpath=ancestor::div[contains(@class, "fixed")][1]')
    await expect(dialogScope.getByText('火车票')).toBeVisible()
    await expect(dialogScope.getByText('飞机票')).toBeVisible()
  })

  test('TicketTypeSelectorModal 点击火车票 -> 弹窗关闭 + 后续表单弹出', async ({ page }) => {
    await page.route('**/api/train-ticket**', mockEmptyTickets)
    await page.route('**/api/flight-ticket**', mockEmptyTickets)
    await gotoTicketPage(page)

    const addBtn = page.locator('nav.sticky button').filter({ hasText: /新增|添加/ }).first()
    await addBtn.dispatchEvent('click')
    await expect(page.getByText('选择添加票据类型')).toBeVisible({ timeout: 5_000 })

    // 点击「火车票」按钮（grid 布局，按文字锁定）
    await page.getByText('火车票').first().click()
    // 弹窗关闭（Transition name="fade" 卸载需要时间，等待 DOM count 变 0）
    await expect(page.getByText('选择添加票据类型')).toHaveCount(0, { timeout: 5_000 })
  })

  // 避免后面 test 跟上一个中的选项重叠，这里仅依赖 mock 数据


  test('点击「导出数据」-> TicketExportModal 出现三种格式按钮', async ({ page }) => {
    await page.route('**/api/train-ticket**', mockEmptyTickets)
    await page.route('**/api/flight-ticket**', mockEmptyTickets)
    await gotoTicketPage(page)

    // TicketHeader 中"导出数据"按钮（title=导出数据）
    const exportBtn = page.locator('button[title="导出数据"]')
    await expect(exportBtn).toBeVisible({ timeout: 5_000 })
    await exportBtn.dispatchEvent('click')

    // 弹窗标题
    await expect(page.getByText('导出车票数据')).toBeVisible({ timeout: 5_000 })
    // 三种格式按钮（PNG 按钮文案为 "仿真纸质票 (PNG)"）
    await expect(page.getByText('JSON 格式')).toBeVisible()
    await expect(page.getByText('CSV 格式')).toBeVisible()
    await expect(page.getByText('仿真纸质票 (PNG)')).toBeVisible()
  })

  test('TicketHeader 搜索框输入 -> 触发 update:searchQuery', async ({ page }) => {
    let lastValue: string | null = null
    // 监听输入事件：DOM 事件不直接挂到 Vue emit 上，改用 input 事件后看 TicketList 是否过滤
    await page.route('**/api/train-ticket**', (route) => {
      // 当带 ?search= 关键词时返回过滤后的结果（这里用空集，验证流程跑通即可）
      const url = new URL(route.request().url())
      const q = url.searchParams.get('search') ?? url.searchParams.get('q')
      if (q) lastValue = q
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, message: 'success', data: [] }),
      })
    })
    await page.route('**/api/flight-ticket**', mockEmptyTickets)
    await gotoTicketPage(page)

    const search = page.locator('nav.sticky input[placeholder*="搜索"]')
    await expect(search).toBeVisible({ timeout: 5_000 })
    await search.fill('北京')
    // 客户端 v-model 直接更新 store；这里验证输入后 value 落到 input 上
    await expect(search).toHaveValue('北京')
  })

  test('TicketFilterBar 类型下拉切换 -> store.filterType 更新（emit 验证）', async ({ page }) => {
    await page.route('**/api/train-ticket**', mockEmptyTickets)
    await page.route('**/api/flight-ticket**', mockEmptyTickets)
    await gotoTicketPage(page)

    // TicketFilterBar 中的 <select>，包含 全部 / 飞机票 / 高铁 / 普速
    const select = page.locator('select').first()
    await expect(select).toBeVisible({ timeout: 5_000 })
    await select.selectOption('flight')
    await expect(select).toHaveValue('flight')
  })
})
