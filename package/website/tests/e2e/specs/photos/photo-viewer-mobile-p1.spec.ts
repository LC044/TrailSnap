import { expect, test, type Locator, type Page } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'
import { requirePhotos } from '../../helpers/data-probe'

test.describe('P1 - 移动端照片查看器、网格密度与更多导航', () => {
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

  test('浏览器返回键优先关闭照片查看器并停留在当前页面', async ({ page, request }, testInfo) => {
    const probe = await requirePhotos(request, testInfo, 1, 20)
    if (!probe.ok) return

    const media = await openFirstPhoto(page)
    const photosUrl = page.url()

    await page.goBack()

    await expect(media).toBeHidden()
    await expect(page).toHaveURL(photosUrl)
  })

  test('更多菜单可展开当前照片的单项处理任务', async ({ page, request }, testInfo) => {
    const probe = await requirePhotos(request, testInfo, 1, 20)
    if (!probe.ok) return

    await openFirstPhoto(page)
    await page.getByTestId('photo-lightbox-toolbar').getByRole('button', { name: '更多' }).click()

    const processingMenu = page.getByTestId('photo-processing-menu')
    await expect(processingMenu).toBeVisible()
    await processingMenu.click()

    const operations = page.getByTestId('photo-processing-operations')
    await expect(operations).toBeVisible()
    await expect(operations.getByRole('button', { name: 'AI 智能分析' })).toBeVisible()
    await expect(operations.getByRole('button', { name: '人脸识别' })).toBeVisible()
    await expect(operations.getByRole('button', { name: '文字识别 OCR' })).toBeVisible()
    await expect(operations.getByRole('button', { name: '场景分类' })).toBeVisible()
    await expect(operations.getByRole('button', { name: '生成搜索特征' })).toBeVisible()
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

    await page.getByRole('button', { name: '更多' }).click()
    await expect(drawer).toBeVisible()
    const pathname = new URL(page.url()).pathname
    await page.goBack()
    await expect(drawer).toBeHidden()
    await expect(page).toHaveURL(url => url.pathname === pathname)
  })

  test('照片墙双指捏合可切换每行照片数量并记住密度', async ({ page, request }, testInfo) => {
    const probe = await requirePhotos(request, testInfo, 12, 50)
    if (!probe.ok) return
    // addInitScript runs again after page.reload(). Only clear the persisted
    // density once, otherwise the reload assertion erases the value it tests.
    await page.addInitScript(() => {
      const initializationKey = 'trailsnap_grid_density_test_initialized'
      if (sessionStorage.getItem(initializationKey)) return
      localStorage.removeItem('trailsnap_mobile_grid_columns')
      sessionStorage.setItem(initializationKey, '1')
    })
    await page.goto('/photos')

    const grid = page.getByTestId('photo-grid').first()
    await expect(grid).toBeVisible({ timeout: 20_000 })
    const columnCount = () => grid.evaluate((element) =>
      getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean).length,
    )
    expect(await columnCount()).toBe(3)

    // Pinch inward: distance 240px -> 80px, revealing more photos per row.
    await grid.dispatchEvent('touchstart', {
      touches: [
        { identifier: 1, clientX: 75, clientY: 400 },
        { identifier: 2, clientX: 315, clientY: 400 },
      ],
      changedTouches: [],
    })
    await grid.dispatchEvent('touchmove', {
      touches: [
        { identifier: 1, clientX: 155, clientY: 400 },
        { identifier: 2, clientX: 235, clientY: 400 },
      ],
      changedTouches: [],
    })
    await page.waitForTimeout(50)
    await grid.dispatchEvent('touchend', { touches: [], changedTouches: [] })

    await expect.poll(columnCount).toBeGreaterThanOrEqual(6)
    expect(await page.evaluate(() => localStorage.getItem('trailsnap_mobile_grid_columns'))).toBeTruthy()

    // The saved density is restored on the next visit.
    const savedColumns = await columnCount()
    await page.reload({ waitUntil: 'domcontentloaded' })
    await expect(page.getByTestId('photo-grid').first()).toBeVisible({ timeout: 20_000 })
    await expect.poll(() => page.getByTestId('photo-grid').first().evaluate((element) =>
      getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean).length,
    )).toBe(savedColumns)
  })

  test('高密度照片墙使用方形缩略图并按月/年折叠日期', async ({ page, request }, testInfo) => {
    const probe = await requirePhotos(request, testInfo, 12, 50)
    if (!probe.ok) return
    await page.addInitScript(() => {
      const initializationKey = 'trailsnap_date_density_test_initialized'
      if (sessionStorage.getItem(initializationKey)) return
      localStorage.setItem('trailsnap_mobile_grid_columns', '12')
      sessionStorage.setItem(initializationKey, '1')
    })
    await page.goto('/photos')

    const photo = page.locator('[data-photo-id]').first()
    await expect(photo).toBeVisible({ timeout: 20_000 })
    await expect(photo).toHaveCSS('border-radius', '0px')
    await expect(page.getByTestId('photo-date-header').first()).toHaveAttribute('data-date-mode', 'month')

    await page.evaluate(() => localStorage.setItem('trailsnap_mobile_grid_columns', '24'))
    await page.reload({ waitUntil: 'domcontentloaded' })
    await expect(page.getByTestId('photo-date-header').first()).toHaveAttribute('data-date-mode', 'year')
  })

  test('从满屏照片放大时双指中心照片保持在视口内', async ({ page, request }, testInfo) => {
    const probe = await requirePhotos(request, testInfo, 24, 50)
    if (!probe.ok) return
    await page.addInitScript(() => localStorage.setItem('trailsnap_mobile_grid_columns', '24'))
    await page.goto('/photos')

    const photos = page.locator('[data-photo-id]')
    await expect(photos.first()).toBeVisible({ timeout: 20_000 })
    const anchor = photos.nth(Math.min(12, await photos.count() - 1))
    const id = await anchor.getAttribute('data-photo-id')
    const before = await anchor.boundingBox()
    expect(id).toBeTruthy()
    expect(before).not.toBeNull()
    const centerX = before!.x + before!.width / 2
    const centerY = before!.y + before!.height / 2

    await anchor.dispatchEvent('touchstart', {
      touches: [
        { identifier: 1, clientX: centerX - 40, clientY: centerY },
        { identifier: 2, clientX: centerX + 40, clientY: centerY },
      ],
      changedTouches: [],
    })
    await anchor.dispatchEvent('touchmove', {
      touches: [
        { identifier: 1, clientX: centerX - 120, clientY: centerY },
        { identifier: 2, clientX: centerX + 120, clientY: centerY },
      ],
      changedTouches: [],
    })
    await page.waitForTimeout(80)
    await anchor.dispatchEvent('touchend', { touches: [], changedTouches: [] })

    const anchoredPhoto = page.locator(`[data-photo-id="${id}"]`)
    await expect(anchoredPhoto).toBeVisible()
    const after = await anchoredPhoto.boundingBox()
    expect(after).not.toBeNull()
    expect(after!.y + after!.height / 2).toBeGreaterThan(0)
    expect(after!.y + after!.height / 2).toBeLessThan(844)
  })

  test('移动端时间轴默认隐藏，滚动显示并支持拖动日期', async ({ page, request }, testInfo) => {
    const probe = await requirePhotos(request, testInfo, 12, 50)
    if (!probe.ok) return
    await page.goto('/photos')

    const timeline = page.getByTestId('album-timeline')
    await expect(timeline).toHaveClass(/opacity-0/)
    await page.mouse.wheel(0, 500)
    await expect(timeline).toHaveClass(/opacity-100/)

    const box = await timeline.boundingBox()
    expect(box).not.toBeNull()
    expect(box!.y).toBeLessThanOrEqual(1)
    expect(box!.height).toBeGreaterThanOrEqual(843)
    await timeline.dispatchEvent('touchstart', {
      touches: [{ identifier: 1, clientX: box!.x + box!.width / 2, clientY: box!.y + 30 }],
      changedTouches: [],
    })
    await timeline.dispatchEvent('touchmove', {
      touches: [{ identifier: 1, clientX: box!.x + box!.width / 2, clientY: box!.y + box!.height - 30 }],
      changedTouches: [],
    })
    const thumb = page.getByTestId('mobile-timeline-thumb')
    await expect(thumb).toBeVisible()
    await expect(thumb).toHaveAttribute('aria-label', '拖动浏览照片日期')
    await expect(thumb.locator('svg')).toHaveCount(2)
    await timeline.dispatchEvent('touchend', { touches: [], changedTouches: [] })
  })
})
