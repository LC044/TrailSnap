import { expect, test, type Page, type Route } from '@playwright/test'

const response = (data: unknown) => ({ code: 0, message: 'success', data })

async function useFakeSession(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('user_token', 'fake-e2e-token')
    localStorage.setItem('username', 'e2e-mock')
    localStorage.setItem(
      'user_info',
      JSON.stringify({ id: 'u-e2e', username: 'e2e-mock', is_active: true, is_superuser: true }),
    )
  })
  await page.route('**/api/auth/me**', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 'u-e2e', username: 'e2e-mock', is_active: true, is_superuser: true }),
    })
  })
}

test.describe('Nightly view coverage — chapter & memory @views-coverage', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test('ChapterList renders empty state with action to create first chapter', async ({ page }) => {
    await useFakeSession(page)
    await page.route('**/api/chapters**', async (route: Route) => {
      const url = route.request().url()
      if (url.includes('counts_only')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(response({ total: 0, items: [] })),
        })
        return
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(response({ total: 0, items: [] })),
      })
    })
    await page.goto('/chapters')
    await expect(page.getByRole('heading', { name: '人生章节', level: 1 })).toBeVisible({ timeout: 10_000 })
    await expect(page.getByRole('link', { name: '创建第一本日记' })).toBeVisible()
    await expect(page.getByRole('button', { name: '从照片发现章节' })).toBeVisible()
  })

  test('ChapterList switches to candidate tab and renders suggestion empty state', async ({ page }) => {
    await useFakeSession(page)
    let listUrl = ''
    await page.route('**/api/chapters**', async (route: Route) => {
      listUrl = route.request().url()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(response({ total: 0, items: [] })),
      })
    })
    await page.goto('/chapters')
    await expect(page.getByRole('heading', { name: '人生章节', level: 1 })).toBeVisible()
    await page.getByRole('button', { name: '章节建议' }).click()
    await expect(page.getByRole('heading', { name: '这里暂时没有章节' })).toBeVisible({ timeout: 5_000 })
    expect(listUrl).toContain('status=candidate')
  })

  test('MemoryList renders empty state with primary actions', async ({ page }) => {
    await useFakeSession(page)
    await page.route('**/api/memories/counts**', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(response({ candidate: 0, confirmed: 0, ignored: 0 })),
      })
    })
    await page.route('**/api/memories**', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(response({ total: 0, items: [] })),
      })
    })
    await page.goto('/memories')
    await expect(page.getByRole('heading', { name: '记忆', level: 1 })).toBeVisible({ timeout: 10_000 })
    await expect(page.getByRole('link', { name: /新建记忆/ }).first()).toBeVisible()
  })
})
