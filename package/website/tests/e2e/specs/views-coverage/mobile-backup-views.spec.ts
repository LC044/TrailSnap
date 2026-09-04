import { expect, test } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

/**
 * Nightly view-coverage round 2026-09-04.
 *
 * 覆盖 coverage-gaps-frontend 中仅剩的 2 个「从未被任何 spec 引用」的 view：
 *   - MobileBackup         (views/settings/MobileBackup.vue)
 *   - MobileBackupSettings (views/settings/MobileBackupSettings.vue)
 * 两者都是 Android 原生壳内的功能页，web 端只能触达其「平台不支持」兜底分支，
 * 因此本文件针对该分支做契约断言（功能分支由 Android App 手工验证）。
 *
 * 挂载条件（src/views/Settings.vue）：
 *   - mobile-backup 菜单项带 mobileOnly: true，但 isAvailable() 在
 *     requestedKey === item.key 时也放行，故带 #mobile-backup(-settings) hash
 *     即可在 web 端直达挂载（requestedKey 会把 mobile-backup-settings 归一为 mobile-backup）。
 *   - MobileBackup 内部 screen === 'settings' 当且仅当 route.hash === '#mobile-backup-settings'，
 *     此时渲染 <MobileBackupSettings embedded>，即 MobileBackupSettings 的唯一 web 触达路径。
 *
 * 平台前提：supportsGalleryBackup() = Capacitor.isNativePlatform() && platform === 'android'，
 * Playwright chromium 为 web 平台 → supported === false，两个 view 都渲染兜底文案。
 */

const OVERVIEW_UNSUPPORTED = '当前设备不支持自动备份'
const SETTINGS_UNSUPPORTED = '当前平台暂不支持图库备份设置'

test.describe('P1 - Nightly view coverage round 2026-09-04 @views-coverage', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo))) return
  })

  test('#mobile-backup -> MobileBackup 概览渲染 + web 端不支持提示', async ({ page }) => {
    await page.goto('/settings#mobile-backup')

    await expect(page.getByRole('heading', { name: '手机备份', level: 1 })).toBeVisible({
      timeout: 15_000,
    })
    await expect(page.getByText(OVERVIEW_UNSUPPORTED)).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText('请使用 Android 原生 App。网页版无法在后台读取系统图库。')).toBeVisible()
    // 不支持时不应渲染「打开备份设置」入口（v-if="supported"）
    await expect(page.getByRole('button', { name: '打开备份设置' })).toHaveCount(0)
  })

  test('#mobile-backup-settings -> MobileBackupSettings 渲染 + 返回按钮可用', async ({ page }) => {
    await page.goto('/settings#mobile-backup-settings')

    await expect(page.getByText(SETTINGS_UNSUPPORTED)).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText('请在 Android 原生 APP 中配置本地相册范围。')).toBeVisible()
    await expect(page.getByRole('button', { name: '返回手机备份' })).toBeVisible()
  })

  test('点击「返回手机备份」-> 回到 MobileBackup 概览且不残留设置屏', async ({ page }) => {
    await page.goto('/settings#mobile-backup-settings')
    await expect(page.getByText(SETTINGS_UNSUPPORTED)).toBeVisible({ timeout: 15_000 })

    await page.getByRole('button', { name: '返回手机备份' }).click()

    await expect(page.getByText(OVERVIEW_UNSUPPORTED)).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText(SETTINGS_UNSUPPORTED)).toHaveCount(0)
  })
})
