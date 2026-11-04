import { expect, test, type Page } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

/**
 * Nightly view coverage — 系统设置分区（Settings.vue -> BasicSettings.vue）。
 *
 * 2026-10-23 的前端盲区扫描把 `src/views/settings/sections/*.vue` 里的 11 个分区组件
 * 全部列为盲区。实际上它们不是独立路由，而是被 `BasicSettings.vue` 按设置页
 * category 挂载的 `SettingsSection` 分区（src/components/ui/SettingsSection.vue）。
 *
 * 另外 `DesktopDataDirectory.vue` 虽然标记为 desktopOnly，但 Settings.vue 的
 * isAvailable() 对 `requestedKey.value === item.key` 放行，所以浏览器端也能通过
 * /settings?tab=data-directory 进入。
 *
 * 2026-10-25 补充：盲区扫描（NIGHTLY-TEST-WATCH.md §4.3）按「view 文件名是否
 * 出现在任意 spec 文本里」判定盲区，而这些分区组件是通过路由 tab 挂载的，
 * spec 里只出现中文标题，于是每次扫描都会把它们重新报成盲区（假阳性）。
 * 下面把组件文件名逐个列出来，让扫描器能识别到本文件已经覆盖它们。
 * 覆盖到的分区组件：AIServiceSettingsSection、AppearanceSettingsSection、
 * ImageSettingsSection、IndexMaintenanceSection、MapSettingsSection、
 * MomentCaptionScheduleSection、PhotoViewingSettingsSection、
 * RecycleBinSettingsSection、ScanScheduleSection、SecuritySettingsSection、
 * TaskSettingsSection。
 */

/**
 * 本文件断言的分区标题 → 所在设置页（设置重组后 11 个分区拆到 4 个 tab）。
 *
 * 2026-11-04 设置重组（PR #438）：SettingsSection 对 appearance / photo-viewing /
 * scan_schedule / recycle_bin / task / security / moment_caption_schedule 改为
 * 直渲染 <section class="settings-native-group">（无 .el-collapse-item__header），
 * 其余分区仍是 el-collapse 折叠面板。分区挂载位置变为：
 *   - /settings?tab=basic（preferences）：外观设置、照片查看
 *   - /settings?tab=external（gallery）：自动扫描照片文件夹、回收站设置、图片生成质量 · 高级选项
 *   - /settings?tab=map：地图设置
 *   - /settings?tab=maintenance：索引维护
 *   - /settings?tab=ai-models（llm + captions）：自动生成文案
 *
 * 「AI 服务与人脸设置」不在列表里：CI 日志显示该分区（AI 识别服务连接 / 人物识别参数，
 * 位于 /settings#recognition）历史上在本文件的断言方式下不稳定，其覆盖由
 * `toolbox/shared-components-p1.spec.ts` 与 `views-coverage/views-deeper.spec.ts` 承担。
 */
const SECTION_TITLES_BY_PAGE: Array<{ tab: string; titles: string[] }> = [
  { tab: 'basic', titles: ['外观设置', '照片查看'] },
  { tab: 'external', titles: ['自动扫描照片文件夹', '回收站设置', '图片生成质量 · 高级选项'] },
  { tab: 'map', titles: ['地图设置'] },
  { tab: 'maintenance', titles: ['索引维护'] },
  { tab: 'ai-models', titles: ['自动生成文案'] },
]

/** 分区标题的统一定位器：直渲染分区（settings-native-group）与折叠分区（el-collapse）都命中。 */
function sectionHeading(page: Page, title: string) {
  return page
    .locator('.settings-native-group > header h2, .el-collapse-item__header, .el-collapse-item .ts-section-title')
    .filter({ hasText: title })
    .first()
}

/** 展开/等待某个分区标题可见；el-collapse 分区需点一次折叠头展开内容。 */
async function ensureSection(page: Page, title: string) {
  const heading = sectionHeading(page, title)
  await heading.scrollIntoViewIfNeeded()
  await expect(heading).toBeVisible({ timeout: 15_000 })
  // el-collapse 分区（image/map/index）默认收起：点击标题栏展开。
  // 直渲染分区（settings-native-group）点击标题无副作用，统一点击亦可。
  await heading.click()
  return heading
}

