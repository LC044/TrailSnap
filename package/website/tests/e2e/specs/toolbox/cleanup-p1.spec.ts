import { test, expect } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

/**
 * REQ-238 工具箱重构后，/toolbox/cleanup 不再直连 /api/toolbox/cleanup 列表接口，
 * 而是与整理/重命名共用 ToolWorkflowPage 的「选择范围 → 设置规则 → 预览并执行」工作流。
 * 旧页面的空态文案、排序下拉和列表接口都不存在了，这里改为验证新页面的范围契约：
 * 默认不预选全库、范围来源可切换、范围核对失败时页面仍可用。
 */

test.describe('P1 - 低质量照片清理工作流 @toolbox-cleanup', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return
  })

  test('默认不预选全库，需显式选择范围后才能设置规则', async ({ page }) => {
    await page.goto('/toolbox/cleanup')
    await expect(page).toHaveURL(/\/toolbox\/cleanup/)
    await expect(page.locator('h1.ts-page-title', { hasText: '低质量照片' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '找出候选，由你决定保留' })).toBeVisible()
    await expect(page.getByRole('group', { name: '范围来源' })).toBeVisible()
    await expect(page.getByRole('group', { name: '范围来源' }).getByRole('button', { name: '相册' }))
      .toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByRole('group', { name: '范围来源' }).getByRole('button', { name: '相册', exact: true })).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByRole('button', { name: /^(查看效果|查找候选照片)$/ })).toBeDisabled()
  })

  test('切换范围来源会更新范围摘要并解锁下一步', async ({ page }) => {
    await page.goto('/toolbox/cleanup')
    const sources = page.getByRole('group', { name: '范围来源' })

    await sources.getByRole('button', { name: '文件夹' }).click()
    await expect(page.getByRole('button', { name: '选择文件夹' })).toBeVisible()
    await expect(page.getByRole('group', { name: '范围来源' }).getByRole('button', { name: '文件夹', exact: true })).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByRole('button', { name: /^(查看效果|查找候选照片)$/ })).toBeDisabled()

    await sources.getByRole('button', { name: '全部' }).click()
    await expect(page.getByText('你已主动选择全部影像，请特别注意执行前的影响范围。')).toBeVisible()
    await expect(page.getByText('你已主动选择全部影像，请特别注意执行前的影响范围。')).toBeVisible()
    await expect(page.getByRole('button', { name: /^(查看效果|查找候选照片)$/ })).toBeEnabled()
  })

  test('范围核对失败时显示错误提示并保持页面可用', async ({ page }) => {
    await page.route('**/api/toolbox/scopes/preview**', route => route.fulfill({
      status: 500, contentType: 'application/json', body: '{}',
    }))

    await page.goto('/toolbox/cleanup')
    await page.getByRole('group', { name: '范围来源' }).getByRole('button', { name: '全部' }).click()
    await page.getByRole('button', { name: '查看范围内影像' }).click()

    await expect(page.getByText('范围核对失败，请检查选择并重试')).toBeVisible({ timeout: 10_000 })
    await expect(page.locator('h1.ts-page-title', { hasText: '低质量照片' })).toBeVisible()
    await expect(page.getByRole('group', { name: '范围来源' })).toBeVisible()
  })
})
