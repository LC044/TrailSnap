import { expect, test } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'
import { requireAnyLocation } from '../../helpers/location-probe'

/**
 * Nightly view coverage round 2026-11-24.
 *
 * The location atlas refactor shipped two new components under
 * `src/views/album/location/components/`:
 *   - LocationAtlasHero  （图鉴头图，第一张位置的通栏卡片）
 *   - LocationAtlasCard  （图鉴网格卡片）
 *
 * Both are rendered by LocationListView, and neither had been referenced by
 * any spec before this round, so the view-coverage scan reported them as
 * blind spots. The atlas only renders when the library has at least one
 * location with photos, so the probe guard skips the case otherwise.
 */
test.describe('P1 - Nightly view coverage round 2026-11-24 @views-coverage', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo))) return
  })

  test('LocationAtlasHero 与 LocationAtlasCard 渲染位置图鉴', async ({ page, request }, testInfo) => {
    const probe = await requireAnyLocation(request, testInfo)
    if (!probe.ok) return

    await page.goto('/album/location')

    // 头图组件：通栏卡片，带 NO. 序号与地点名。
    const hero = page.locator('.atlas-hero').first()
    await expect(hero).toBeVisible({ timeout: 20_000 })
    await expect(hero.locator('.atlas-hero-name')).toBeVisible()

    // 网格卡片组件：每个地点一张卡片，展示地点名。
    const cards = page.locator('.atlas-card')
    await expect(cards.first()).toBeVisible({ timeout: 20_000 })
    await expect(cards.first().locator('.atlas-card-name')).toBeVisible()

    // 卡片数量应与图鉴网格里的地点数一致（头图不计入卡片）。
    const gridItems = page.getByTestId('location-album-grid').locator(':scope > div.group')
    await expect(gridItems).toHaveCount(await cards.count() + 1)
  })
})
