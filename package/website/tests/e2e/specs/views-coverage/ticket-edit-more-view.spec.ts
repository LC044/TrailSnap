import { expect, test, type Locator, type Page, type Route } from '@playwright/test'

/**
 * Nightly view coverage for `views/More.vue` — the ticket editor page that is
 * reachable at `/toolbox/ticket-edit`.
 *
 * The 2026-10-28 nightly gap scan mapped every routed view to the Playwright
 * specs that reach it.  `More.vue` was the single routed view with no spec at
 * all, so this file closes that hole.
 *
 * The page is a purely client-side ticket generator: it renders a form, swaps
 * between the "座位号" and "铺位号" fields depending on whether the chosen
 * seat type is a sleeper berth, and mirrors the form into a live preview.
 */

const response = (data: unknown) => ({ code: 0, message: 'success', data })

async function useFakeSession(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('user_token', 'fake-e2e-token')
    localStorage.setItem('username', 'e2e-mock')
    localStorage.setItem(
      'user_info',
      JSON.stringify({ id: 'u-e2e', username: 'e2e-mock', is_active: true, is_superuser: true }),
    )
  })
  await page.route('**/api/auth/me**', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 'u-e2e', username: 'e2e-mock', is_active: true, is_superuser: true }),
    })
  })
}

/** The `.form-group` block whose label text is exactly `label`. */
function field(page: Page, label: string): Locator {
  return page.locator('div.form-group').filter({ has: page.locator(`label:text-is("${label}")`) })
}

async function openEditor(page: Page) {
  await useFakeSession(page)
  await page.goto('/toolbox/ticket-edit')
  await expect(page.getByRole('heading', { name: '车票信息编辑', level: 1 })).toBeVisible({
    timeout: 10_000,
  })
}

test.describe('Nightly view coverage — ticket editor page @views-coverage', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test('More 渲染车票编辑表单与实时预览', async ({ page }) => {
    await openEditor(page)

    await expect(page.getByRole('heading', { name: '实时预览' })).toBeVisible()
    await expect(field(page, '出发站').locator('input')).toBeVisible()
    await expect(field(page, '到达站').locator('input')).toBeVisible()
    await expect(field(page, '车次').locator('input')).toBeVisible()
    await expect(field(page, '乘客姓名').locator('input')).toBeVisible()
    await expect(page.getByRole('button', { name: '保存火车票为图片' })).toBeVisible()
  })

  test('More 默认使用座位号字段且不显示铺位类型', async ({ page }) => {
    await openEditor(page)

    await expect(field(page, '座位号').locator('input')).toBeVisible()
    await expect(field(page, '铺位类型')).toHaveCount(0)
    // The form model starts empty; 一等座 is simply the first offered option.
    await expect(
      field(page, '座位类型').locator('select').locator('option').first(),
    ).toHaveText('一等座')
  })

  test('More 选择卧铺后显示铺位类型并把座位号切换为铺位号', async ({ page }) => {
    await openEditor(page)

    await field(page, '座位类型').locator('select').selectOption('硬卧')

    await expect(field(page, '铺位类型').locator('select')).toBeVisible()
    await expect(field(page, '铺位号').locator('input')).toBeVisible()
    await expect(field(page, '座位号')).toHaveCount(0)

    await expect(field(page, '铺位类型').locator('option')).toHaveText(['选择铺位', '上铺', '中铺', '下铺'])
  })

  test('More 从卧铺切回普通座时隐藏铺位类型', async ({ page }) => {
    await openEditor(page)

    const seatType = field(page, '座位类型').locator('select')
    await seatType.selectOption('硬卧')
    await expect(field(page, '铺位类型').locator('select')).toBeVisible()

    await seatType.selectOption('二等座')

    await expect(field(page, '铺位类型')).toHaveCount(0)
    await expect(field(page, '座位号').locator('input')).toBeVisible()
  })

  test('More 实时预览跟随表单填写更新', async ({ page }) => {
    await openEditor(page)

    await field(page, '出发站').locator('input').fill('北京南')
    await field(page, '车次').locator('input').fill('G1234')
    await field(page, '乘客姓名').locator('input').fill('张三')

    // The typed values only appear as text inside the live ticket preview
    // (the form fields hold them as input values).
    await expect(page.getByText('北京南').first()).toBeVisible()
    await expect(page.getByText('G1234').first()).toBeVisible()
    await expect(page.getByText('张三').first()).toBeVisible()
  })
})
