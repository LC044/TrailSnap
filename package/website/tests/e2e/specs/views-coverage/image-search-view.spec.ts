import { expect, test, type Page, type Route } from '@playwright/test'

/**
 * Nightly view coverage for `views/search/ImageSearch.vue` — the "以图搜图"
 * page that the Chinese-CLIP rollout (REQ-205) added at `/search/image`.
 *
 * The 2026-10-28 nightly gap scan maps every routed view to the specs that
 * reach it.  `ImageSearch.vue` was the only routed view without a spec after
 * `master` merged, so this file closes that hole.
 *
 * The page offers two sources for the query image: an uploaded file
 * (`POST /api/search/image`) and a library photo (`POST /api/search/photo`).
 * The library-photo path is covered here because it is the one that can be
 * driven deterministically from a URL, without synthesising a file upload.
 */

const response = (data: unknown) => ({ code: 0, message: 'success', data })

const PHOTO = {
  id: 'p-1',
  owner_id: 'u-e2e',
  filename: 'a.jpg',
  width: 800,
  height: 600,
  photo_time: '2024-05-06T10:00:00',
  upload_time: '2024-05-06T10:00:00',
  file_type: 'image',
  is_deleted: false,
}

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

test.describe('Nightly view coverage — image search @views-coverage', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test('ImageSearch 渲染以图搜图页面与两个图片来源入口', async ({ page }) => {
    await useFakeSession(page)
    await page.goto('/search/image')

    await expect(page.getByRole('heading', { name: '以图搜图' })).toBeVisible({ timeout: 10_000 })
    await expect(page.getByRole('button', { name: '上传图片' })).toBeVisible()
    await expect(page.getByRole('button', { name: '从图库选择' })).toBeVisible()
    await expect(page.getByText('支持不超过 20 MB 的图片，上传仅用于本次搜索。')).toBeVisible()
  })

  test('ImageSearch 用图库照片搜索并展示相似照片数量', async ({ page }) => {
    await useFakeSession(page)

    const requests: string[] = []
    await page.route('**/api/search/photo**', async (route: Route) => {
      const body = route.request().postDataJSON() as { photo_id?: string }
      requests.push(body.photo_id ?? '')
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(response([{ photo: PHOTO, score: 0.9 }])),
      })
    })

    await page.goto('/search/image?photo=p-1')

    await expect(page.getByText('找到 1 张相似照片，按相似度排序（最多 100 张）')).toBeVisible({
      timeout: 10_000,
    })
    expect(requests).toContain('p-1')
  })

  test('ImageSearch 搜索失败时展示错误提示与重试入口', async ({ page }) => {
    await useFakeSession(page)

    await page.route('**/api/search/photo**', async (route: Route) => {
      await route.fulfill({
        status: 502,
        contentType: 'application/json',
        body: JSON.stringify({ code: 502, message: 'AI 服务错误', data: null }),
      })
    })

    await page.goto('/search/image?photo=p-1')

    // The page renders its own role="alert" box; Element Plus also raises
    // toast alerts, so the assertion is scoped to the in-page one.
    const alert = page.locator('div[role="alert"]').filter({ hasText: '搜索失败' })
    await expect(alert).toBeVisible({ timeout: 10_000 })
    await expect(alert).toContainText('搜索失败')
    await expect(page.getByRole('button', { name: '重试' })).toBeVisible()
  })

  test('ImageSearch 没有相似照片时展示空态', async ({ page }) => {
    await useFakeSession(page)

    await page.route('**/api/search/photo**', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(response([])),
      })
    })

    await page.goto('/search/image?photo=p-1')

    await expect(page.getByText('未找到相似照片，请尝试其他图片')).toBeVisible({ timeout: 10_000 })
  })
})
