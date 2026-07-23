import { expect, test } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

test.describe('P1 - 照片与工具箱视图合同', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return
  })

  test('PhotosPage 可展开并关闭筛选面板', async ({ page }) => {
    await page.goto('/photos')

    const filterButton = page.locator('main').getByRole('button', { name: '筛选' })
    await expect(filterButton).toBeVisible({ timeout: 15_000 })
    await filterButton.click()
    const sourceGroup = page.locator('main').getByRole('heading', { name: '来源' })
    await expect(sourceGroup).toBeVisible()
    await expect(page.locator('main').getByRole('heading', { name: '类型' })).toBeVisible()

    await filterButton.click()
    await expect(sourceGroup).toBeHidden()
  })

  test('ToolboxPage 的低分清理卡片导航到清理页', async ({ page }) => {
    await page.goto('/toolbox')
    await expect(page.getByRole('heading', { name: '工具箱' })).toBeVisible()

    await page.getByText('低分清理', { exact: true }).click()
    await expect(page).toHaveURL(/\/toolbox\/cleanup$/)
    await expect(page.getByRole('heading', { name: '清理相册' })).toBeVisible()
  })

  test('CleanupPage 切换降序会以 desc 重新请求', async ({ page }) => {
    const requests: string[] = []
    await page.route('**/api/toolbox/cleanup**', async route => {
      requests.push(route.request().url())
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 0, message: 'success', data: [] }) })
    })

    await page.goto('/toolbox/cleanup')
    await expect(page.getByText(/暂无照片/)).toBeVisible({ timeout: 10_000 })
    await page.locator('select').selectOption('desc')

    await expect.poll(() => requests.some(url => url.includes('sort_by=desc'))).toBeTruthy()
  })

  test('OrganizePage 切换位置策略显示位置粒度', async ({ page }) => {
    await page.route('**/api/toolbox/organize/**', async route => {
      const url = route.request().url()
      const data = url.includes('preview') ? { options: [] } : null
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 0, message: 'success', data }) })
    })

    await page.goto('/toolbox/organize')
    await expect(page.getByRole('heading', { name: '图片文件整理' })).toBeVisible()
    await page.getByText('按位置', { exact: true }).click()

    await expect(page.getByText('位置粒度', { exact: true })).toBeVisible()
    await expect(page.getByText('省-市-区', { exact: true })).toBeVisible()
  })

  test('TimeFromFilenamePage 指定时间模式显示日期控件', async ({ page }) => {
    await page.route('**/api/toolbox/time-from-filename/**', async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 0, message: 'success', data: null }) })
    })

    await page.goto('/toolbox/time-from-filename')
    await expect(page.getByRole('heading', { name: '修改图片元数据' })).toBeVisible()
    await page.getByText('指定时间', { exact: true }).click()

    await expect(page.getByPlaceholder('选择日期和时间')).toBeVisible()
    await expect(page.getByRole('button', { name: '开始修改拍摄信息' })).toBeDisabled()
  })
})


