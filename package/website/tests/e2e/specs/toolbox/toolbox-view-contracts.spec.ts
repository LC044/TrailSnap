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
    await expect(page.locator('h1.ts-page-title', { hasText: '照片清理' })).toBeVisible()
  })

  test('CleanupPage 选择全部范围后才解锁下一步（排序列表已移除）', async ({ page }) => {
    await page.goto('/toolbox/cleanup')
    await expect(page.locator('h1.ts-page-title', { hasText: '照片清理' })).toBeVisible()

    // 旧页的 sort_by=asc/desc 请求随直连列表页移除，候选改由预览计划生成。
    const next = page.getByRole('button', { name: '下一步：设置规则' })
    await expect(next).toBeDisabled()
    await page.getByRole('group', { name: '范围来源' }).getByRole('button', { name: '全部' }).click()
    await expect(next).toBeEnabled()
    await expect(page.getByText('全部图库（主动选择）')).toBeVisible()
  })

  test('OrganizePage 使用范围与规则分离的工作流骨架', async ({ page }) => {
    await page.goto('/toolbox/organize')
    await expect(page.locator('h1.ts-page-title', { hasText: '影像整理' })).toBeVisible()
    await expect(page.getByRole('list', { name: '操作步骤' })).toBeVisible()
    // 「按位置 / 位置粒度 / 省-市-区」是旧 OrganizePage 的直连表单，现归入第二步的归档规则编辑器。
    await expect(page.getByRole('group', { name: '范围来源' })).toBeVisible()
    await expect(page.getByRole('button', { name: '下一步：设置规则' })).toBeDisabled()
  })

  test('修正拍摄信息页显示工作流骨架，指定时间入口移到第二步', async ({ page }) => {
    await page.goto('/toolbox/time-from-filename')
    await expect(page.locator('h1.ts-page-title', { hasText: '修正拍摄信息' })).toBeVisible()
    await expect(page.getByRole('list', { name: '操作步骤' })).toBeVisible()
    // 旧页「指定时间」+ 日期控件 +「开始修改拍摄信息」直连表单已被 ToolWorkflowPage 第二步取代。
    await expect(page.getByRole('group', { name: '范围来源' })).toBeVisible()
    await expect(page.getByRole('button', { name: '下一步：设置规则' })).toBeDisabled()
    await expect(page.getByRole('button', { name: '开始修改拍摄信息' })).toHaveCount(0)
  })
})


