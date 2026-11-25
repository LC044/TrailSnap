import { expect, test, type CDPSession, type Locator, type Page } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'
import { requirePhotos } from '../../helpers/data-probe'

/**
 * P1 - 照片快速选择（PC Shift 范围选择 / 移动端滑选）
 *
 * 覆盖 PC 端 Shift 连选与移动端长按滑选。
 * 运行于 Nightly（pnpm test:e2e），不带 @smoke 标签。
 */

test.describe('P1 - 照片快速选择', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo))) return
  })

  // 进入批量选择模式（走视图设置菜单，与 2.1.7 同入口）
  async function enterBatchMode(page: Page) {
    await page.getByTitle('视图设置').click()
    const batchBtn = page.getByRole('button', { name: '批量选择' })
    await expect(batchBtn).toBeVisible({ timeout: 10_000 })
    await batchBtn.click()
    await expect(page.getByTestId('photo-selection-bar')).toBeVisible({ timeout: 10_000 })
  }

  // 读取当前选中的照片数量（photo-selection-bar 的「已选 N 项」）
  async function selectedCount(page: Page): Promise<number> {
    const bar = page.getByTestId('photo-selection-bar')
    const text = await bar.textContent()
    const match = text?.match(/已选\s*(\d+)\s*项/)
    return match ? Number(match[1]) : 0
  }

  test('PC Shift 点击范围选择：锚点到目标整段选中', async ({ page, request }, testInfo) => {
    const probe = await requirePhotos(request, testInfo, 4, 50)
    if (!probe.ok) return
    await page.goto('/photos')

    const photos = page.locator('[data-photo-id]')
    await expect(photos.first()).toBeVisible({ timeout: 20_000 })

    await enterBatchMode(page)
    await expect(photos.first()).toBeVisible()

    // 普通点击第 1 张作为锚点
    await photos.nth(0).click({ force: true })
    await expect.poll(() => selectedCount(page)).toBe(1)

    // Shift 点击第 3 张：锚点(1)到(3)整段选中
    await photos.nth(2).click({ modifiers: ['Shift'], force: true })
    await expect.poll(() => selectedCount(page)).toBe(3)

    await expect(page.getByTestId('photo-selection-bar')).toContainText('已选 3 项')
  })

  test('PC Shift 重复点击保持选区，移近终点时只缩短范围', async ({ page, request }, testInfo) => {
    const probe = await requirePhotos(request, testInfo, 4, 50)
    if (!probe.ok) return
    await page.goto('/photos')

    const photos = page.locator('[data-photo-id]')
    await expect(photos.first()).toBeVisible({ timeout: 20_000 })

    await enterBatchMode(page)
    await expect(photos.first()).toBeVisible()

    // 先选 3 张（锚点 + Shift 范围）
    await photos.nth(0).click({ force: true })
    await photos.nth(2).click({ modifiers: ['Shift'], force: true })
    await expect.poll(() => selectedCount(page)).toBe(3)

    await photos.nth(2).click({ modifiers: ['Shift'], force: true })
    await expect.poll(() => selectedCount(page)).toBe(3)

    await photos.nth(1).click({ modifiers: ['Shift'], force: true })
    await expect.poll(() => selectedCount(page)).toBe(2)
  })

  test('PC Shift 范围选择后普通点击重设锚点', async ({ page, request }, testInfo) => {
    const probe = await requirePhotos(request, testInfo, 5, 50)
    if (!probe.ok) return
    await page.goto('/photos')

    const photos = page.locator('[data-photo-id]')
    await expect(photos.first()).toBeVisible({ timeout: 20_000 })

    await enterBatchMode(page)
    await expect(photos.first()).toBeVisible()

    // 中间两张保持未选中，旧锚点会错误地把它们也选上。
    await photos.nth(0).click({ force: true })
    await photos.nth(3).click({ force: true })
    await expect.poll(() => selectedCount(page)).toBe(2)

    await photos.nth(4).click({ modifiers: ['Shift'], force: true })
    await expect.poll(() => selectedCount(page)).toBe(3)
  })

  test('右键已选照片操作整组，右键未选照片保留选区', async ({ page, request }, testInfo) => {
    const probe = await requirePhotos(request, testInfo, 4, 50)
    if (!probe.ok) return
    await page.goto('/photos')

    const photos = page.locator('[data-photo-id]')
    await expect(photos.first()).toBeVisible({ timeout: 20_000 })
    await enterBatchMode(page)
    await photos.nth(0).click()
    await photos.nth(1).click({ modifiers: ['Shift'] })
    await expect.poll(() => selectedCount(page)).toBe(2)

    const menu = page.getByRole('menu', { name: '照片操作' })
    await photos.nth(0).click({ button: 'right' })
    await expect(menu).toContainText('已选 2 项')
    await expect(menu.getByRole('menuitem', { name: '下载所选' })).toBeVisible()
    await menu.getByRole('menuitem', { name: '移到回收站' }).click()
    await expect(page.getByText(/确定要删除选中的 2 张照片/)).toBeVisible()
    await page.getByRole('button', { name: '取消', exact: true }).click()
    await expect(page.locator('.responsive-dialog-leave-active')).toHaveCount(0)

    await photos.nth(2).click({ button: 'right' })
    await menu.getByRole('menuitem', { name: '移到回收站' }).click()
    await expect(page.getByText(/确定要删除选中的 1 张照片/)).toBeVisible()
    await page.getByRole('button', { name: '取消', exact: true }).click()
    await expect(page.locator('.responsive-dialog-leave-active')).toHaveCount(0)

    await photos.nth(2).click({ button: 'right' })
    await menu.getByRole('menuitem', { name: '查看详情' }).click()
    await expect(page.getByRole('button', { name: '查看元数据' })).toHaveAttribute('aria-expanded', 'true')
    await expect.poll(() => selectedCount(page)).toBe(2)
  })
})

