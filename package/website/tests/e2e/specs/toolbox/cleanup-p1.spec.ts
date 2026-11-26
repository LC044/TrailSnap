import { test, expect } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

/**
 * REQ-238 工具箱重构后，/toolbox/cleanup 不再直连 /api/toolbox/cleanup 列表接口，
 * 而是与整理/重命名共用 ToolWorkflowPage 的「选择范围 → 设置规则 → 预览并执行」工作流。
 * 旧页面的空态文案、排序下拉和列表接口都不存在了，这里改为验证新页面的范围契约：
 * 默认范围为全部、范围来源可切换、范围核对失败时页面仍可用。
 */

test.describe('P1 - 低质量照片清理工作流 @toolbox-cleanup', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return
  })

  test('默认全部，可在查找前缩小范围', async ({ page }) => {
    await page.goto('/toolbox/cleanup?new=1')
    await expect(page).toHaveURL(/\/toolbox\/cleanup/)
    await expect(page.locator('h1.ts-page-title', { hasText: '低质量照片' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '查找设置' })).toBeVisible()
    await expect(page.getByRole('group', { name: '范围来源' })).toBeVisible()
    await expect(page.getByRole('group', { name: '范围来源' }).getByRole('button', { name: '全部', exact: true })).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByRole('button', { name: /^(预览|查找)$/ })).toBeEnabled()
  })

  test('切换范围来源会更新范围摘要并解锁下一步', async ({ page }) => {
    await page.goto('/toolbox/cleanup?new=1')
    const sources = page.getByRole('group', { name: '范围来源' })

    await sources.getByRole('button', { name: '文件夹' }).click()
    await expect(page.getByRole('button', { name: '选择', exact: true })).toBeVisible()
    await expect(page.getByRole('group', { name: '范围来源' }).getByRole('button', { name: '文件夹', exact: true })).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByRole('button', { name: /^(预览|查找)$/ })).toBeDisabled()

    await sources.getByRole('button', { name: '全部' }).click()
    await expect(page.getByText('你已主动选择全部影像，请特别注意执行前的影响范围。')).toHaveCount(0)
    await expect(page.getByText('你已主动选择全部影像，请特别注意执行前的影响范围。')).toHaveCount(0)
    await expect(page.getByRole('button', { name: /^(预览|查找)$/ })).toBeEnabled()
  })

  test('范围核对失败时显示错误提示并保持页面可用', async ({ page }) => {
    await page.route('**/api/toolbox/scopes/preview**', route => route.fulfill({
      status: 500, contentType: 'application/json', body: '{}',
    }))

    await page.goto('/toolbox/cleanup?new=1')
    await page.getByRole('group', { name: '范围来源' }).getByRole('button', { name: '全部' }).click()
    await page.getByRole('button', { name: '查看', exact: true }).click()

    await expect(page.getByText('范围核对失败，请检查选择并重试')).toBeVisible({ timeout: 10_000 })
    await expect(page.locator('h1.ts-page-title', { hasText: '低质量照片' })).toBeVisible()
    await expect(page.getByRole('group', { name: '范围来源' })).toBeVisible()
  })
})
