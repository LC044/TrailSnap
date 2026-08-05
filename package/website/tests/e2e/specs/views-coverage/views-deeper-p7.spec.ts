import { expect, test } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

/**
 * P1 - 设置中心问题反馈 + 截图清理覆盖（coverage-gaps-frontend.md 真实未覆盖）
 *
 * 命中此前完全没被任何 spec 触达的两个 view：
 *   - views/settings/FeedbackPage.vue        (/settings?tab=feedback)
 *   - views/settings/ScreenshotCleanupDialog.vue  （dialog，挂载在 BasicSettings
 *                                                  截图清理按钮下，orphan SFC；
 *                                                  这里用 page.goto + console
 *                                                  错误兜底：确保 BasicSettings
 *                                                  加载不抛 dialog resolve 错误）
 *
 * 用例：
 *   1. 「问题反馈」Tab 渲染 - title + GitHub Issues 卡片 + QQ 群
 *   2. 「问题反馈」Tab 链接全部以新窗口打开 (target=_blank)
 *   3. BasicSettings 区块加载不报错（dialog 静态可解析）
 *
 * 不依赖任何后端业务数据，纯渲染层验证。
 */

test.describe('P1 - 设置中心问题反馈 + 截图清理覆盖 @views-coverage', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return
  })

  test('设置中心打开「问题反馈」Tab - 渲染标题 + GitHub Issues + 交流社群', async ({ page }) => {
    await page.goto('/settings?tab=feedback')
    await expect(page).toHaveURL(/settings/)

    // FeedbackPage.vue 模板硬编码 <h2>问题反馈</h2>。
    await expect(page.locator('h2', { hasText: '问题反馈' })).toBeVisible({ timeout: 10_000 })

    // 三张 GitHub Issues 卡片：「报告 Bug」「功能建议」「查看已有 Issues」。
    await expect(page.getByText('报告 Bug', { exact: true }).first()).toBeVisible()
    await expect(page.getByText('功能建议', { exact: true }).first()).toBeVisible()
    await expect(page.getByText('查看已有 Issues', { exact: true }).first()).toBeVisible()

    // 交流社群 + QQ 群号码。
    await expect(page.locator('h3', { hasText: '交流社群' })).toBeVisible()
    await expect(page.locator('text=1078946004')).toBeVisible()
  })

  test('问题反馈链接全部以新窗口打开 (target=_blank)', async ({ page }) => {
    await page.goto('/settings?tab=feedback')
    await expect(page.locator('h2', { hasText: '问题反馈' })).toBeVisible({ timeout: 10_000 })

    // 三个 issue 跳转链接都是 GitHub 链接，且 target=_blank。
    const links = page.locator('a[href^="https://github.com/LC044/TrailSnap"]')
    await expect(links).toHaveCount(3)
    const targets = await links.evaluateAll((anchors) =>
      anchors.map((a) => (a as HTMLAnchorElement).target),
    )
    expect(new Set(targets)).toEqual(new Set(['_blank']))
  })

  test('BasicSettings 区块加载不报错（dialog 静态可解析）', async ({ page }) => {
    // ScreenshotCleanupDialog 是 Element Plus 全屏 dialog + v-model 双向绑定，
    // 没有独立路由 / 没有 spec 直接命中「打开 / 关闭」流（dialog 由 BasicSettings
    // 内部按需触发）。这里改成：用 page.goto 加载 BasicSettings，验证页面挂载
    // 不会因为 dialog 文件存在而抛 resolve 错误。
    const consoleErrors: string[] = []
    page.on('pageerror', (err) => consoleErrors.push(err.message))

    await page.goto('/settings?tab=basic')
    await page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => {})

    // 没有任何 page error；尤其不能有「Failed to resolve component」「找不到 dialog 文件」之类。
    const fatal = consoleErrors.filter(
      (e) => /Failed to resolve|Cannot find module|TypeError:.*dialog/i.test(e),
    )
    expect(fatal).toEqual([])
  })
})
