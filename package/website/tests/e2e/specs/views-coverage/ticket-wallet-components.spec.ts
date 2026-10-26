import { expect, test, type Page, type Route } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

/**
 * Nightly view coverage —— 票夹子组件（ticket/components）。
 *
 * 2026-10-24 的前端盲区扫描把 `src/views/ticket/components/` 下的组件全部列为盲区。
 * 排查后发现两种情况：
 *
 * 1. 真正的盲区（没有任何 spec 锁住其渲染 / 交互）：
 *    - TicketWalletPreview   ：相册列表页顶部的票夹预览（src/views/album/AlbumList.vue 挂载）
 *    - TicketDetailDialog    ：票夹详情弹窗（TicketPage.vue 挂载）
 *    - TicketAssociationDialog：详情弹窗里的「关联相册或回忆」二级弹窗
 *    - TicketThumbnail / WalletTicketCard：卡片缩略图与卡片主体
 * 2. 名字看着像盲区、实际是死代码（src 下零引用，E2E 无法触达）：
 *    - TicketList.vue / TicketFilterBar.vue / TicketCityStatsModal.vue / TicketPaperModal.vue
 *    这四个组件没有任何 import，永远不会渲染 —— 属于维护债，不是测试债。
 *
 * 本文件覆盖第 1 类。
 */

const TICKET = {
  key: 'train:tk-nightly-1',
  id: 'tk-nightly-1',
  type: 'train',
  title: '国庆回家',
  code: 'G1',
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
  memories: [],
  candidates: [],
}

const CONTEXT = { id: 'album-nightly-1', title: '十月旅行相册', kind: 'album' }

function ok(data: unknown) {
  return {
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ code: 0, msg: 'success', data }),
  }
}

/** 票夹相关接口的公共 stub。 */
async function stubTicketWallet(page: Page, options: { tickets?: unknown[]; contexts?: unknown[] } = {}) {
  const tickets = options.tickets ?? [TICKET]
  const contexts = options.contexts ?? [CONTEXT]
  await page.route('**/api/ticket-wallet**', async (route: Route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    const method = route.request().method()
    if (path === '/api/ticket-wallet' && method === 'GET') {
      return route.fulfill(ok({ items: tickets, total: tickets.length }))
    }
    if (path === '/api/ticket-wallet/contexts' && method === 'GET') {
      return route.fulfill(ok({ items: contexts, total: contexts.length }))
    }
    if (path === '/api/ticket-wallet/links' && method === 'POST') {
      return route.fulfill(ok({ linked: true }))
    }
    if (/\/api\/ticket-wallet\/[^/]+\/[^/]+$/.test(path) && method === 'GET') {
      return route.fulfill(ok(TICKET))
    }
    return route.fulfill(ok(null))
  })
  // 里程/时长是可选增强，失败不应阻塞票夹本身。
  await page.route('**/api/railway/stats/batch', route =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 0, msg: 'success', data: [] }) }),
  )
}

test.describe('Nightly view coverage —— 票夹子组件 @views-coverage', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo))) return
  })

  test('TicketWalletPreview 在相册列表页渲染票夹卡片', async ({ page }) => {
    await stubTicketWallet(page)
    await page.goto('/album')

    const section = page.locator('section', { has: page.getByRole('button', { name: '票夹' }) }).first()
    await expect(section).toBeVisible({ timeout: 20_000 })
    // WalletTicketCard 的主按钮 aria-label 是「火车票 <标题> <车次> · <时间>」
    await expect(section.getByRole('button', { name: /火车票 国庆回家 G1/ })).toBeVisible()
    await expect(section.getByText('国庆回家')).toBeVisible()
    await expect(section.getByRole('link', { name: '查看全部' })).toHaveAttribute('href', '/ticket')
  })

  test('TicketWalletPreview 没有票据时给出空态与新增入口', async ({ page }) => {
    await stubTicketWallet(page, { tickets: [] })
    await page.goto('/album')

    const section = page.locator('section', { has: page.getByRole('button', { name: '票夹' }) }).first()
    await expect(section).toBeVisible({ timeout: 20_000 })
    await expect(section.getByText('留下一张票据，找回一段经历')).toBeVisible()
    await expect(section.getByRole('link', { name: '新增票据' })).toHaveAttribute('href', '/ticket?add=true')
  })

  test('TicketDetailDialog 打开票据详情并可进入关联经历弹窗', async ({ page }) => {
    await stubTicketWallet(page)
    await page.goto('/ticket')

    await page.getByRole('button', { name: /火车票 国庆回家 G1/ }).first().click()

    const dialog = page.locator('section[role="dialog"]').first()
    await expect(dialog.getByRole('heading', { name: '火车票详情' })).toBeVisible({ timeout: 15_000 })
    await expect(dialog.getByRole('heading', { name: '国庆回家' })).toBeVisible()
    await expect(dialog.getByText('火车票 · G1')).toBeVisible()

    await dialog.getByRole('button', { name: '关联相册或回忆' }).click()

    // TicketAssociationDialog 是第二个弹窗
    const association = page.locator('section[role="dialog"]').last()
    await expect(association.getByRole('heading', { name: '关联经历' })).toBeVisible()
    await expect(association.getByPlaceholder('搜索名称')).toBeVisible()
    await expect(association.getByRole('button', { name: '相册' })).toBeVisible()
    await expect(association.getByRole('button', { name: '回忆' })).toBeVisible()
  })

  test('TicketAssociationDialog 选择相册后提交关联请求', async ({ page }) => {
    const linkBodies: unknown[] = []
    await stubTicketWallet(page)
    page.on('request', request => {
      if (request.method() === 'POST' && request.url().endsWith('/api/ticket-wallet/links')) {
        linkBodies.push(JSON.parse(request.postData() || '{}'))
      }
    })
    await page.goto('/ticket')

    await page.getByRole('button', { name: /火车票 国庆回家 G1/ }).first().click()
    const dialog = page.locator('section[role="dialog"]').first()
    await expect(dialog.getByRole('heading', { name: '火车票详情' })).toBeVisible({ timeout: 15_000 })
    await dialog.getByRole('button', { name: '关联相册或回忆' }).click()

    const association = page.locator('section[role="dialog"]').last()
    await expect(association.getByRole('heading', { name: '关联经历' })).toBeVisible()
    await expect(association.getByText('十月旅行相册')).toBeVisible()

    await association.getByRole('checkbox').first().check()
    const saveButton = association.getByRole('button', { name: '关联 1 项' })
    await expect(saveButton).toBeEnabled()
    await saveButton.click()

    await expect.poll(() => linkBodies.length).toBeGreaterThan(0)
    expect(linkBodies[0]).toMatchObject({
      tickets: [{ type: 'train', id: TICKET.id }],
      context_kind: 'album',
      context_id: CONTEXT.id,
    })
    await expect(page.getByText('关联已保存')).toBeVisible()
  })
})
