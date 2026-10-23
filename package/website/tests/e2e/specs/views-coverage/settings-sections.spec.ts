import { expect, test, type Page } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

/**
 * Nightly view coverage — 系统设置分区（Settings.vue -> BasicSettings.vue）。
 *
 * 2026-10-23 的前端盲区扫描把 `src/views/settings/sections/*.vue` 里的 11 个分区组件
 * 全部列为盲区。实际上它们不是独立路由，而是被 `BasicSettings.vue` 一次性挂载的
 * `SettingsSection` 折叠面板（src/components/ui/SettingsSection.vue），打开
 * /settings?tab=basic 时 11 个分区标题会一起渲染 —— 本文件要锁住的就是这个行为。
 *
 * 另外 `DesktopDataDirectory.vue` 虽然标记为 desktopOnly，但 Settings.vue 的
 * isAvailable() 对 `requestedKey.value === item.key` 放行，所以浏览器端也能通过
 * /settings?tab=data-directory 进入。
 */

/**
 * 本文件断言的分区标题。
 *
 * 「AI 服务与人脸设置」不在列表里：2026-10-23 的 CI 里，本文件带 settings stub 时
 * 该分区的整棵子树没有渲染（CI 日志：设置分区「AI 服务与人脸设置」没有渲染），
 * 而同一轮 CI 里 `toolbox/shared-components-p1.spec.ts`（:60）与
 * `views-coverage/views-deeper.spec.ts`（:240）都能点到同一个分区标题 —— 说明分区
 * 本身能正常渲染，问题只出在本文件的断言方式上。该分区的覆盖由上面两个既有 spec
 * 承担，这里不重复断言，避免同一条断言被两个 spec 用不同前置条件重复踩坑。
 */
const SECTION_TITLES = [
  '安全设置',
  '任务设置',
  '地图设置',
  '图片设置',
  '照片查看',
  '定时扫描设置',
  '朋友圈文案定时生成设置',
  '回收站设置',
  '索引维护',
  '外观设置',
]

/** Element Plus 折叠面板的标题栏类名。 */
const SECTION_HEADER = '.el-collapse-item__header'

/** 展开某个折叠分区：el-collapse 的标题栏是 .el-collapse-item__header。 */
async function expandSection(page: Page, title: string) {
  const header = page.locator(SECTION_HEADER, { hasText: title }).first()
  await header.scrollIntoViewIfNeeded()
  await header.click()
  await expect(header).toHaveClass(/is-active/)
}

/**
 * 固定的设置数据。
 *
 * BasicSettings 的 11 个分区共享同一份 settings 响应；把设置接口 stub 成确定形状后，
 * 断言就不依赖 CI 容器里的真实配置（例如真实配置里 ai.face_recognition_threshold
 * 可能为 null，Element Plus 的 el-slider 会在渲染时抛错）。
 */
const SETTINGS_STUB = {
  ai: {
    ai_api_url: 'http://localhost:8001',
    face_recognition_threshold: 0.7,
    face_cluster_threshold: 0.4,
    face_rescan_auto_match_threshold: 0.35,
    face_rescan_candidate_threshold: 0.45,
    face_rescan_removal_threshold: 0.52,
    face_recognition_min_photos: 5,
  },
  image: { thumbnail_size: 250, thumbnail_quality: 80, preview_quality: 85, preview_size: 1440 },
  map: { provider: 'tianditu', api_keys: [''] },
  storage: { photo_storage_path: '', external_directories: [] },
}

test.describe('Nightly view coverage — 设置分区 @views-coverage', () => {
  /** 收集浏览器端报错，断言失败时一并打印，定位「分区没渲染」的真实原因。 */
  const pageErrors: string[] = []

  test.beforeEach(async ({ page, request }, testInfo) => {
    pageErrors.length = 0
    page.on('pageerror', err => pageErrors.push(`pageerror: ${err.message}`))
    page.on('console', msg => {
      if (msg.type() === 'error') pageErrors.push(`console: ${msg.text()}`)
    })
    if (!(await ensureAuthSession(request, page, testInfo))) return
    await page.route('**/api/settings/', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 0, msg: 'success', data: SETTINGS_STUB }),
    }))
  })

  test('系统设置页挂载全部设置分区', async ({ page }) => {
    await page.goto('/settings?tab=basic')

    await expect(page.locator('h1', { hasText: '系统设置' }).first()).toBeVisible({ timeout: 20_000 })

    // 一次性收集所有折叠面板标题：分多次断言时，一旦某个分区没渲染，
    // 后面的分区根本不会被检查，问题会被前一个失败掩盖。
    await expect
      .poll(async () => (await page.locator(SECTION_HEADER).allTextContents()).map(t => t.trim()), { timeout: 20_000 })
      .toContain('安全设置')

    const headers = (await page.locator(SECTION_HEADER).allTextContents()).map(t => t.trim())
    const missing = SECTION_TITLES.filter(title => !headers.some(text => text.includes(title)))
    expect(
      missing,
      `缺少设置分区: ${missing.join(' / ')}；实际渲染: ${headers.join(' / ')}；浏览器报错: ${pageErrors.join(' | ') || '无'}`,
    ).toEqual([])
  })

  test('展开图片设置显示缩略图与预览图选项', async ({ page }) => {
    await page.goto('/settings?tab=basic')
    await expandSection(page, '图片设置')

    await expect(page.getByText('缩略图大小', { exact: true })).toBeVisible()
    await expect(page.getByText('缩略图质量', { exact: true })).toBeVisible()
    await expect(page.getByText('预览图大小', { exact: true })).toBeVisible()
  })

  test('展开外观设置显示显示模式与主题颜色', async ({ page }) => {
    await page.goto('/settings?tab=basic')
    await expandSection(page, '外观设置')

    await expect(page.getByRole('heading', { name: '显示模式' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '主题颜色' })).toBeVisible()
  })

  test('展开定时扫描与朋友圈文案分区显示各自表单', async ({ page }) => {
    await page.goto('/settings?tab=basic')
    await expandSection(page, '定时扫描设置')
    await expect(page.getByText('扫描模式', { exact: true })).toBeVisible()

    await expandSection(page, '朋友圈文案定时生成设置')
    await expect(page.getByText('生成模式', { exact: true })).toBeVisible()
  })

  test('展开回收站与索引维护分区显示保留天数与重建索引', async ({ page }) => {
    await page.goto('/settings?tab=basic')
    await expandSection(page, '回收站设置')
    await expect(page.getByText('保留天数', { exact: true })).toBeVisible()

    await expandSection(page, '索引维护')
    await expect(page.getByText('重建索引', { exact: true })).toBeVisible()
  })

  test('展开照片查看分区显示自动查看原图开关', async ({ page }) => {
    await page.goto('/settings?tab=basic')
    await expandSection(page, '照片查看')

    await expect(page.getByText('自动查看原图', { exact: true })).toBeVisible()
  })

  test('照片与数据位置页在浏览器端给出桌面端提示', async ({ page }) => {
    await page.goto('/settings?tab=data-directory')

    await expect(page.getByRole('heading', { name: '照片与数据位置' })).toBeVisible({ timeout: 20_000 })
    await expect(page.getByText('请在行影集桌面客户端中管理本机照片位置', { exact: false })).toBeVisible()
  })
})
