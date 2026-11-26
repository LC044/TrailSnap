import { expect, test, type Page } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

/**
 * Nightly view coverage round 2026-11-25.
 *
 * The view gap scan (NIGHTLY-TEST-WATCH.md 4.3) reported `ToolboxPhotoPreview`
 * as the only view under `src/views` that no spec referenced by name. The
 * component is the thumbnail button used by the toolbox plan cards
 * (`ToolPlanPreview`, `ToolboxHomePage`, `ToolWorkflowPage`).
 *
 * The component owns three behaviours that no other spec pinned down:
 *   1. it renders the thumbnail of the given photo id;
 *   2. clicking it opens the shared PhotoLightbox on the clicked photo;
 *   3. the lightbox walks the whole group (`photo-ids`), not just the photo
 *      that was clicked.
 *
 * The plan APIs are stubbed so the preview renders without scanned fixtures.
 */

const planId = 'nightly-toolbox-preview-plan'

const previewPlan = {
  id: planId,
  kind: 'cleanup',
  status: 'preview',
  version: 1,
  request: {
    scope: {
      source: 'all', album_ids: [], folders: [], include_children: false,
      photo_ids: [], excluded_ids: [], start_date: null, end_date: null,
      upload_time_fallback: false, media_type: 'image',
    },
    config: {
      kind: 'cleanup', action: null, target: '', layout: 'preserve', rules: [],
      missing: 'skip', multi_group: 'skip', template: '', start_index: 1,
      reset_index: false, descending: false, album_prefix: '', cleanup_mode: 'quality',
      compare_all: false, similarity: 0.9, quality_max: 60, time_mode: 'auto',
      custom_time: null, make: '', model: '', only_missing_metadata: false,
    },
  },
  summary: { total: 3, ready: 3, skipped: 0, failed: 0, success: 0 },
  task_id: null,
  created_at: '2026-11-25T00:00:00',
  expires_at: '2026-11-26T00:00:00',
  finished_at: null,
  stop_requested: false,
}

const planItems = [
  { id: 1, photo_id: '00000000-0000-0000-0000-000000000501', source: '/photos/nightly-a.jpg', target: '', status: 'candidate', reason: '', detail: { quality_score: 12 } },
  { id: 2, photo_id: '00000000-0000-0000-0000-000000000502', source: '/photos/nightly-b.jpg', target: '', status: 'candidate', reason: '', detail: { quality_score: 8 } },
  { id: 3, photo_id: '00000000-0000-0000-0000-000000000503', source: '/photos/nightly-c.jpg', target: '', status: 'candidate', reason: '', detail: { quality_score: 4 } },
]

async function stubPlan(page: Page) {
  await page.route('**/api/toolbox/plans**', async route => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/items')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, msg: 'success', data: { items: planItems, total: planItems.length } }),
      })
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 0, msg: 'success', data: previewPlan }),
    })
  })
}

test.describe('P1 - Nightly view coverage round 2026-11-25 @views-coverage', () => {
  test.setTimeout(120_000)

  test.beforeEach(async ({ page, request }, testInfo) => {
    const token = await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' })
    if (!token) return
  })

  test('ToolboxPhotoPreview renders a thumbnail and opens the group in the lightbox', async ({ page }) => {
    await stubPlan(page)
    await page.goto('/toolbox/cleanup?plan=' + planId)

    // The preview button is rendered once per plan item.
    const previews = page.getByRole('button', { name: /^查看照片 / })
    await expect(previews).toHaveCount(3, { timeout: 30_000 })

    // Each preview shows the thumbnail of its own photo.
    await expect(previews.nth(0).locator('img')).toHaveAttribute(
      'src', /00000000-0000-0000-0000-000000000501\/thumbnail/,
    )

    // Clicking the second preview opens the lightbox on that photo, and the
    // lightbox can walk through the whole group.
    await previews.nth(1).click()
    const lightbox = page.locator('.photo-lightbox-shell')
    await expect(lightbox).toBeVisible({ timeout: 20_000 })

    const next = lightbox.getByRole('button', { name: '下一张照片' })
    await expect(next).toBeVisible()
    await next.click()
    await expect(lightbox.getByRole('button', { name: '上一张照片' })).toBeVisible()

    await lightbox.getByRole('button', { name: '关闭照片查看器' }).click()
    await expect(lightbox).toHaveCount(0, { timeout: 20_000 })
  })
})
