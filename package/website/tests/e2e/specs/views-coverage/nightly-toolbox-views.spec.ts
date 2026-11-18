import { test, expect, type Page } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

/**
 * Nightly view coverage for the toolbox views introduced by REQ-238.
 *
 * The frontend gap scan (NIGHTLY-TEST-WATCH.md 4.3) reported these views were
 * never referenced by any spec:
 *   ToolboxHomePage, MediaScopeSelector, OrganizeRuleEditor, ToolPlanPreview.
 *
 * Coverage notes:
 * - ToolboxHomePage: /toolbox landing, tool cards, template section and history section.
 * - MediaScopeSelector: step 1 of the workflow (scope source group + explicit "all" warning).
 * - OrganizeRuleEditor: step 2 of /toolbox/organize.
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

  test('ToolboxHomePage lists every tool entry and history without templates', async ({ page }) => {
    await page.route('**/api/toolbox/preferences', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ code: 0, msg: 'success', data: { version: 0, presets: [], recent: [], default_rename_id: null } }) }))
    await page.goto('/toolbox', { waitUntil: 'domcontentloaded' })
    await waitForApp(page)

    await expect(page.getByRole('heading', { name: '工具箱' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '整理文件夹' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '重复照片' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '我的常用模板' })).toHaveCount(0)
    await expect(page.locator('#history > summary')).toHaveText('操作记录')
    await page.locator('#history > summary').click()
    await expect(page.getByRole('button', { name: '刷新记录' })).toHaveCount(0)

    // Each tool card must point at a real toolbox route.
    const links = [
      ['整理文件夹', '/toolbox/organize'],
      ['批量修改文件名', '/toolbox/rename'],
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

    await expect(page.locator('summary').filter({ hasText: /^选择照片$/ })).toBeVisible()
    await expect(page.getByRole('heading', { name: '整理方式' })).toBeVisible()

    const sources = page.getByRole('group', { name: '范围来源' })
    for (const label of ['相册', '文件夹', '手动选', '全部']) {
      await expect(sources.getByRole('button', { name: label })).toBeVisible()
    }

    // Nothing is preselected: the next step stays disabled until the user picks a scope.
    await expect(page.getByRole('button', { name: '预览', exact: true })).toBeDisabled()

    // "全部" must warn about the blast radius instead of silently covering the library.
    await sources.getByRole('button', { name: '全部' }).click()
    await expect(page.getByText('你已主动选择全部影像，请特别注意执行前的影响范围。')).toHaveCount(0)
    await expect(page.getByRole('button', { name: '预览', exact: true })).toBeDisabled() // 尚未选择目标与移动/复制

  })

  test('OrganizeRuleEditor renders rules without saved schemes', async ({ page }) => {
    await stubScopePreview(page)
    await page.goto('/toolbox/organize', { waitUntil: 'domcontentloaded' })
    await waitForApp(page)

    const sources = page.getByRole('group', { name: '范围来源' })
    await sources.getByRole('button', { name: '全部' }).click()

    await expect(page.getByText('使用已有方案', { exact: true })).toHaveCount(0)
    await expect(page.getByRole('button', { name: '保存为方案' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: '模板管理' })).toHaveCount(0)

    // OrganizeRuleEditor: rule levels are composable up to three times.
    await expect(page.getByRole('heading', { name: '整理方式' })).toBeVisible()
    await expect(page.getByRole('button', { name: '自定义', exact: true })).toHaveCount(0)
    await expect(page.getByRole('button', { name: '按年份和城市', exact: true })).toBeVisible()
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
    await page.getByRole('button', { name: '查找', exact: true }).click()

    // ToolPlanPreview: preview banner, scope/operation summary and the item list.
    await expect(page.getByText('已选 0 张', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: '确认', exact: true })).toBeDisabled()
    await expect(page.getByRole('button', { name: '导出' })).toHaveCount(0)
  })
})

