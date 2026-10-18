import { test as base, expect, type Page } from '@playwright/test'
import { createServer } from 'vite'
import path from 'node:path'
import os from 'node:os'

// CI serves the production image, which intentionally has no /src modules.
// Exercise the actual Vue components on a separate, worker-owned Vite server.
const test = base.extend<{}, { motionServer: string }>({
  motionServer: [async ({}, use, workerInfo) => {
    const server = await createServer({
      configFile: path.resolve('vite.config.js'),
      cacheDir: path.join(os.tmpdir(), 'trailsnap-motion-cache', String(process.pid), String(workerInfo.workerIndex)),
      optimizeDeps: { entries: ['tests/e2e/fixtures/motion-harness.js'] },
      server: { host: '127.0.0.1', port: 0, strictPort: false, open: false },
    })
    await server.listen()
    try { await use(server.resolvedUrls!.local[0]!) }
    finally { await server.close() }
  }, { scope: 'worker' }],
})

test.use({ storageState: { cookies: [], origins: [] } })

async function fixture(page: Page, origin: string) {
  page.on('pageerror', error => console.error('Motion fixture:', error.message))
  await page.route('**/__motion-fixture', route => route.fulfill({ contentType: 'text/html', body: `
    <html><head><meta charset="utf-8"></head><body><div id="fixture"></div><script type="module">
    import '/tests/e2e/fixtures/motion-harness.js';
    </script></body></html>` }))
  await page.goto(new URL('/__motion-fixture', origin).href)
  await expect(page.locator('#menu-trigger')).toBeVisible({ timeout: 15_000 })
}

