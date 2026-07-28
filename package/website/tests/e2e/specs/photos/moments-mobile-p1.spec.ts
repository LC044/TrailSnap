import { test, expect } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'
import { requirePhotos } from '../../helpers/data-probe'

/**
 * P1 - 朋友圈布局 · 移动端 UX（/photos?layout=moments）
 *
 * 回归本次会话对朋友圈布局在移动端的三项改动，防止后续再改 CSS/虚拟列表估算
 * 时又出现"按钮不见 / 无提示 / day-block 重叠"三类历史 Bug：
 *   1) 按钮组常显：桌面端 hover 才显示（md:opacity-0），移动端因无 hover 需常驻可见
 *   2) 无 EXIF 时间的兜底提示：整天照片都缺 photo_time 时，前端显示琥珀色说明
 *      并隐藏"AI 生成"按钮（后端必定报错），但保留"手动写"按钮
 *   3) day-block 不重叠：虚拟列表 bottomSpacing 在移动端 = 72px（vs 桌面 32px），
 *      覆盖按钮组常显 + mb-10/mb-4/mt-2 三处新增间距共 ~40px；不加会出现下一天
 *      的日期头覆盖上一天的按钮/文案
 *
 * 数据前置：至少 1 张照片。切换到朋友圈布局后触发 /api/moments/day-captions 等接口，
 * 不依赖 AI 模型是否配置（AI 生成失败提示的分类文案属于错误路径，需要真实 LLM 报错
 * 才能稳定复现，不在本 spec 覆盖范围内）。
 */

