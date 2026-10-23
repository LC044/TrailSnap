import { expect, test, type Page } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

/**
 * Nightly view coverage — 系统设置分区（Settings.vue -> BasicSettings.vue）。
 *
 * 2026-10-23 的前端盲区扫描（路由反查 + 视图名匹配）把
 * `src/views/settings/sections/*.vue` 里的 11 个分区组件全部列为盲区。
 * 实际上它们都不是独立路由，而是被 `BasicSettings.vue` 一次性挂载的
 * `SettingsSection` 折叠面板（src/components/ui/SettingsSection.vue），
 * 因此只要打开 /settings?tab=basic，11 个分区标题就会一起渲染 ——
 * 这正是本文件要锁住的行为：任何一个分区没渲染出来都属于回归。
 *
 * 另外 `DesktopDataDirectory.vue` 虽然被标记为 desktopOnly，但
 * Settings.vue 的 isAvailable() 对 `requestedKey.value === item.key` 放行，
 * 所以浏览器端也能通过 /settings?tab=data-directory 进入。
 */

/** BasicSettings.vue 里 11 个分区折叠面板的标题（顺序与模板一致）。 */
const SECTION_TITLES = [
  '安全设置',
  '任务设置',
  '地图设置',
  'AI 服务与人脸设置',
  '图片设置',
  '照片查看',
  '定时扫描设置',
  '朋友圈文案定时生成设置',
  '回收站设置',
  '索引维护',
  '外观设置',
]

/** 展开某个折叠分区：el-collapse 的标题栏是 .el-collapse-item__header。 */
async function expandSection(page: Page, title: string) {
  const header = page.locator('.el-collapse-item__header', { hasText: title }).first()
  await header.scrollIntoViewIfNeeded()
  await header.click()
  await expect(header).toHaveClass(/is-active/)
}

test.describe('Nightly view coverage — 设置分区 @views-coverage', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo))) return
  })

  test('系统设置页挂载全部 11 个设置分区', async ({ page }) => {
    await page.goto('/settings?tab=basic')

    await expect(page.getByRole('heading', { name: '系统设置', level: 1 })).toBeVisible({ timeout: 20_000 })
    for (const title of SECTION_TITLES) {
      await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible()
    }
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
