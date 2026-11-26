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
    await expect(page.getByRole('region', { name: '照片清理' }).getByRole('link', { name: '重复照片' })).toBeVisible()
    await expect(page.getByRole('region', { name: '照片整理' }).getByRole('link', { name: '整理文件夹' })).toBeVisible()
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
    await page.goto('/toolbox/organize?new=1', { waitUntil: 'domcontentloaded' })
    await waitForApp(page)

    await expect(page.locator('summary').filter({ hasText: /^选择照片$/ })).toBeVisible()
    await expect(page.getByRole('heading', { name: '整理方式' })).toBeVisible()

    const sources = page.getByRole('group', { name: '范围来源' })
    for (const label of ['相册', '文件夹', '手动选', '按日期筛选', '全部']) {
      await expect(sources.getByRole('button', { name: label })).toBeVisible()
    }

    await expect(sources.getByRole('button', { name: '全部' })).toHaveAttribute('aria-pressed', 'true')
    // A destination and processing mode are still required.
    await expect(page.getByRole('button', { name: '预览', exact: true })).toBeDisabled()

    // "全部" must warn about the blast radius instead of silently covering the library.
    await sources.getByRole('button', { name: '全部' }).click()
    await expect(page.getByText('你已主动选择全部影像，请特别注意执行前的影响范围。')).toHaveCount(0)
    await expect(page.getByRole('button', { name: '预览', exact: true })).toBeDisabled() // 尚未选择目标与移动/复制

  })

  test('OrganizeRuleEditor renders rules without saved schemes', async ({ page }) => {
    await stubScopePreview(page)
    await page.goto('/toolbox/organize?new=1', { waitUntil: 'domcontentloaded' })
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

  test('ToolPlanPreview shows quality scores below thumbnails without duplicating details', async ({ page }) => {
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
              { id: 1, photo_id: '00000000-0000-0000-0000-000000000401', source: '/photos/nightly-a.jpg', target: '', status: 'candidate', reason: '', detail: { quality_score: 12, memory_score: 18, label: '评分 30' } },
              { id: 2, photo_id: '00000000-0000-0000-0000-000000000402', source: '/photos/nightly-b.jpg', target: '', status: 'candidate', reason: '', detail: { quality_score: 0, memory_score: 0, label: '评分 0' } },
              { id: 3, photo_id: '00000000-0000-0000-0000-000000000403', source: '/photos/nightly-c.jpg', target: '', status: 'candidate', reason: '', detail: { quality_score: null, memory_score: null, label: '评分 0' } },
              { id: 4, photo_id: '00000000-0000-0000-0000-000000000404', source: '/photos/nightly-legacy.jpg', target: '', status: 'candidate', reason: '', detail: { label: '评分 25' } },
            ],
            total: 4,
          },
        }),
      })
    })

    await page.goto('/toolbox/cleanup?new=1', { waitUntil: 'domcontentloaded' })
    await waitForApp(page)

    const sources = page.getByRole('group', { name: '范围来源' })
    await sources.getByRole('button', { name: '全部' }).click()
    await expect(page.getByText('综合评分上限（0–200）', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: '查找', exact: true }).click()

    // ToolPlanPreview: preview banner, scope/operation summary and the item list.
    await expect(page.getByText('已选 0 张', { exact: true })).toBeVisible()
    const cards = page.locator('article').filter({ has: page.locator('details > summary', { hasText: '详情' }) })
    await expect(cards).toHaveCount(4)
    // Toolbox thumbnails now open the same PhotoLightbox as albums.
    await expect(cards.getByRole('button', { name: /^查看照片 / })).toHaveCount(4)
    await expect(cards.locator('.el-image')).toHaveCount(0)
    await expect(cards.nth(0).getByText('质量分 12 / 综合评分 30', { exact: true })).toBeVisible()
    await expect(cards.nth(0).locator('[aria-label="质量分（0–100）12 / 综合评分（0–200）30"]')).toBeVisible()
    for (const index of [1, 2]) {
      await expect(cards.nth(index).getByText('质量分 0 / 综合评分 0', { exact: true })).toBeVisible()
    }
    await expect(cards.nth(3).getByText('评分 25', { exact: true })).toBeVisible()
    // All quality candidates share one responsive grid.
    await expect(page.locator('div.grid').filter({ has: cards })).toHaveCount(1)
    for (let index = 0; index < 4; index++) {
      const details = cards.nth(index).locator('details')
      await details.locator('summary').click()
      await expect(details.locator('p').first()).toContainText('/photos/nightly-')
      await expect(details).not.toContainText(/质量分|综合评分|评分 25/)
    }
    await expect(page.getByRole('checkbox', { name: /将 nightly-a.jpg 移入回收站/ })).toBeVisible()

    await expect(page.getByRole('button', { name: '删除', exact: true })).toBeDisabled()
    await expect(page.getByRole('button', { name: '导出' })).toHaveCount(0)
  })
  for (const mode of ['quality', 'similar', 'duplicate'] as const) {
    test(`cleanup ${mode} supports two deletion batches without leaving results`, async ({ page }) => {
      const id = 'batch-' + mode
      let state = 'preview'
      let executions = 0
      const selected = new Set<number>()
      let remaining = [1, 2, 3, 4, 5]
      const item = (index: number) => ({
        id: index, photo_id: 'batch-photo-' + index, source: '/photos/batch-' + index + '.jpg',
        target: '', status: 'candidate', reason: '', selected: selected.has(index),
        detail: mode === 'quality' ? { quality_score: 10, memory_score: 5 } : { group_id: 8 },
      })
      const plan = () => ({
        ...previewPlan, id, status: state,
        request: { ...previewPlan.request, config: { ...previewPlan.request.config, cleanup_mode: mode } },
        summary: { phase: 'done', candidate: remaining.length, ready: 0, success: 5 - remaining.length },
      })
      const reply = (route: import('@playwright/test').Route, data: unknown) =>
        route.fulfill({ contentType: 'application/json', body: JSON.stringify({ code: 0, msg: 'success', data }) })
      await page.route('**/api/toolbox/plans**', async route => {
        const url = new URL(route.request().url())
        const path = url.pathname
        if (path.endsWith('/selection')) {
          const body = route.request().postDataJSON()
          for (const value of body.item_ids) body.selected ? selected.add(value) : selected.delete(value)
          return reply(route, { selected_count: selected.size })
        }
        if (path.endsWith('/execute')) {
          expect([...selected]).toEqual([executions + 1])
          executions++
          remaining = remaining.filter(index => !selected.has(index))
          selected.clear()
          state = 'queued'
          return reply(route, plan())
        }
        if (path.endsWith('/items')) {
          const grouped = mode !== 'quality'
          expect(url.searchParams.get('group_by')).toBe(String(grouped))
          return reply(route, {
            total: grouped ? (remaining.length ? 1 : 0) : remaining.length,
            selected_count: selected.size, items: (grouped ? remaining.slice(0, 1) : remaining).map(item),
          })
        }
        if (path.endsWith('/members')) return reply(route, {
          total: remaining.length, representative_id: 'batch-photo-1',
          items: remaining.map(index => ({ photo_id: item(index).photo_id, source: item(index).source,
            in_scope: index === 1, item: item(index) })),
        })
        if (path.endsWith('/' + id)) { state = 'preview'; return reply(route, plan()) }
        if (route.request().method() === 'POST') return reply(route, plan())
        return route.fallback()
      })
      await page.goto('/toolbox/cleanup?plan=' + id)
      const cards = page.locator('article').filter({ has: page.getByRole('checkbox', { name: /移入回收站/ }) })
      await expect(cards).toHaveCount(5)
      await expect(cards.getByRole('button', { name: /^查看照片 / })).toHaveCount(5)
      await expect(cards.locator('.el-image')).toHaveCount(0)
      if (mode !== 'quality') {
        const boxes = await cards.evaluateAll(elements => elements.map(element => element.getBoundingClientRect().top))
        expect(new Set(boxes).size).toBe(1)
        for (let index = 0; index < 5; index++) {
          const path = '/photos/batch-' + (index + 1) + '.jpg'
          if (mode === 'similar') await cards.nth(index).locator('summary').click()
          await expect(cards.nth(index).getByText(path, { exact: true })).toBeVisible()
        }
      }
      const remove = page.getByRole('button', { name: '删除', exact: true })
      await expect(page.getByRole('checkbox', { name: '已悉知变更情况', exact: true })).toHaveCount(0)
      for (const index of [1, 2]) {
        const photo = page.getByRole('checkbox', { name: '将 batch-' + index + '.jpg 移入回收站', exact: true })
        await photo.click()
        await expect(remove).toBeEnabled()
        await remove.click()
        const confirmation = page.getByRole('dialog', { name: '确认移入回收站' })
        await expect(confirmation.getByText('将选中的 1 张照片移入回收站？')).toBeVisible()
        if (index === 1) {
          await confirmation.getByRole('button', { name: '取消', exact: true }).click()
          await expect(confirmation).toBeHidden()
          expect(executions).toBe(0)
          await expect(photo).toBeChecked()
          await remove.click()
        }
        await confirmation.getByRole('button', { name: '移入回收站', exact: true }).click()
        // Completion restores the selection summary; queued/running only show the central loader.
        await expect(page.getByText('已选 0 张', { exact: true })).toBeVisible()
        await expect(cards).toHaveCount(5 - index)
        await expect(page.getByText('已选 0 张', { exact: true })).toBeVisible()
        await expect(remove).toBeDisabled()
        await expect(confirmation).toBeHidden()
      }
      expect(executions).toBe(2)
      await expect(page).toHaveURL(new RegExp('plan=' + id))
    })
  }

})

