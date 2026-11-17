/**
 * P1 - Nightly view coverage: ClassificationGroupDetail
 *
 * Route: /album/classification/group/:group(.*)  (router name `ClassificationGroup`)
 *
 * This view is the "big group -> category" drill-down of the intelligent
 * classification feature.  It is the only view under
 * `src/views/album/intelligent-classification/` that was not referenced by any
 * spec, so the nightly view-coverage scan flagged it as a gap.
 *
 * Covered here (deliberately *not* overlapping `classification-folder.spec.ts`,
 * which already exercises the category strip rendering + collapse/expand of a
 * CLIP group):
 *
 *  1. the YOLO / custom-classification group branch - it lists the plain YOLO
 *     tags and hides every tag that is already owned by a CLIP category;
 *  2. selecting a category rewrites the route query (`tag_id`) and re-requests
 *     the photos of the newly active tag;
 *  3. the legacy "moon" entry (a category literally named the moon) redirects
 *     to the moon journal instead of loading photos;
 *  4. a group without any visible category renders the dedicated empty state.
 */

import { test, expect, type Page, type Route } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

test.describe.configure({ mode: 'serial' })

/** "YOLO / custom classification" - the special group handled by the view. */
const YOLO_GROUP = 'YOLO / \u81ea\u5b9a\u4e49\u5206\u7c7b'

/** Plain (non CLIP) tags returned by GET /api/tags. */
const YOLO_TAGS = [
  { id: 'tag-yolo-1', tag_name: '\u6d77\u8fb9', count: 12, cover: null },
  { id: 'tag-yolo-2', tag_name: '\u591c\u666f', count: 8, cover: null },
  // This tag is owned by a CLIP category and must therefore be hidden here.
  { id: 'tag-clip-1', tag_name: '\u81ea\u62cd', count: 5, cover: null },
]

/** CLIP categories - one of them owns a tag id that also exists in /api/tags. */
const CLIP_CATEGORIES = {
  code: 0,
  message: 'success',
  data: {
    groups: ['\u4eba\u7269'],
    categories: [
      {
        id: 'cat-1',
        tag_id: 'tag-clip-1',
        name: '\u81ea\u62cd',
        groups: ['\u4eba\u7269'],
        enabled: false,
        revision: 1,
        descriptions: [],
        reference_images: [],
        strictness: 'standard',
        thresholds: {},
        builtin: true,
        count: 5,
        calibration: { status: 'reviewed' },
      },
    ],
  },
}

function ok(data: unknown) {
  return { code: 0, message: 'success', data }
}

/** GET /api/tags -> the plain tag list. */
async function mockTags(page: Page, tags: unknown[] = YOLO_TAGS) {
  await page.route('**/api/tags**', (route: Route) => {
    const url = new URL(route.request().url())
    if (/\/photos$/.test(url.pathname)) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ok([])) })
    }
    if (/\/remove-photos$/.test(url.pathname) || /\/cover$/.test(url.pathname)) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ok(true)) })
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ok(tags)) })
  })
}

/** GET /api/tags/clip/categories -> the CLIP category catalogue. */
async function mockClipCategories(page: Page, body: unknown = CLIP_CATEGORIES) {
  await page.route('**/api/tags/clip/categories', (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) }),
  )
}

test.describe('P1 - Nightly view coverage: ClassificationGroupDetail @views-coverage', () => {
  test.setTimeout(120_000)

  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return
  })

  test('YOLO group -> lists the plain tags and hides the CLIP-owned ones', async ({ page }) => {
    await mockTags(page)
    await mockClipCategories(page)

    await page.goto(`/album/classification/group/${encodeURIComponent(YOLO_GROUP)}`, {
      waitUntil: 'domcontentloaded',
    })

    const strip = page.getByTestId('classification-category-strip')
    await expect(strip).toBeVisible({ timeout: 15_000 })

    // The plain YOLO tag is shown ...
    await expect(strip.getByTestId('classification-category-\u6d77\u8fb9')).toBeVisible()
    await expect(strip.getByTestId('classification-category-\u591c\u666f')).toBeVisible()
    // ... while the tag that is owned by a CLIP category is filtered out.
    await expect(strip.getByTestId('classification-category-\u81ea\u62cd')).toHaveCount(0)
  })

  test('selecting a category -> rewrites the route query and reloads that tag', async ({ page }) => {
    await mockTags(page)
    await mockClipCategories(page)

    const requested: string[] = []
    await page.route('**/api/tags/**/photos**', (route: Route) => {
      const url = new URL(route.request().url())
      requested.push(url.pathname + '?' + url.searchParams.toString())
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ok([])) })
    })

    await page.goto(`/album/classification/group/${encodeURIComponent(YOLO_GROUP)}`, {
      waitUntil: 'domcontentloaded',
    })
    const strip = page.getByTestId('classification-category-strip')
    await expect(strip.getByTestId('classification-category-\u591c\u666f')).toBeVisible({ timeout: 15_000 })

    await strip.getByTestId('classification-category-\u591c\u666f').click()

    // The active category is written into the query string.
    await expect.poll(() => page.url(), { timeout: 10_000 }).toContain('tag_id=tag-yolo-2')
    // And the photos of the newly selected tag are requested.
    await expect
      .poll(() => requested.some((r) => r.includes('tag_id=tag-yolo-2')), { timeout: 10_000 })
      .toBeTruthy()
  })

  test('a category named "moon" -> redirects to the moon journal', async ({ page }) => {
    // The moon tile must not be the active one, otherwise the view ignores
    // the click (clicking the active category is a no-op).
    await mockTags(page, [
      { id: 'tag-yolo-2', tag_name: '\u591c\u666f', count: 8, cover: null },
      { id: 'tag-moon', tag_name: '\u6708\u4eae', count: 3, cover: null },
    ])
    await mockClipCategories(page)

    await page.goto(`/album/classification/group/${encodeURIComponent(YOLO_GROUP)}`, {
      waitUntil: 'domcontentloaded',
    })
    const strip = page.getByTestId('classification-category-strip')
    await expect(strip.getByTestId('classification-category-\u6708\u4eae')).toBeVisible({ timeout: 15_000 })

    await strip.getByTestId('classification-category-\u6708\u4eae').click()

    await expect.poll(() => new URL(page.url()).pathname, { timeout: 10_000 }).toBe('/moon')
  })

  test('a group without any visible category -> renders the empty state', async ({ page }) => {
    await mockTags(page, [])
    await mockClipCategories(page)

    await page.goto(`/album/classification/group/${encodeURIComponent('\u81ea\u7136\u98ce\u666f')}`, {
      waitUntil: 'domcontentloaded',
    })

    await expect(page.getByText('\u8be5\u5206\u7ec4\u6682\u65e0\u7c7b\u522b')).toBeVisible({ timeout: 15_000 })
    await expect(page.getByTestId('classification-category-strip')).toHaveCount(0)
  })
})