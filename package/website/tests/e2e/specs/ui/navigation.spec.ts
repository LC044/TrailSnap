import { test as base, expect, type Page } from '@playwright/test'
import { createServer } from 'vite'
import path from 'node:path'

const test = base.extend<{}, { navigationServer: string }>({
  navigationServer: [async ({}, use, workerInfo) => {
    const server = await createServer({
      configFile: path.resolve('vite.config.js'),
      cacheDir: path.resolve('.playwright-system/navigation-cache', String(workerInfo.workerIndex)),
      optimizeDeps: { entries: ['tests/e2e/fixtures/navigation-harness.js'] },
      server: { host: '127.0.0.1', port: 0, strictPort: false, open: false },
    })
    await server.listen()
    try { await use(server.resolvedUrls!.local[0]!) } finally { await server.close() }
  }, { scope: 'worker' }],
})
test.use({ storageState: { cookies: [], origins: [] } })

async function fixture(page: Page, origin: string) {
  page.on('pageerror', error => console.error('Navigation fixture:', error.message))
  await page.route('**/__navigation-fixture', route => route.fulfill({ contentType: 'text/html', body: `
    <html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
    <body><div id="fixture"></div><script type="module" src="/tests/e2e/fixtures/navigation-harness.js"></script></body></html>` }))
  await page.goto(new URL('/__navigation-fixture', origin).href, { waitUntil: 'commit' })
  await expect(page.getByText('原页面', { exact: true })).toBeVisible({ timeout: 30_000 })
}

test.describe('Navigation feedback @p0', () => {
  // A cold Vite dependency prebundle can take tens of seconds on CI/Windows.
  test.setTimeout(60_000)
  test('slow route gives immediate feedback before the module arrives, then clears it', async ({ page, navigationServer }) => {
    let release!: () => void
    const gate = new Promise<void>(resolve => { release = resolve })
    await page.route('**/navigation-target.js', async route => { await gate; await route.continue() })
    await fixture(page, navigationServer)
    await page.getByRole('link', { name: '照片', exact: true }).click()
    await expect(page.getByRole('progressbar')).toBeVisible()
    await expect(page.getByRole('status')).toContainText('正在打开所有照片')
    await expect(page.getByText('原页面', { exact: true })).toBeVisible()
    release()
    await expect(page.getByText('照片已打开', { exact: true })).toBeVisible()
    await expect(page.getByRole('progressbar')).toHaveCount(0)
    await expect(page.getByRole('status')).toHaveCount(0)
  })

  test('failure supports keyboard retry and retains the full destination', async ({ page, navigationServer }) => {
    await fixture(page, navigationServer)
    await page.getByRole('link', { name: '票夹', exact: true }).click()
    await expect(page.getByRole('alert')).toContainText('票夹加载失败')
    await expect(page.getByRole('progressbar')).toHaveCount(0)
    await page.getByRole('button', { name: '重试', exact: true }).focus()
    await page.keyboard.press('Enter')
    await expect(page.getByText('票夹已打开', { exact: true })).toBeVisible()
    expect(await page.evaluate(() => (window as any).fixtureRouter.currentRoute.value.fullPath)).toBe('/retry?wallet=all#tickets')
    await expect(page.getByRole('alert')).toHaveCount(0)
  })

  test('mobile dark recovery notice fits the screen and reload uses the failed destination', async ({ page, navigationServer }, testInfo) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await fixture(page, navigationServer)
    await page.evaluate(() => {
      const theme = (window as any).fixtureTheme
      theme.setMode('dark'); theme.setTheme(theme.themeColors.find((item: any) => item.name === 'violet'))
    })
    await page.getByRole('link', { name: '票夹', exact: true }).click()
    const notice = page.getByRole('alert')
    await expect(notice).toBeVisible()
    const box = (await notice.boundingBox())!
    expect(box.x).toBeGreaterThanOrEqual(0)
    expect(box.x + box.width).toBeLessThanOrEqual(375)
    await page.screenshot({ path: testInfo.outputPath('navigation-dark-mobile.png') })
    await page.route('**/retry?wallet=all', route => route.fulfill({ contentType: 'text/html; charset=utf-8', body: '已重新加载目标页面' }))
    await page.getByRole('button', { name: '重新加载页面', exact: true }).click()
    await expect(page).toHaveURL(/\/retry\?wallet=all#tickets$/)
    await expect(page.getByText('已重新加载目标页面')).toBeVisible()
  })
})
