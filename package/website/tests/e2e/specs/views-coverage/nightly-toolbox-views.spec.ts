import { test, expect, type Page } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

/**
 * Nightly view coverage for the toolbox views introduced by REQ-238.
 *
 * The frontend gap scan (NIGHTLY-TEST-WATCH.md 4.3) reported these views were
 * never referenced by any spec:
 *   ToolboxHomePage, MediaScopeSelector, ToolPresetBar, OrganizeRuleEditor, ToolPlanPreview.
 *
 * Coverage notes:
 * - ToolboxHomePage: /toolbox landing, tool cards, template section and history section.
 * - MediaScopeSelector: step 1 of the workflow (scope source group + explicit "all" warning).
 * - ToolPresetBar + OrganizeRuleEditor: step 2 of /toolbox/organize.
 * - ToolPlanPreview: step 3 of /toolbox/cleanup with the plan API stubbed, so no real
 *   file operation is triggered.
 *
 * The scope preview endpoint is stubbed so the workflow can advance to the rule step
 * without depending on scanned photo fixtures.
 */

/** Wait until the SPA finished booting (the splash screen is gone). */
async function waitForApp(page: Page) {
  await expect(page.locator('h1.ts-page-title').first()).toBeVisible({ timeout: 20_000 })
}

/** Stub the scope check so "next step" is reachable regardless of scanned fixtures. */
async function stubScopePreview(page: Page, total = 2) {
  await page.route('**/api/toolbox/scopes/preview**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0, msg: 'success',
        data: {
          items: [
            { id: '00000000-0000-0000-0000-000000000401', filename: 'nightly-a.jpg' },
            { id: '00000000-0000-0000-0000-000000000402', filename: 'nightly-b.jpg' },
          ].slice(0, total),
          total,
        },
      }),
    })
  })
}

const previewPlan = {
  id: 'nightly-preview-plan',
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
  summary: { total: 3, ready: 2, skipped: 1, failed: 0, success: 0 },
  task_id: null,
  created_at: '2026-11-11T00:00:00',
  expires_at: '2026-11-12T00:00:00',
  finished_at: null,
  stop_requested: false,
}

