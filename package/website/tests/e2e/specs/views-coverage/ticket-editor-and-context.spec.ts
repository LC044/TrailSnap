import { expect, test, type Page, type Route } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

/**
 * Nightly view coverage —— 票据新增表单与「相关票据」区块。
 *
 * 2026-10-25 的前端盲区扫描把 `src/views/ticket/components/` 下的三个组件列为盲区。
 * 排查后结论：
 *
 * 1. 真正的盲区（本文件覆盖）：
 *    - TicketEditorDialog：火车票 / 机票的新增表单，被 TicketFormModal 与
 *      FlightTicketFormModal 挂载，从 /ticket 的「新增票据」入口可达。
 *    - TicketContextSection：记忆详情页与相册详情页的「相关票据」区块。
 * 2. 维护债而非测试债：
 *    - TicketTypeSelectorModal.vue 在 src 下零引用（TicketPage.vue 自己内联了
 *      同样的类型选择弹窗），永远不会渲染，E2E 无法触达。
 */

const MEMORY_ID = 'mem-nightly-ticket-1'

const TICKET = {
  key: 'train:tk-nightly-ctx-1',
  id: 'tk-nightly-ctx-1',
  type: 'train',
  title: '十月回家',
  code: 'G1920',
  from: '北京南',
  to: '上海虹桥',
  date_time: '2026-10-01T08:00:00',
  price: 553,
  name: '张三',
  photo_id: null,
  distance: 1318,
  duration: 300,
  comments: '',
  albums: [],
  memories: [{ id: MEMORY_ID, title: '十月三日', kind: 'memory' }],
  candidates: [],
}

const MEMORY = {
  id: MEMORY_ID,
  status: 'confirmed',
  title: '十月三日回乡',
  cover_photo_id: null,
  start_time: '2026-10-01T09:00:00',
  end_time: '2026-10-03T18:00:00',
  photo_count: 0,
  places: [],
  people: [],
  evidence: [],
  photos: [],
  tickets: [],
  story: null,
  created_at: '2026-10-03T18:00:00',
  updated_at: '2026-10-03T18:00:00',
  confirmed_at: '2026-10-03T18:00:00',
}

/** TrailSnap 后端统一返回 BaseResponse：{ code, msg, data }。 */
function ok(data: unknown) {
  return {
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ code: 0, msg: 'success', data }),
  }
}

async function stubMemory(page: Page) {
  await page.route('**/api/memories/**', async (route: Route) => {
    await route.fulfill(ok(MEMORY))
  })
}

async function stubTicketWallet(page: Page, items: unknown[] = [TICKET]) {
  await page.route('**/api/ticket-wallet**', async (route: Route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/contexts')) {
      await route.fulfill(ok({ items: [], total: 0 }))
      return
    }
    if (route.request().method() !== 'GET') {
      await route.fulfill(ok(null))
      return
    }
    await route.fulfill(ok({ items, total: items.length }))
  })
}

test.describe('Nightly view coverage —— 票据新增表单 / 相关票据区块 @views-coverage', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo))) return
  })

  test('TicketEditorDialog 渲染火车票新增表单', async ({ page }) => {
    await page.goto('/ticket')

    await page.locator('[aria-label="新增票据"]').first().click()
    const typeDialog = page.getByRole('dialog').filter({ hasText: '新增票据' }).first()
    await expect(typeDialog).toBeVisible({ timeout: 15_000 })
    await typeDialog.getByRole('button', { name: '火车票' }).click()

    const editor = page.getByRole('dialog').filter({ hasText: '新增火车票' }).first()
    await expect(editor).toBeVisible({ timeout: 15_000 })
    await expect(editor.getByLabel('车次')).toBeVisible()
    await expect(editor.getByLabel('出发地')).toBeVisible()
    await expect(editor.getByLabel('目的地')).toBeVisible()
    await expect(editor.getByRole('button', { name: /上传票据图片/ })).toBeVisible()
  })

  test('TicketEditorDialog 渲染机票新增表单', async ({ page }) => {
    await page.goto('/ticket')

    await page.locator('[aria-label="新增票据"]').first().click()
    const typeDialog = page.getByRole('dialog').filter({ hasText: '新增票据' }).first()
    await expect(typeDialog).toBeVisible({ timeout: 15_000 })
    await typeDialog.getByRole('button', { name: '机票' }).click()

    const editor = page.getByRole('dialog').filter({ hasText: '新增机票' }).first()
    await expect(editor).toBeVisible({ timeout: 15_000 })
    await expect(editor.getByLabel('航班号')).toBeVisible()
    await expect(editor.getByLabel('出发地')).toBeVisible()
    await expect(editor.getByLabel('目的地')).toBeVisible()
  })

  test('TicketContextSection 在记忆详情展示相关票据', async ({ page }) => {
    await stubMemory(page)
    await stubTicketWallet(page)

    await page.goto(`/memories/${MEMORY_ID}`)

    const section = page.getByRole('button', { name: /相关票据/ }).first()
    await expect(section).toBeVisible({ timeout: 15_000 })
    await expect(section).toHaveText(/相关票据 · 1/)
    await expect(page.getByText('十月回家').first()).toBeVisible()
    // 「可编辑」形态下提供关联 / 新增入口
    await expect(page.getByRole('button', { name: '关联已有票据' })).toBeVisible()
  })

  test('TicketContextSection 可打开「选择票据」弹窗', async ({ page }) => {
    await stubMemory(page)
    await stubTicketWallet(page)

    await page.goto(`/memories/${MEMORY_ID}`)

    await page.getByRole('button', { name: '关联已有票据' }).click()

    const dialog = page.getByRole('dialog').filter({ hasText: '选择票据' }).first()
    await expect(dialog).toBeVisible({ timeout: 15_000 })
    await expect(dialog.getByLabel('搜索票据')).toBeVisible()
  })

  test('TicketContextSection 没有关联票据时给出空态', async ({ page }) => {
    await stubMemory(page)
    await stubTicketWallet(page, [])

    await page.goto(`/memories/${MEMORY_ID}`)

    await expect(page.getByRole('button', { name: /相关票据/ }).first()).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText('还没有关联票据')).toBeVisible()
  })
})