test.describe('Shared motion @p0', () => {
  test('pointer and keyboard presses compress then settle; disabled controls stay still', async ({ page, motionServer }) => {
    await fixture(page, motionServer)
    const button = page.locator('#sheet-trigger')
    const box = (await button.boundingBox())!
    await page.mouse.move(box.x + 10, box.y + 10)
    await page.mouse.down()
    await expect(button).toHaveClass(/ts-is-pressed/)
    await expect.poll(() => button.evaluate(el => Number(getComputedStyle(el).scale))).toBeCloseTo(.96, 2)
    await page.mouse.move(1, 1); await page.mouse.up()
    await expect(button).not.toHaveClass(/ts-is-pressed/)
    await expect.poll(() => button.evaluate(el => getComputedStyle(el).scale)).toBe('none')
    await button.focus(); await page.keyboard.down(' ')
    await expect(button).toHaveClass(/ts-is-pressed/)
    await page.keyboard.up(' ')
    await expect(button).not.toHaveClass(/ts-is-pressed/)
    await expect(page.locator('#disabled')).not.toHaveClass(/ts-is-pressed/)
  })

  test('menu uses compositor motion anchored to its trigger and survives rapid toggles', async ({ page, motionServer }) => {
    await fixture(page, motionServer)
    // Capture real keyframes when the animation starts. The 200 ms animation
    // may already finish before a Playwright round trip on a busy build host.
    await page.evaluate(() => {
      const frames = new WeakMap<Element, Keyframe[]>()
      ;(window as any).__motionFrames = frames
      const animate = Element.prototype.animate
      Element.prototype.animate = function (...args) {
        const animation = animate.apply(this, args)
        frames.set(this, (animation.effect as KeyframeEffect).getKeyframes())
        return animation
      }
    })
    const trigger = page.locator('#menu-trigger')
    await trigger.click()
    const menu = page.getByRole('menu')
    await expect(menu).toBeVisible()
    const origin = await menu.evaluate(el => ((window as any).__motionFrames.get(el) as Keyframe[] | undefined)?.find(frame => frame.transform))
    expect(origin).toBeTruthy()
    expect(origin!.transform).toContain('scale(0.96)')
    for (const property of ['width', 'height', 'left', 'top', 'padding', 'backdropFilter', 'boxShadow']) {
      expect(origin).not.toHaveProperty(property)
    }
    await expect.poll(() => menu.evaluate(el => el.getAnimations().length)).toBe(0)
    const triggerBox = (await trigger.boundingBox())!
    const menuBox = (await menu.boundingBox())!
    expect(menuBox.width).toBeGreaterThan(triggerBox.width)
    expect(menuBox.y).toBeGreaterThan(triggerBox.y)
    const originX = await menu.evaluate(el => parseFloat(getComputedStyle(el).transformOrigin))
    expect(Math.abs(menuBox.x + originX - triggerBox.x - triggerBox.width / 2)).toBeLessThan(2)
    await expect(menu).toHaveCSS('will-change', 'auto')
    await trigger.click()
    await expect(menu).toHaveCount(0)
    await trigger.evaluate(el => { (el as HTMLElement).click(); setTimeout(() => (el as HTMLElement).click(), 60) })
    await expect(menu).toHaveCount(0)
    await expect(trigger).toHaveCSS('opacity', '1')
    await trigger.click(); await expect(menu).toBeVisible()
    await trigger.evaluate(el => { (el as HTMLElement).click(); setTimeout(() => (el as HTMLElement).click(), 30) })
    await expect(menu).toBeVisible()
    await expect.poll(() => menu.evaluate(el => el.getAnimations().length)).toBe(0)
    await expect(menu).toHaveCSS('opacity', '1')
    await page.keyboard.press('Escape'); await expect(menu).toHaveCount(0)
  })

  test('capsule buttons compress the shared surface together', async ({ page, motionServer }) => {
    await fixture(page, motionServer)
    const capsule = page.locator('#capsule')
    const child = page.locator('#capsule-other')
    const box = (await child.boundingBox())!
    await page.mouse.move(box.x + 10, box.y + 10); await page.mouse.down()
    await expect(capsule).toHaveClass(/ts-is-pressed/)
    await expect(child).not.toHaveClass(/ts-is-pressed/)
    await expect(child).toHaveCSS('scale', 'none')
    await expect.poll(() => capsule.evaluate(el => Number(getComputedStyle(el).scale))).toBeCloseTo(.96, 2)
    await page.mouse.up()
    await expect.poll(() => capsule.evaluate(el => getComputedStyle(el).scale)).toBe('none')
    const other = page.locator('#menu-trigger')
    const otherBox = (await other.boundingBox())!
    await page.mouse.move(otherBox.x + 10, otherBox.y + 10); await page.mouse.down()
    await expect(capsule).toHaveClass(/ts-is-pressed/)
    await expect.poll(() => capsule.evaluate(el => Number(getComputedStyle(el).scale))).toBeCloseTo(.96, 2)
    await page.mouse.move(1, 1); await page.mouse.up()
  })

  test('overlapping menus and returning to a cached page never leave the capsule hidden', async ({ page, motionServer }) => {
    await fixture(page, motionServer)
    for (let i = 0; i < 3; i++) {
      await page.evaluate(async () => {
        const state = (window as any).fixtureState
        state.menu.value = true
        await new Promise(resolve => setTimeout(resolve, 40))
        state.menu2.value = true
        await new Promise(resolve => setTimeout(resolve, 40))
        state.menu.value = false
        await new Promise(resolve => setTimeout(resolve, 30))
        ;(window as any).fixtureNavigation.value = true
      })
      await expect(page.locator('#away-page')).toBeVisible()
      await expect(page.getByRole('menu')).toHaveCount(0)
      await page.evaluate(() => {
        const state = (window as any).fixtureState
        state.menu.value = false; state.menu2.value = false
        ;(window as any).fixtureNavigation.value = false
      })
      const capsule = page.locator('#capsule')
      await expect(capsule).toHaveCSS('opacity', '1')
      expect(await capsule.evaluate(el => (el as HTMLElement).style.opacity)).toBe('')
      await expect.poll(() => capsule.evaluate(el => el.getAnimations().length)).toBe(0)
    }
  })

  test('successful navigation closes menus and dialogs even when the view is reused', async ({ page, motionServer }) => {
    await fixture(page, motionServer)
    await page.locator('#menu-trigger').click()
    await expect(page.getByRole('menu')).toBeVisible()
    await page.evaluate(() => (window as any).fixtureRouter.push('/motion/two'))
    await expect(page.getByRole('menu')).toHaveCount(0)
    await expect(page.locator('#capsule')).toHaveCSS('opacity', '1')
    await page.locator('#sheet-trigger').click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.evaluate(() => (window as any).fixtureRouter.push('/motion/three'))
    await expect(page.getByRole('dialog')).toHaveCount(0)
  })

  test('navigation during menu exit removes the teleported surface without leaving a white mask', async ({ page, motionServer }) => {
    await fixture(page, motionServer)
    await page.locator('#menu-trigger').click()
    await expect.poll(() => page.getByRole('menu').evaluate(el => el.getAnimations().length)).toBe(0)
    await page.evaluate(async () => {
      ;(window as any).fixtureState.menu.value = false
      await new Promise(resolve => setTimeout(resolve, 30))
      ;(window as any).fixtureNavigation.value = true
    })
    await expect(page.locator('#away-page')).toBeVisible()
    await expect(page.locator('.ts-desktop-menu')).toHaveCount(0)
    await page.evaluate(() => { (window as any).fixtureNavigation.value = false })
    await expect(page.locator('#capsule')).toHaveCSS('opacity', '1')
    await expect(page.locator('.ts-desktop-menu')).toHaveCount(0)
  })

  test('mobile menu keeps layout and glass static throughout the opening animation', async ({ page, motionServer }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await fixture(page, motionServer)
    await page.evaluate(() => {
      const animate = Element.prototype.animate
      let paused = false
      Element.prototype.animate = function (...args) {
        const animation = animate.apply(this, args)
        if (!paused && this.matches('[role="menu"]')) {
          paused = true
          animation.pause()
          animation.currentTime = 100
        }
        return animation
      }
    })
    await page.locator('#menu-trigger').click()
    const menu = page.getByRole('menu', { name: '菜单', exact: true })
    await expect(menu).toBeVisible()
    const motion = await menu.evaluate(el => {
      const animation = el.getAnimations()[0]!
      const effect = animation.effect as KeyframeEffect
      const sample = (time: number) => {
        animation.currentTime = time
        const style = getComputedStyle(el)
        return { width: style.width, height: style.height, filter: style.backdropFilter, padding: style.padding }
      }
      return { duration: effect.getTiming().duration, frames: effect.getKeyframes(), early: sample(20), late: sample(180),
        contentAnimations: el.firstElementChild!.getAnimations().length }
    })
    expect(motion.duration).toBe(200)
    expect(motion.early).toEqual(motion.late)
    expect(motion.contentAnimations).toBe(0)
    expect(motion.frames.every(frame => !('width' in frame) && !('backdropFilter' in frame))).toBe(true)
    await expect(page.locator('#capsule')).toHaveCSS('opacity', '1')
    const menuBox = (await menu.boundingBox())!
    expect(menuBox.x).toBeGreaterThanOrEqual(0)
    expect(menuBox.x + menuBox.width).toBeLessThanOrEqual(390)
    await page.evaluate(() => document.getAnimations().forEach(animation => animation.play()))
    await expect.poll(() => menu.evaluate(el => el.getAnimations().length)).toBe(0)
    await page.keyboard.press('Escape'); await expect(menu).toHaveCount(0)
  })

  test('persistent location panels rubber-band and snap without dismissing', async ({ page, motionServer }) => {
    await fixture(page, motionServer)
    const panel = page.locator('#anchored-sheet'), handle = page.locator('#anchored-handle')
    let box = (await handle.boundingBox())!
    await page.mouse.move(box.x + 20, box.y + 12); await page.mouse.down()
    await page.mouse.move(box.x + 20, -100, { steps: 8 })
    expect((await panel.boundingBox())!.height).toBeGreaterThan(600)
    await page.mouse.up()
    await expect.poll(async () => Math.round((await panel.boundingBox())!.height)).toBe(600)
    box = (await handle.boundingBox())!
    await page.mouse.move(box.x + 20, box.y + 12); await page.mouse.down()
    await page.mouse.move(box.x + 20, 710, { steps: 8 }); await page.mouse.up()
    await expect.poll(async () => Math.round((await panel.boundingBox())!.height)).toBe(62)
    await expect(panel).toBeVisible()
  })

  test('mobile sheet expands, cancels drag safely, resizes and flicks closed', async ({ page, motionServer }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await fixture(page, motionServer)
    await page.locator('#sheet-trigger').click()
    const panel = page.getByRole('dialog')
    await expect(panel).toBeVisible()
    const initial = (await panel.boundingBox())!.height
    const handle = panel.locator('.sheet-drag-zone').first()
    let box = (await handle.boundingBox())!
    await page.mouse.move(box.x + 20, box.y + 14); await page.mouse.down()
    await page.mouse.move(box.x + 20, box.y - 350, { steps: 10 }); await page.mouse.up()
    await expect.poll(async () => (await panel.boundingBox())!.height).toBeGreaterThan(initial + 100)
    box = (await handle.boundingBox())!
    await page.mouse.move(box.x + 20, box.y + 14); await page.mouse.down()
    await page.mouse.move(box.x + 20, box.y + 60)
    await handle.dispatchEvent('pointercancel', { pointerId: 1 })
    await page.mouse.up()
    await expect(panel).toBeVisible()
    await page.setViewportSize({ width: 844, height: 600 })
    await expect.poll(() => panel.evaluate(el => (el as HTMLElement).style.height)).toBe('')
    await page.setViewportSize({ width: 390, height: 844 })
    box = (await handle.boundingBox())!
    await page.mouse.move(box.x + 20, box.y + 14); await page.mouse.down()
    await page.mouse.move(box.x + 20, 840, { steps: 6 }); await page.mouse.up()
    await expect(panel).toHaveCount(0)
  })

  test('reduced motion opens menus without animation or button scaling', async ({ page, motionServer }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await fixture(page, motionServer)
    await page.locator('#menu-trigger').click()
    await expect(page.getByRole('menu')).toBeVisible()
    expect(await page.getByRole('menu').evaluate(el => el.getAnimations().length)).toBe(0)
    await expect(page.locator('#menu-trigger')).toHaveCSS('scale', 'none')
  })
})
