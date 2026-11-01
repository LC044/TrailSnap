import { expect, test } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

/**
 * Nightly view coverage round 2026-11-02.
 *
 * Covers the six location-statistics components that were absent from every
 * spec after the statistics-page refactor:
 *   LocationStatsView, StatsAnnualTrendCard, StatsTopPlacesCard,
 *   StatsHeatmapCard, StatsPersonPlacesCard, StatsRevisitsCard.
 *
 * The cards render deterministic loading/empty states, so this test does not
 * depend on the local library having location records.
 */
test.describe('P1 - Nightly view coverage round 2026-11-02 @views-coverage', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo))) return
  })

  test('LocationStatsView mounts all statistics cards', async ({ page }) => {
    await page.goto('/album/location')

    const statsButton = page.locator('.location-list button[title="统计视图"]').first()
    await expect(statsButton).toBeVisible({ timeout: 15_000 })
    await statsButton.click()

    for (const heading of [
      '足迹统计',
      '足迹随时间变化',
      '留下最多照片的地方',
      '拍摄日历',
      '人物足迹',
      '多日记录的地方',
    ]) {
      await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible({
        timeout: 20_000,
      })
    }
  })
})