test.describe('P1 - 移动端照片滑动快速选择', () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true })

  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo))) return
  })

  async function selectedCount(page: Page): Promise<number> {
    const bar = page.getByTestId('photo-selection-bar')
    const text = await bar.textContent()
    const match = text?.match(/已选\s*(\d+)\s*项/)
    return match ? Number(match[1]) : 0
  }

  async function photoCenter(photo: Locator) {
    const box = await photo.boundingBox()
    if (!box) throw new Error('照片卡片不可见')
    return { x: box.x + box.width / 2, y: box.y + box.height / 2 }
  }

  async function startLongPress(input: CDPSession, photo: Locator) {
    await photo.scrollIntoViewIfNeeded()
    const center = await photoCenter(photo)
    await input.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [center] })
    return center
  }

  async function moveTouch(input: CDPSession, point: { x: number; y: number }) {
    await input.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [point] })
  }

  async function endTouch(input: CDPSession) {
    await input.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
  }

  test('长按进入选择后拖动滑选多张照片，滑动期间不滚动页面', async ({ page, request }, testInfo) => {
    const probe = await requirePhotos(request, testInfo, 4, 20)
    if (!probe.ok) return
    await page.addInitScript(() => localStorage.setItem('trailsnap_mobile_grid_columns', '3'))
    await page.goto('/photos')

    const photos = page.locator('[data-photo-id]')
    await expect(photos.first()).toBeVisible({ timeout: 20_000 })
    const input = await page.context().newCDPSession(page)
    const start = await startLongPress(input, photos.first())
    await expect.poll(() => selectedCount(page)).toBe(1)

    const scrollPosition = () => page.evaluate(() => [window.scrollY, document.querySelector('main')?.scrollTop])
    const beforeSwipe = await scrollPosition()
    // 在滑选监听器之后记录可信移动事件，确认浏览器收到了取消滚动的请求。
    await page.evaluate(() => {
      const gallery = document.querySelector('.photo-gallery')
      window.addEventListener('touchmove', event => {
        if (event.isTrusted) {
          gallery?.setAttribute('data-test-touch-move-cancelled', String(event.defaultPrevented))
        }
      }, { passive: true })
    })
    await moveTouch(input, { x: start.x, y: start.y - 24 })
    await expect(page.locator('.photo-gallery')).toHaveAttribute('data-test-touch-move-cancelled', 'true')
    await moveTouch(input, await photoCenter(photos.nth(1)))
    await moveTouch(input, await photoCenter(photos.nth(2)))
    await endTouch(input)

    await expect.poll(() => selectedCount(page)).toBe(3)
    expect(await scrollPosition()).toEqual(beforeSwipe)
    await expect(page.getByTestId('photo-lightbox-media')).toHaveCount(0)
  })

  test('长按松手后的点击不会取消选择或打开大图', async ({ page, request }, testInfo) => {
    const probe = await requirePhotos(request, testInfo, 4, 20)
    if (!probe.ok) return
    await page.goto('/photos')

    const photo = page.locator('[data-photo-id]').first()
    await expect(photo).toBeVisible({ timeout: 20_000 })
    const input = await page.context().newCDPSession(page)
    await startLongPress(input, photo)
    await expect.poll(() => selectedCount(page)).toBe(1)

    await photo.evaluate(card => {
      window.addEventListener('touchend', event => {
        card.setAttribute('data-test-touch-end-cancelled', String(event.defaultPrevented))
      }, { once: true, passive: true })
    })
    await endTouch(input)

    await expect(photo).toHaveAttribute('data-test-touch-end-cancelled', 'true')
    await expect.poll(() => selectedCount(page)).toBe(1)
    await expect(page.getByTestId('photo-lightbox-media')).toHaveCount(0)
  })

  test('滑动已选中照片区域可快速取消选择', async ({ page, request }, testInfo) => {
    const probe = await requirePhotos(request, testInfo, 4, 20)
    if (!probe.ok) return
    await page.addInitScript(() => localStorage.setItem('trailsnap_mobile_grid_columns', '3'))
    await page.goto('/photos')

    const photos = page.locator('[data-photo-id]')
    await expect(photos.first()).toBeVisible({ timeout: 20_000 })
    const input = await page.context().newCDPSession(page)

    const sweep = async (countAfterLongPress: number) => {
      await startLongPress(input, photos.first())
      await expect.poll(() => selectedCount(page)).toBe(countAfterLongPress)
      await moveTouch(input, await photoCenter(photos.nth(1)))
      await moveTouch(input, await photoCenter(photos.nth(2)))
      await endTouch(input)
    }

    await sweep(1)
    await expect.poll(() => selectedCount(page)).toBe(3)
    await sweep(2)
    await expect.poll(() => selectedCount(page)).toBe(0)
  })
})
