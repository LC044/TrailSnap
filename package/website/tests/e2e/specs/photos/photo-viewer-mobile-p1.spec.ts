import { expect, test, type Locator, type Page } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'
import { requirePhotos } from '../../helpers/data-probe'

test.describe('P1 - 移动端照片查看器与更多导航', () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true })

  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo))) return
  })

  async function openFirstPhoto(page: Page) {
    await page.goto('/photos')
    // Click the image itself. A generic `.group.cursor-pointer` also matches the
    // date-level selection header and would enter bulk selection mode instead.
    const photo = page.locator('.day-block img[alt]').first()
    await expect(photo).toBeVisible({ timeout: 20_000 })
    await photo.click()
    const media = page.getByTestId('photo-lightbox-media')
    await expect(media).toBeVisible({ timeout: 10_000 })
    return media
  }

  async function swipe(media: Locator, fromX: number, toX: number) {
    const box = await media.boundingBox()
    expect(box).not.toBeNull()
    const y = box!.y + box!.height / 2
    await media.dispatchEvent('touchstart', {
      touches: [{ identifier: 1, clientX: fromX, clientY: y }],
      changedTouches: [{ identifier: 1, clientX: fromX, clientY: y }],
    })
    await media.dispatchEvent('touchmove', {
      touches: [{ identifier: 1, clientX: toX, clientY: y }],
      changedTouches: [{ identifier: 1, clientX: toX, clientY: y }],
    })
    await media.dispatchEvent('touchend', {
      touches: [],
      changedTouches: [{ identifier: 1, clientX: toX, clientY: y }],
    })
  }

  test('左右滑动切换照片，点击照片切换工具栏显隐', async ({ page, request }, testInfo) => {
    const probe = await requirePhotos(request, testInfo, 2, 20)
    if (!probe.ok) return
    const media = await openFirstPhoto(page)
    const toolbar = page.getByTestId('photo-lightbox-toolbar')
    await expect(toolbar).toBeVisible()

    const image = media.locator('img').first()
    const firstSrc = await image.getAttribute('src')
    await swipe(media, 320, 70)
    await expect.poll(() => image.getAttribute('src')).not.toBe(firstSrc)

    await swipe(media, 70, 320)
    await expect.poll(() => image.getAttribute('src')).toBe(firstSrc)

    // Let the synthetic click generated after touchend be suppressed; the next
    // deliberate tap should toggle controls.
    await page.waitForTimeout(400)
    await media.click({ position: { x: 195, y: 420 } })
    await expect(toolbar).toBeHidden()
    await media.click({ position: { x: 195, y: 420 } })
    await expect(toolbar).toBeVisible()
  })

  test('更多导航可显式关闭且长内容限制在视口内滚动', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: '更多' }).click()

    const drawer = page.locator('.more-sheet')
    await expect(drawer).toBeVisible()
    const drawerBox = await drawer.boundingBox()
    expect(drawerBox).not.toBeNull()
    expect(drawerBox!.height).toBeLessThanOrEqual(844 * 0.85 + 2)
    await expect(drawer.locator('.el-drawer__body')).toHaveCSS('overflow-y', 'auto')

    await page.getByRole('button', { name: '关闭更多导航' }).click()
    await expect(drawer).toBeHidden()
  })
})
