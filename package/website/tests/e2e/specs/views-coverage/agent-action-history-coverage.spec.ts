import { expect, test, type Route } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

const proposedPlan = {
  id: '11111111-1111-4111-8111-111111111111',
  plan_type: 'organize_album',
  title: '整理武汉旅行照片',
  summary: '把武汉美食和夜景照片放进同一个相册。',
  status: 'proposed',
  attempt_count: 1,
  error_message: null,
  preview: {
    mode: 'create',
    album_name: '武汉旅行',
    photo_count: 3,
    tags: ['美食', '夜景'],
    sample_photos: [],
    notice: '不会修改原文件',
    artifact_id: null,
  },
  result: {},
  created_at: '2026-09-07T08:00:00Z',
  updated_at: '2026-09-07T08:00:00Z',
}

const executedPlan = {
  ...proposedPlan,
  id: '22222222-2222-4222-8222-222222222222',
  title: '整理西安旅行照片',
  summary: '把城墙和博物馆照片放进西安相册。',
  status: 'executed',
  preview: { ...proposedPlan.preview, mode: 'update', photo_count: 5, tags: [] },
  result: {
    album_url: '/album/1',
    artifact_url: '/agent/artifacts/33333333-3333-4333-8333-333333333333',
  },
  created_at: '2026-09-06T08:00:00Z',
}

function respond(route: Route, data: unknown) {
  return route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ code: 0, message: 'success', data }),
  })
}

test.describe('P1 - ActionHistory / AgentActionPlanCard @views-coverage', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo))) return

    await page.route('**/api/agent/proactive**', route => respond(route, { messages: [], unread: 0 }))
  })

  test('ActionHistory 渲染计划卡并按状态过滤', async ({ page }) => {
    const requests: string[] = []
    await page.route('**/api/agent/actions**', async route => {
      const url = new URL(route.request().url())
      if (url.pathname.endsWith('/actions')) {
        requests.push(url.searchParams.get('status') ?? 'all')
        return respond(route, url.searchParams.get('status') === 'executed' ? [executedPlan] : [proposedPlan, executedPlan])
      }
      return respond(route, url.pathname.endsWith(executedPlan.id) ? executedPlan : proposedPlan)
    })

    await page.goto('/agent/actions')
    await expect(page.getByRole('heading', { name: 'Agent 任务中心' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '整理武汉旅行照片' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '整理西安旅行照片' })).toBeVisible()
    await expect(page.getByText('等待确认').first()).toBeVisible()
    await expect(page.getByText('已执行').first()).toBeVisible()

    await page.getByRole('button', { name: '已执行' }).click()
    await expect(page.getByRole('heading', { name: '整理西安旅行照片' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '整理武汉旅行照片' })).toHaveCount(0)
    expect(requests).toEqual(['all', 'executed'])
  })

  test('ActionHistory 空列表渲染安全空态', async ({ page }) => {
    await page.route('**/api/agent/actions**', async route => {
      const url = new URL(route.request().url())
      if (url.pathname.endsWith('/actions')) return respond(route, [])
      return respond(route, proposedPlan)
    })

    await page.goto('/agent/actions')
    await expect(page.getByText('暂无符合条件的 Agent 操作')).toBeVisible()
    await expect(page.getByRole('button', { name: '刷新' })).toBeVisible()
  })

  test('AgentActionPlanCard 刷新后展示执行态操作', async ({ page }) => {
    await page.route('**/api/agent/actions**', async route => {
      const url = new URL(route.request().url())
      if (url.pathname.endsWith('/actions')) return respond(route, [proposedPlan])
      return respond(route, executedPlan)
    })

    await page.goto('/agent/actions')
    await expect(page.getByRole('heading', { name: '整理西安旅行照片' })).toBeVisible()
    await expect(page.getByRole('button', { name: '打开相册' })).toBeVisible()
    await expect(page.getByRole('button', { name: '撤销操作' })).toBeVisible()
    await expect(page.getByRole('button', { name: '查看旅行日志' })).toBeVisible()
    await expect(page.getByText('修改已撤销')).toHaveCount(0)
  })

  test('AgentActionPlanCard 确认执行后更新为已执行', async ({ page }) => {
    await page.route('**/api/agent/actions**', async route => {
      const url = new URL(route.request().url())
      if (url.pathname.endsWith('/execute')) return respond(route, executedPlan)
      if (url.pathname.endsWith('/actions')) return respond(route, [proposedPlan])
      return respond(route, proposedPlan)
    })

    await page.goto('/agent/actions')
    await page.getByRole('button', { name: '确认执行' }).click()
    await page.locator('.el-message-box').getByRole('button', { name: '确认执行' }).click()

    await expect(page.getByText('相册整理完成，可随时撤销')).toBeVisible()
    await expect(page.getByRole('button', { name: '打开相册' })).toBeVisible()
    await expect(page.getByRole('button', { name: '撤销操作' })).toBeVisible()
  })
})