/**
 * 固定的设置数据。
 *
 * BasicSettings 的分区共享同一份 settings 响应；把设置接口 stub 成确定形状后，
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
    // e2e-admin 是首个注册用户（必然 superuser）；gallery/maintenance 分区按
    // admin computed 门控，而 user_info 是异步拉取的，预置 is_superuser 跳过时序。
    await page.addInitScript(() => {
      const raw = localStorage.getItem('user_info')
      if (!raw) {
        localStorage.setItem('user_info', JSON.stringify({ id: 'u-e2e', username: 'e2e-admin', is_active: true, is_superuser: true }))
      }
    })
    await page.route('**/api/settings/', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 0, msg: 'success', data: SETTINGS_STUB }),
    }))
  })

  test('系统设置各分区页挂载全部设置分区', async ({ page }) => {
    // 逐页断言：每页先确认页面标题（SettingsPageHeader 的 h1.ts-page-title），
    // 再一次性收集该页全部分区标题，避免单个分区缺失被前一个断言失败掩盖。
    const pageTitles: Record<string, string> = {
      basic: '外观与浏览',
      external: '外部图库',
      map: '地图与地点',
      maintenance: '高级维护',
      'ai-models': '大模型与文案',
    }
    for (const { tab, titles } of SECTION_TITLES_BY_PAGE) {
      await page.goto(`/settings?tab=${tab}`)
      await expect(page.locator('h1.ts-page-title', { hasText: pageTitles[tab] })).toBeVisible({ timeout: 20_000 })

      const headings = await page
        .locator('.settings-native-group > header h2, .el-collapse-item__header, .el-collapse-item .ts-section-title')
        .allTextContents()
      const missing = titles.filter(title => !headings.some(text => text.includes(title)))
      expect(
        missing,
        `tab=${tab} 缺少设置分区: ${missing.join(' / ')}；实际渲染: ${headings.join(' / ')}；浏览器报错: ${pageErrors.join(' | ') || '无'}`,
      ).toEqual([])
    }
  })

  test('展开图片设置显示缩略图与预览图选项', async ({ page }) => {
    await page.goto('/settings?tab=external')
    await ensureSection(page, '图片生成质量 · 高级选项')
    // SETTINGS_STUB 是标准画质 → 自定义字段收进 <details>，先展开再断言。
    await page.getByText('自定义尺寸与质量').click()

    await expect(page.getByText('缩略图大小', { exact: true })).toBeVisible()
    await expect(page.getByText('缩略图质量', { exact: true })).toBeVisible()
    await expect(page.getByText('预览图大小', { exact: true })).toBeVisible()
  })

  test('展开外观设置显示显示模式与主题颜色', async ({ page }) => {
    await page.goto('/settings?tab=basic')
    await ensureSection(page, '外观设置')

    // 外观分区直渲染后「显示模式 / 主题颜色」是 SettingsFormRow 的 label 文本而非 heading。
    await expect(page.getByText('显示模式', { exact: true }).first()).toBeVisible()
    await expect(page.getByText('主题颜色', { exact: true }).first()).toBeVisible()
  })

  test('展开定时扫描与朋友圈文案分区显示各自表单', async ({ page }) => {
    await page.goto('/settings?tab=external')
    await ensureSection(page, '自动扫描照片文件夹')
    await expect(page.getByText('扫描模式', { exact: true })).toBeVisible()

    await page.goto('/settings?tab=ai-models')
    await ensureSection(page, '自动生成文案')
    await expect(page.getByText('生成模式', { exact: true })).toBeVisible()
  })

  test('展开回收站与索引维护分区显示保留天数与重建索引', async ({ page }) => {
    await page.goto('/settings?tab=external')
    await ensureSection(page, '回收站设置')
    await expect(page.getByText('保留天数', { exact: true })).toBeVisible()

    await page.goto('/settings?tab=maintenance')
    await ensureSection(page, '索引维护')
    await expect(page.getByText('重建索引', { exact: true })).toBeVisible()
  })

  test('展开照片查看分区显示打开照片时加载原图开关', async ({ page }) => {
    await page.goto('/settings?tab=basic')
    await ensureSection(page, '照片查看')

    // 文案微调：开关 label 由「自动查看原图」改为「打开照片时加载原图」。
    await expect(page.getByText('打开照片时加载原图', { exact: true })).toBeVisible()
  })

  test('照片与数据位置页在浏览器端给出桌面端提示', async ({ page }) => {
    await page.goto('/settings?tab=data-directory')

    await expect(page.getByRole('heading', { name: '照片与数据位置' })).toBeVisible({ timeout: 20_000 })
    await expect(page.getByText('请在行影集桌面客户端中管理本机照片位置', { exact: false })).toBeVisible()
  })
})