test.describe.serial('Nightly toolbox view coverage @views-coverage', () => {
  test.setTimeout(120_000)

  test.beforeEach(async ({ page, request }, testInfo) => {
    const token = await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' })
    if (!token) return
  })

  test('ToolboxHomePage lists every tool entry, templates and history', async ({ page }) => {
    await page.route('**/api/toolbox/preferences', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ code: 0, msg: 'success', data: { version: 0, presets: [], recent: [], default_rename_id: null } }) }))
    const preferencesResponse = page.waitForResponse(r => r.url().includes('/api/toolbox/preferences') && r.request().method() === 'GET')
    await page.goto('/toolbox', { waitUntil: 'domcontentloaded' })
    expect((await preferencesResponse).ok()).toBeTruthy()
    await waitForApp(page)

    await expect(page.getByRole('heading', { name: '工具箱' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '整理与命名' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '清理与修复' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '我的常用模板' })).toHaveCount(0)
    await expect(page.locator('#history > summary')).toHaveText('操作记录')
    await page.locator('#history > summary').click()
    await expect(page.getByRole('button', { name: '刷新记录' })).toBeVisible()

    // Each tool card must point at a real toolbox route.
    const links = [
      ['影像整理', '/toolbox/organize'],
      ['批量重命名', '/toolbox/rename'],
      ['重复照片', '/toolbox/duplicate'],
      ['相似照片', '/toolbox/similar'],
      ['低质量照片', '/toolbox/cleanup'],
      ['修正拍摄信息', '/toolbox/time-from-filename'],
    ] as const
    for (const [name, href] of links) {
      await expect(page.getByRole('link', { name: new RegExp(name) }).first()).toHaveAttribute('href', href)
    }
  })

  test('MediaScopeSelector requires an explicit scope choice before the next step', async ({ page }) => {
    await page.goto('/toolbox/organize', { waitUntil: 'domcontentloaded' })
    await waitForApp(page)

    await expect(page.getByRole('heading', { name: '这次处理哪些影像？' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '怎样整理？' })).toBeVisible()

    const sources = page.getByRole('group', { name: '范围来源' })
    for (const label of ['相册', '文件夹', '条件', '手动选', '全部']) {
      await expect(sources.getByRole('button', { name: label })).toBeVisible()
    }

    // Nothing is preselected: the next step stays disabled until the user picks a scope.
    await expect(page.getByRole('button', { name: '查看效果', exact: true })).toBeDisabled()

    // "全部" must warn about the blast radius instead of silently covering the library.
    await sources.getByRole('button', { name: '全部' }).click()
    await expect(page.getByText('你已主动选择全部影像，请特别注意执行前的影响范围。')).toBeVisible()
    await expect(page.getByRole('button', { name: '查看效果', exact: true })).toBeDisabled() // 尚未选择目标与移动/复制

  })

  test('ToolPresetBar and OrganizeRuleEditor render the rule step', async ({ page }) => {
    await stubScopePreview(page)
    await page.goto('/toolbox/organize', { waitUntil: 'domcontentloaded' })
    await waitForApp(page)

    const sources = page.getByRole('group', { name: '范围来源' })
    await sources.getByRole('button', { name: '全部' }).click()

    await page.getByText('使用已有方案（可选）', { exact: true }).click()
    // 已有方案按需展开，规则与范围同屏。
    await expect(page.getByText('选择保存的模板或整理方案')).toBeVisible()
    await expect(page.getByRole('button', { name: '保存为方案' })).toBeVisible()
    await expect(page.getByRole('button', { name: '更新所选' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: '模板管理' })).toBeVisible()

    // OrganizeRuleEditor: rule levels are composable up to three times.
    await expect(page.getByRole('heading', { name: '怎样整理？' })).toBeVisible()
    await page.getByRole('button', { name: '自定义', exact: true }).click()
    await expect(page.getByText('第 1 级')).toBeVisible()
    await page.getByRole('button', { name: '增加一级' }).click()
    await expect(page.getByText('第 2 级')).toBeVisible()
  })

  test('ToolPlanPreview shows the real-preview summary before execution', async ({ page }) => {
    await stubScopePreview(page)
    await page.route('**/api/toolbox/plans', async (route) => {
      if (route.request().method() !== 'POST') return route.fallback()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, msg: 'success', data: previewPlan }),
      })
    })
    await page.route('**/api/toolbox/plans/*/items**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0, msg: 'success',
          data: {
            items: [
              { id: 1, photo_id: '00000000-0000-0000-0000-000000000401', source: '/photos/nightly-a.jpg', target: '', status: 'ready', reason: '评分低于阈值', detail: { label: '模糊' } },
              { id: 2, photo_id: '00000000-0000-0000-0000-000000000402', source: '/photos/nightly-b.jpg', target: '', status: 'skipped', reason: '缺少分析结果', detail: {} },
            ],
            total: 2,
          },
        }),
      })
    })

    await page.goto('/toolbox/cleanup', { waitUntil: 'domcontentloaded' })
    await waitForApp(page)

    const sources = page.getByRole('group', { name: '范围来源' })
    await sources.getByRole('button', { name: '全部' }).click()
    await page.getByRole('button', { name: '查找候选照片', exact: true }).click()

    // ToolPlanPreview: preview banner, scope/operation summary and the item list.
    await expect(page.getByText('真实预览，尚未执行')).toBeVisible()
    await expect(page.getByText('修改范围或规则后，必须重新生成预览。文件已变化或目标被占用时将记录异常，不覆盖。')).toBeVisible()
    await expect(page.getByText('范围内 3 项 · 跳过 1 项')).toBeVisible()
    await expect(page.getByText('nightly-a.jpg', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: '导出清单' })).toBeVisible()
  })
})

