import { expect, test, type Page, type Route } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

/**
 * Nightly view coverage — people sub-pages.
 *
 * The 2026-10-22 frontend gap scan (route-table reverse lookup) left two
 * routed views that no existing spec ever touched:
 *
 *   album/people/PersonTimeline     /album/people/:id/timeline
 *   album/people/GroupAlbumDetail   /album/people/group/:ids
 *
 * Both are reachable only from inside the people album (a person's
 * "时光线" tab, and the 合影 card grid), which is why the naive
 * "is the view name mentioned in any spec" scan kept flagging them.
 *
 * Each case drives the view with stubbed API responses and asserts the
 * view really mounted and rendered its own primary heading -- a page that
 * silently renders nothing is exactly the regression this file catches.
 */

const ok = (data: unknown) => ({ code: 0, msg: 'success', data })

/** A year entry of the timeline payload (see src/api/personTimeline.ts). */
const timelineYear = (year: number, photoCount: number) => ({
  year,
  photo_count: photoCount,
  representative_event: {
    start_at: `${year}-05-01T10:00:00`,
    end_at: `${year}-05-02T18:00:00`,
    photo_count: photoCount,
  },
  representative_photos: [],
  memories: [],
})

const personTimeline = {
  people: [
    { id: 'p-1', name: '林小满', avatar_url: null, tags: ['家人'] },
    { id: 'p-2', name: '周野', avatar_url: null, tags: [] },
  ],
  mode: 'pair',
  photo_count: 6,
  year_count: 2,
  years: [timelineYear(2023, 2), timelineYear(2024, 4)],
  first_photo: { id: 'ph-1', photo_time: '2023-05-01T10:00:00' },
  latest_photo: { id: 'ph-2', photo_time: '2024-08-11T18:30:00' },
  peak_month: { month: '2024-08', count: 3 },
}

const identities = [
  { id: 'p-1', identity_name: '林小满', is_hidden: false },
  { id: 'p-2', identity_name: '周野', is_hidden: false },
]

/**
 * One dispatcher for every `/api/faces/**` call the two views make.
 *
 * Playwright evaluates routes in reverse registration order, so several
 * overlapping `page.route` patterns would shadow each other. A single
 * handler that dispatches on the URL keeps the stubs unambiguous.
 */
async function mockFaces(page: Page) {
  await page.route('**/api/faces/**', async (route: Route) => {
    const url = route.request().url()

    if (url.includes('/timeline/hidden')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(ok([])),
      })
      return
    }
    if (url.includes('/timeline')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(ok(personTimeline)),
      })
      return
    }
    if (url.includes('/group-albums')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(ok([])),
      })
      return
    }
    if (url.includes('/identities')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(ok(identities)),
      })
      return
    }
    await route.fallback()
  })
}

test.describe('Nightly view coverage — people sub-pages @views-coverage', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo))) return
    await mockFaces(page)
  })

  test('PersonTimeline 渲染双人时光线标题与年份', async ({ page }) => {
    await page.goto('/album/people/p-1/timeline?with=p-2')

    await expect(page.getByRole('heading', { name: '林小满与周野', level: 1 })).toBeVisible({ timeout: 15_000 })
    // The year rail is rendered from the timeline payload.
    await expect(page.getByRole('navigation', { name: '年份' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '2023' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '2024' })).toBeVisible()
    expect(new URL(page.url()).pathname).toBe('/album/people/p-1/timeline')
  })

  test('PersonTimeline 隐藏管理抽屉可打开', async ({ page }) => {
    await page.goto('/album/people/p-1/timeline')

    await page.getByRole('button', { name: '隐藏管理' }).click()
    await expect(page.getByText('隐藏仅影响当前', { exact: false })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText('暂无隐藏片段')).toBeVisible()
  })

  test('GroupAlbumDetail 渲染合影相册标题', async ({ page }) => {
    await page.goto('/album/people/group/p-1,p-2?names=林小满、周野')

    await expect(page.getByRole('heading', { name: '林小满、周野' })).toBeVisible({ timeout: 15_000 })
    expect(new URL(page.url()).pathname).toBe('/album/people/group/p-1,p-2')
  })

  test('GroupAlbumDetail 成员不足两人时回退到人物列表', async ({ page }) => {
    await page.goto('/album/people/group/p-1')

    await expect(page).toHaveURL(/\/album\/people$/, { timeout: 15_000 })
  })
})
