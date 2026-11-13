import { expect, test } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

test.describe('P1 - 照片与工具箱视图合同', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return
  })

  test('PhotosPage 可展开并关闭筛选面板', async ({ page }) => {
    await page.goto('/photos')

    // 面板内「高级筛选」按钮的 accessible name 也含「筛选」，需用精确名称定位开关按钮。
    const filterButton = page.locator('main').getByRole('button', { name: '筛选照片', exact: true })
    await expect(filterButton).toBeVisible({ timeout: 15_000 })
    await filterButton.click()
    // 筛选面板重构后主分组为媒体类型/拍摄年份/地点/人物/类别，
    // 来源与相机信息收进「高级筛选」折叠区。
    const mediaTypeGroup = page.locator('main').getByRole('heading', { name: '媒体类型' })
    await expect(mediaTypeGroup).toBeVisible()
    await expect(page.locator('main').getByRole('heading', { name: '拍摄年份' })).toBeVisible()

    await filterButton.click()
    await expect(mediaTypeGroup).toBeHidden()
  })

  test('ToolboxPage 的低质量照片卡片导航到清理页', async ({ page }) => {
    await page.goto('/toolbox')
    await expect(page.locator('h1.ts-page-title', { hasText: '工具箱' })).toBeVisible()

    // 首页卡片改名「低质量照片」，并统一指向 kind=cleanup 的工作流页。
    await page.getByRole('link', { name: /低质量照片/ }).first().click()
    await expect(page).toHaveURL(/\/toolbox\/cleanup$/)
    await expect(page.locator('h1.ts-page-title', { hasText: '低质量照片' })).toBeVisible()
  })

  test('CleanupPage 明确选择范围后才允许查找候选', async ({ page }) => {
    await page.goto('/toolbox/cleanup')
    await expect(page.locator('h1.ts-page-title', { hasText: '低质量照片' })).toBeVisible()

    // 旧页的 sort_by=asc/desc 请求随直连列表页移除，候选改由预览计划生成。
    const next = page.getByRole('button', { name: /^(查看效果|查找候选照片)$/ })
    await expect(next).toBeDisabled()
    await page.getByRole('group', { name: '范围来源' }).getByRole('button', { name: '全部' }).click()
    await expect(next).toBeEnabled()
    await expect(page.getByText('你已主动选择全部影像，请特别注意执行前的影响范围。')).toBeVisible()
  })

  test('OrganizePage 使用范围与规则分离的工作流骨架', async ({ page }) => {
    await page.goto('/toolbox/organize')
    await expect(page.locator('h1.ts-page-title', { hasText: '影像整理' })).toBeVisible()
    await expect(page.getByRole('group', { name: '范围来源' })).toBeVisible()
    // 规则与范围同屏，无需点击下一步。
    await expect(page.getByRole('heading', { name: '怎样整理？' })).toBeVisible()
    await expect(page.getByRole('button', { name: /^(查看效果|查找候选照片)$/ })).toBeDisabled()
  })

  test('修正拍摄信息页同屏显示范围和设置', async ({ page }) => {
    await page.goto('/toolbox/time-from-filename')
    await expect(page.locator('h1.ts-page-title', { hasText: '修正拍摄信息' })).toBeVisible()
    await expect(page.getByRole('group', { name: '范围来源' })).toBeVisible()
    await expect(page.getByText('时间处理', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: /^(查看效果|查找候选照片)$/ })).toBeDisabled()
    await expect(page.getByRole('button', { name: '开始修改拍摄信息' })).toHaveCount(0)
  })
})


