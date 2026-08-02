import { test, expect } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

const moonPhotos = [
  {
    id: '00000000-0000-0000-0000-000000000101',
    filename: 'full-moon.jpg',
    photo_time: '2026-07-29T21:30:00',
    upload_time: '2026-07-30T08:00:00',
    file_type: 'image',
    size: 1024,
    width: 1200,
    height: 1200,
  },
  {
    id: '00000000-0000-0000-0000-000000000102',
    filename: 'crescent-moon.jpg',
    photo_time: '2026-08-18T20:15:00',
    upload_time: '2026-08-19T08:00:00',
    file_type: 'image',
    size: 2048,
    width: 1600,
    height: 1200,
  },
]

test.describe('月迹页面 @p0', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo))) return
    await page.route('**/api/tags/%E6%9C%88%E4%BA%AE/photos**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, msg: 'success', data: moonPhotos }),
      })
    })
    await page.route('**/api/medias/**', async (route) => {
      await route.fulfill({ status: 204 })
    })
  })

  test('月相视图展示八阶段导航和照片记录', async ({ page }) => {
    await page.goto('/moon', { waitUntil: 'domcontentloaded' })

    await expect(page.getByRole('heading', { name: '月迹' })).toBeVisible()
    await expect(page.getByRole('navigation', { name: '月迹视图' })).toBeVisible()
    await expect(page.getByRole('button', { name: '满月', exact: true })).toBeVisible()
    await expect(page.locator('[data-testid="moon-photo-card"]')).toHaveCount(2)
  })

  test('移动端可按农历日汇总历次照片', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/moon', { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: '农历日' }).click()

    await expect(page).toHaveURL(/view=calendar/)
    await expect(page.getByRole('heading', { name: '农历日记录' })).toBeVisible()
    await expect(page.getByText('初一', { exact: true })).toBeVisible()
    const lunarDayCount = await page.locator('[data-testid="lunar-day"]').count()
    expect(lunarDayCount).toBe(30)
    await page.getByRole('button', { name: /农历十五/ }).click()
    await expect(page).toHaveURL(/day=15/)

    const emptyLunarDay = page.getByRole('button', { name: /0 张月亮照片/ }).first()
    await emptyLunarDay.click()
    await expect(page.getByText('下一次补拍机会')).toBeVisible()
    await expect(page.getByText(/拍摄后会根据照片时间自动归入农历/)).toBeVisible()
  })

  test('全部视图滚动后仍可切换顶部导航', async ({ page }) => {
    await page.goto('/moon', { waitUntil: 'domcontentloaded' })
    const moonNavigation = page.getByRole('navigation', { name: '月迹视图' })
    await moonNavigation.getByRole('button', { name: '全部', exact: true }).click()
    await expect(page).toHaveURL(/view=all/)

    const scrollContainer = page.locator('#main-content-wrapper > main')
    await scrollContainer.evaluate((element) => { element.scrollTop = 600 })
    await expect(moonNavigation).toBeVisible()
    await moonNavigation.getByRole('button', { name: '月相', exact: true }).click()

    await expect(page).not.toHaveURL(/view=all/)
    await expect(page.getByRole('heading', { name: '月相记录' })).toBeVisible()
  })
})
