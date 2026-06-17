import { expect, test } from '@playwright/test'

test.describe('系统 UI 冒烟', () => {
  test('照片页可以看到导入结果并打开详情', async ({ page }) => {
    await page.goto('/photos')

    await expect(page).toHaveURL(/\/photos$/)
    await expect(page.locator('.photo-gallery')).toBeVisible()

    const firstPhoto = page.locator('.photo-gallery img[alt]').first()
    await expect(firstPhoto).toBeVisible({ timeout: 30_000 })
    await firstPhoto.click()

    await expect(page.getByTitle('查看元数据')).toBeVisible()
    await expect(page.getByTitle('下载图片')).toBeVisible()

    await page.getByTitle('查看元数据').click()
    // 侧边栏打开后，由于没直接写“文件路径”几个字，我们可以断言一些通用的标题或者属性是否存在
    await expect(page.getByText('基本信息')).toBeVisible({ timeout: 10_000 })
  })

  test('任务管理页可以打开并展示任务状态', async ({ page }) => {
    await page.goto('/settings#tasks')

    await expect(page).toHaveURL(/\/settings#tasks$/)
    await expect(page.getByRole('heading', { name: '任务管理' })).toBeVisible()
    await expect(page.getByText('快速模式')).toBeVisible()
    await expect(page.getByText('失败').first()).toBeVisible()
  })
})