test.describe('P1 - 朋友圈布局 · 移动端 UX', () => {
  // iPhone 12 mini 尺寸，落在 tailwind sm/md 断点以下（< 640 触发虚拟列表 mobile 分支；
  // < 768 触发按钮组常显）。与 UnifiedPhotoPage.vue 中 isMobile = width < 768 对齐。
  test.use({ viewport: { width: 390, height: 844 } })

  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo))) return
  })

  /**
   * 通用步骤：进入照片页 → 打开视图设置 → 切到"朋友圈"布局 → 等第一组卡片渲染出来。
   * moments 布局下 UnifiedPhotoPage 会触发 useMomentCaptions.fetchDayCaptionsForRange，
   * 但即便未生成 caption，PhotoGallery 也会渲染每个 day-block（含 avatar / 昵称 / 占位文案）。
   */
  async function enterMomentsLayout(page: import('@playwright/test').Page) {
    await page.goto('/photos')

    // 视图设置菜单入口（UnifiedPhotoPage.vue: title="视图设置"）
    const viewOptionsBtn = page.getByTitle('视图设置').first()
    await expect(viewOptionsBtn).toBeVisible({ timeout: 15_000 })
    await viewOptionsBtn.click()

    // 布局模式 → 朋友圈
    const momentsBtn = page.locator('button', { hasText: '朋友圈' }).first()
    await expect(momentsBtn).toBeVisible({ timeout: 5_000 })
    await momentsBtn.click()

    // 关掉菜单（点标题空白处），避免遮挡后续断言
    await page.mouse.click(10, 10)

    // 等第一张朋友圈卡片出现（PhotoGallery.vue 中 moments 分支：div.flex.gap-3.mb-10 md:mb-8）
    const firstMomentBlock = page.locator('.day-block').first()
    await expect(firstMomentBlock).toBeVisible({ timeout: 20_000 })
  }

  test('3.1.1 移动端按钮组常显 - 无需 hover 即可看到「AI 生成 / 手动写」', async ({ page, request }, testInfo) => {
    const probe = await requirePhotos(request, testInfo, 1, 50)
    if (!probe.ok) return
    await enterMomentsLayout(page)

    // group/caption 容器内的按钮组：桌面端 md:opacity-0 隐形，移动端应该 opacity: 1
    // 用 filter 精准锁定"包含 AI 生成 或 手动写 的按钮组容器"
    const captionActionRow = page.locator('.day-block .group\\/caption > div.relative.z-20')
      .filter({ hasText: /AI\s*生成|手动写|重新生成|编辑/ })
      .first()
    await expect(captionActionRow).toBeVisible({ timeout: 10_000 })

    // 关键：opacity 必须为 1（原来的 opacity-0 是桌面 hover 才 opacity-100）
    const opacity = await captionActionRow.evaluate((el) => getComputedStyle(el).opacity)
    expect(parseFloat(opacity)).toBeGreaterThan(0.9)

    // 至少应有一个可点击的操作按钮（AI 生成 / 手动写 / 编辑 / 重新生成之一）
    const anyActionBtn = captionActionRow.locator('button').first()
    await expect(anyActionBtn).toBeVisible({ timeout: 5_000 })
  })

  test('3.1.2 无 EXIF 拍摄时间的一天 - 显示琥珀色提示并隐藏 AI 生成按钮', async ({ page, request }, testInfo) => {
    const probe = await requirePhotos(request, testInfo, 1, 200)
    if (!probe.ok) return

    // 从探测到的照片中，查有没有整天照片都缺 photo_time 的一组
    // photo_time 字段在探测返回结构中，缺失即 undefined/null
    const missingTimePhoto = probe.photos.find((p: any) => !p.photo_time)
    if (!missingTimePhoto) {
      testInfo.skip(true, 'No photo without photo_time in current dataset; skip amber-hint regression.')
      return
    }

    await enterMomentsLayout(page)

    // 前端琥珀色提示文案：见 PhotoGallery.vue 模板
    // "这一天的照片没有拍摄时间（EXIF 缺失），AI 无法自动生成文案。你可以点右边的「编辑」手动写一段。"
    // 该提示只在 caption 尚未生成 且 dayHasPhotoTime(day.key) === false 时出现
    const amberHint = page.locator('.day-block').getByText(/没有拍摄时间.*EXIF/).first()

    // 兜底：数据集里可能存在 photo_time 缺失的照片，但当天还有别的照片带 photo_time，
    // 这样 dayHasPhotoTime 为 true，前端不会渲染琥珀提示 —— 允许 skip
    const hasHint = await amberHint.isVisible({ timeout: 15_000 }).catch(() => false)
    if (!hasHint) {
      testInfo.skip(true, 'Missing-photo_time photo exists but its day has at least one dated photo; hint not triggered.')
      return
    }

    // 断言 1：琥珀色（text-amber-600 / text-amber-500）—— 用 computed color 校验偏红黄
    const color = await amberHint.evaluate((el) => getComputedStyle(el as HTMLElement).color)
    // rgb(180, 83, 9) = amber-600, rgb(245, 158, 11) = amber-500；R 分量应显著大于 B
    const m = color.match(/rgb[a]?\((\d+),\s*(\d+),\s*(\d+)/)
    expect(m, `expect rgb() color, got: ${color}`).not.toBeNull()
    const [r, g, b] = [Number(m![1]), Number(m![2]), Number(m![3])]
    expect(r).toBeGreaterThan(b + 50)
    expect(r).toBeGreaterThan(g)

    // 断言 2：该 day-block 内不出现"AI 生成"按钮，但"手动写"按钮存在
    const dayBlock = page.locator('.day-block').filter({ has: amberHint }).first()
    await expect(dayBlock.locator('button', { hasText: /^AI\s*生成$/ })).toHaveCount(0)
    await expect(dayBlock.locator('button', { hasText: /手动写|编辑/ }).first()).toBeVisible({ timeout: 5_000 })
  })

  test('3.1.3 虚拟列表估算 - 相邻 day-block 不重叠', async ({ page, request }, testInfo) => {
    // 需要至少 2 天的照片才有相邻 day-block 可比。若数据集只有 1 天，skip。
    const probe = await requirePhotos(request, testInfo, 2, 100)
    if (!probe.ok) return

    // 判断有 ≥2 个不同日期
    const dayKeys = new Set<string>()
    for (const p of probe.photos as any[]) {
      const ts = p.photo_time || p.upload_time
      if (!ts) continue
      const d = new Date(ts)
      if (!isNaN(d.getTime())) {
        dayKeys.add(`${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`)
        if (dayKeys.size >= 2) break
      }
    }
    if (dayKeys.size < 2) {
      testInfo.skip(true, 'Need at least 2 distinct days to assert non-overlap; dataset has only one day.')
      return
    }

    await enterMomentsLayout(page)

    // 至少两个 day-block 都渲染进 DOM（可能需要一点时间以让虚拟列表初始化多个块）
    const blocks = page.locator('.day-block')
    for (let i = 0; i < 10; i++) {
      if ((await blocks.count()) >= 2) break
      await page.waitForTimeout(500)
    }
    const count = await blocks.count()
    expect(count, 'need at least 2 day-blocks rendered').toBeGreaterThanOrEqual(2)

    // 采集所有 day-block 的 [top, top+height]，按 top 排序后检查两两不重叠
    const rects = await blocks.evaluateAll((els) =>
      els.map((el) => {
        const r = (el as HTMLElement).getBoundingClientRect()
        return { top: r.top, bottom: r.bottom }
      }),
    )
    rects.sort((a, b) => a.top - b.top)

    // 允许 1px 浮点/亚像素误差；虚拟列表的 bottomSpacing 在移动端 = 72，正常情况下两块间距远大于 0
    for (let i = 1; i < rects.length; i++) {
      const prev = rects[i - 1]
      const curr = rects[i]
      expect(
        curr.top,
        `day-block #${i} (top=${curr.top}) overlaps with previous block bottom=${prev.bottom}`,
      ).toBeGreaterThanOrEqual(prev.bottom - 1)
    }
  })
})
