import { test, expect, type Route } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

const cleanupApi = '**/api/toolbox/cleanup**'

function fulfillCleanup(route: Route, photos: unknown[]) {
  return route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ code: 0, message: 'success', data: photos }),
  })
}

test.describe('P1 - 清理相册页面 @toolbox-cleanup', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return
  })

  test('无低分照片时显示空态和处理建议', async ({ page }) => {
    await page.route(cleanupApi, route => fulfillCleanup(route, []))

    await page.goto('/toolbox/cleanup')
    await expect(page).toHaveURL(/\/toolbox\/cleanup/)
    await expect(page.getByRole('heading', { name: '清理相册' })).toBeVisible()
    await expect(page.getByText('暂无照片，请在完成')).toBeVisible({ timeout: 10_000 })
    await expect(page.getByRole('link', { name: '大模型智能分析任务' })).toHaveAttribute('href', '/settings#tasks')
  })

  test('切换排序后以降序重新请求清理照片', async ({ page }) => {
    const requests: string[] = []
    await page.route(cleanupApi, async route => {
      requests.push(route.request().url())
      await fulfillCleanup(route, [])
    })

    await page.goto('/toolbox/cleanup')
    await expect(page.getByText('暂无照片，请在完成')).toBeVisible({ timeout: 10_000 })

    const sort = page.locator('select')
    await expect(sort).toHaveValue('asc')
    await sort.selectOption('desc')
    await expect.poll(() => requests.length).toBeGreaterThanOrEqual(2)
    expect(requests.at(-1)).toContain('sort_by=desc')
    await expect(sort).toHaveValue('desc')
  })

  test('清理照片接口失败时显示错误提示并保持页面可用', async ({ page }) => {
    await page.route(cleanupApi, route => route.fulfill({ status: 500, contentType: 'application/json', body: '{}' }))

    await page.goto('/toolbox/cleanup')
    await expect(page.getByRole('heading', { name: '清理相册' })).toBeVisible()
    await expect(page.getByText('获取照片失败')).toBeVisible({ timeout: 10_000 })
    await expect(page.locator('select')).toBeVisible()
  })
})
