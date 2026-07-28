import { expect, test } from '@playwright/test'

const hostPath = '/tests/e2e/fixtures/nightly-view-host.html'
const pixel =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
// Fixture imports Vue + ElementPlus + Pinia + global CSS + the heavy SFCs; on a cold
// CI runner the bundle can take >5s to mount the first time. The helper waits for
// networkidle and bumps the first toBeVisible timeout to absorb the cold load.
const COLD_LOAD_TIMEOUT = 30_000

async function loadFixture(page, fixture) {
  await page.goto(`${hostPath}?fixture=${fixture}`, { waitUntil: 'domcontentloaded' })
  await page.waitForLoadState('networkidle')
  // Note: do not wait on #nightly-view-host visibility here; the screenshots fixture
  // wraps a closed dialog so the host is hidden until the dialog opens. Individual
  // tests wait for the specific element they need with COLD_LOAD_TIMEOUT.
}

test.describe.configure({ mode: 'serial' })

test.describe('P1 - nightly component coverage @views-coverage', () => {
  test('RegionDetailsPanel renders metrics and emits navigation events', async ({ page }) => {
    await loadFixture(page, 'region')

    const host = page.locator('#nightly-view-host')
    await expect(host.getByRole('heading', { name: '\u6e56\u5317\u7701' })).toBeVisible({ timeout: COLD_LOAD_TIMEOUT })
    await expect(host.getByText('12', { exact: true })).toBeVisible()
    await expect(host.getByText('50%', { exact: true })).toBeVisible()
    await expect(host.getByText('#\u6c5f\u57ce', { exact: true })).toBeVisible()
    await expect(host.getByText('\u9ec4\u77f3\u5e02', { exact: true })).toBeVisible()
    await expect(host.getByText('\u7cbe\u5f69\u77ac\u95f4', { exact: true })).toBeVisible()

    await host.getByText('\u6b66\u6c49\u5e02', { exact: true }).first().click()
    await expect(page.locator('#event-log')).toContainText('click-location:\u6b66\u6c49\u5e02:city')

    await host.getByRole('button', { name: '\u8fdb\u5165\u57ce\u5e02\u5730\u56fe' }).click()
    await expect(page.locator('#event-log')).toContainText('change-level:city:\u6e56\u5317\u7701')
  })

  test('RegionDetailsPanel renders empty states and clears selection', async ({ page }) => {
    await loadFixture(page, 'region-empty')

    const host = page.locator('#nightly-view-host')
    await expect(host.getByText('\u8fd9\u91cc\u8fd8\u662f\u4e00\u7247\u672a\u77e5\u9886\u57df\uff0c\u5feb\u53bb\u63a2\u7d22\u5427\uff01')).toBeVisible()
    await expect(host.getByText('\u6682\u65e0\u6700\u8fd1\u8bbf\u95ee\u8bb0\u5f55')).toBeVisible()
    await expect(host.getByText('\u6682\u65e0\u7167\u7247\u9884\u89c8')).toBeVisible()
    await expect(host.getByText('0%', { exact: true })).toBeVisible()

    await host.locator('button').first().click()
    await expect(page.locator('#event-log')).toContainText('clear-selection')
  })

  test('ScreenshotCleanupDialog loads screenshots and totals their size', async ({ page }) => {
    let requestUrl = ''
    await page.route('**/api/storage/screenshots**', async (route) => {
      requestUrl = route.request().url()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          msg: 'success',
          data: [
            {
              id: 'capture-1',
              url: pixel,
              thumbnail: pixel,
              preview: pixel,
              srcset: '',
              timestamp: 1,
              albumIds: [],
              filename: 'capture-a.png',
              file_type: 'image',
              size: 1024,
            },
            {
              id: 'capture-2',
              url: pixel,
              thumbnail: pixel,
              preview: pixel,
              srcset: '',
              timestamp: 2,
              albumIds: [],
              filename: 'capture-b.png',
              file_type: 'image',
              size: 2048,
            },
          ],
        }),
      })
    })

    await loadFixture(page, 'screenshots')

    await expect(page.getByRole('dialog')).toBeVisible({ timeout: COLD_LOAD_TIMEOUT })
    await expect(page.getByText('\u7ba1\u7406\u622a\u56fe\u4e0e\u8868\u60c5\u5305')).toBeVisible()
    await expect(page.getByText('\u5171 2 \u5f20\u622a\u56fe\uff0c\u5360\u7528 3 KB')).toBeVisible()
    await expect(page.locator('img[alt="capture-a.png"]')).toBeVisible()
    expect(requestUrl).toContain('skip=0')
    expect(requestUrl).toContain('limit=1000')
  })

  test('ScreenshotCleanupDialog renders its empty state', async ({ page }) => {
    await page.route('**/api/storage/screenshots**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, msg: 'success', data: [] }),
      })
    })

    await loadFixture(page, 'screenshots')

    await expect(page.getByText('\u592a\u68d2\u4e86\uff0c\u6ca1\u6709\u627e\u5230\u622a\u56fe\uff01')).toBeVisible()
    await expect(page.getByText('\u5171 0 \u5f20\u622a\u56fe\uff0c\u5360\u7528 0 B')).toBeVisible()
  })

  test('ScreenshotCleanupDialog reports API failures', async ({ page }) => {
    await page.route('**/api/storage/screenshots**', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ code: 500, msg: 'storage unavailable', data: null }),
      })
    })

    await loadFixture(page, 'screenshots')

    await expect(page.locator('.el-message', { hasText: '\u52a0\u8f7d\u622a\u56fe\u5931\u8d25' })).toBeVisible({ timeout: COLD_LOAD_TIMEOUT })
  })
})
