import { expect, test, type Page, type Route } from '@playwright/test'

/**
 * Nightly view coverage for `views/search/ConditionSearchResult.vue`.
 *
 * The 2026-11-11 nightly gap scan (NIGHTLY-TEST-WATCH.md 4.3) reported this view
 * was never referenced by any spec: the structured-condition-search rework
 * (REQ-240 / PR #458) shipped `ConditionSearchResult.vue` as a child of
 * `SearchResult.vue`, but no spec drives the condition-search branch of `/search`.
 *
 * The view renders when `?type=` is one of the condition search types
 * (person / location / ocr / album / folder / filename / tag / scene / date).
 * It owns three behaviours that are otherwise untested:
 *   1. the condition chip strip (type label + value, removable),
 *   2. the "add filter" entry that opens the FilterPanel dialog,
 *   3. the empty state when the condition search returns nothing.
 *
 * All API calls are stubbed, so the test needs no photo fixtures and no backend.
 */

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

/** Stub the endpoints the search photo store touches: timeline stats, photos, filter options. */
async function stubConditionSearchApi(page: Page, timelineParams: URLSearchParams[] = []) {
  await page.route('**/api/stats/timeline**', async (route: Route) => {
    timelineParams.push(new URL(route.request().url()).searchParams)
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(response({ total_photos: 0, timeline: [] })),
    })
  })
  await page.route('**/api/photos**', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(response([])),
    })
  })
  await page.route('**/api/stats/filters**', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(response({ person_options: [], tag_options: [], location_options: [] })),
    })
  })
}

test.describe('Nightly view coverage — condition search @views-coverage', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test('条件搜索渲染条件标签、空状态与筛选入口', async ({ page }) => {
    await useFakeSession(page)
    const timelineParams: URLSearchParams[] = []
    await stubConditionSearchApi(page, timelineParams)

    await page.goto('/search?q=%E5%A4%9C%E6%99%AF&type=tag')

    // 条件 chip：类型标签 + 关键字，可点击移除
    const chip = page.getByRole('button', { name: '移除标签条件：夜景' })
    await expect(chip).toBeVisible({ timeout: 15_000 })
    await expect(chip).toContainText('标签：夜景')

    // 空状态（搜索无结果）
    await expect(page.getByText('没有符合条件的照片')).toBeVisible({ timeout: 15_000 })

    // 筛选入口
    await expect(page.getByRole('button', { name: '添加筛选' }).first()).toBeVisible()

    // 请求确实带上结构化条件
    expect(timelineParams.length).toBeGreaterThan(0)
    expect(timelineParams[0]?.get('search_type')).toBe('tag')
    expect(timelineParams[0]?.get('search_text')).toBe('夜景')
  })

  test('点击添加筛选打开筛选面板弹窗', async ({ page }) => {
    await useFakeSession(page)
    await stubConditionSearchApi(page)

    await page.goto('/search?q=%E5%A4%9C%E6%99%AF&type=tag')
    await expect(page.getByRole('button', { name: '移除标签条件：夜景' })).toBeVisible({ timeout: 15_000 })

    await page.getByRole('button', { name: '添加筛选' }).first().click()

    const dialog = page.getByRole('dialog', { name: '筛选搜索结果' })
    await expect(dialog).toBeVisible({ timeout: 10_000 })
  })

  test('日期类型无法识别时给出错误提示', async ({ page }) => {
    await useFakeSession(page)
    await stubConditionSearchApi(page)

    await page.goto('/search?q=not-a-date&type=date')

    await expect(page.getByText('无法识别日期，请重新搜索')).toBeVisible({ timeout: 15_000 })
  })
})
