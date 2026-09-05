import { expect, test, type Route } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

const plan = {
  id: '11111111-1111-4111-8111-111111111111',
  user_id: '22222222-2222-4222-8222-222222222222',
  session_id: null,
  plan_type: 'album_organize',
  title: '整理相册：西安秋日',
  summary: '将 3 张照片整理为旅行相册。',
  status: 'proposed',
  attempt_count: 0,
  error_message: null,
  operations: {},
  preview: {
    mode: 'create',
    album_name: '西安秋日',
    photo_count: 3,
    cover_photo_id: null,
    tags: ['西安', '旅行'],
    artifact_id: '33333333-3333-4333-8333-333333333333',
    artifact_title: '西安秋日旅行日志',
    artifact_url: '/agent/artifacts/33333333-3333-4333-8333-333333333333',
    sample_photos: [],
    notice: '只创建或更新相册关系和标签，不删除、移动或重命名原始照片。',
  },
  undo_data: null,
  result: null,
  created_at: '2026-09-05T08:00:00Z',
  updated_at: '2026-09-05T08:00:00Z',
  expires_at: '2026-09-12T08:00:00Z',
  executed_at: null,
  failed_at: null,
  undone_at: null,
}

function respond(route: Route, data: unknown) {
  return route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ code: 0, message: 'success', data }),
  })
}

test.describe('P1.1 - Agent 操作审计 @agent-action-history', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo))) return
  })

  test('列表加载 -> 确认执行 -> 撤销，保留旅行日志入口', async ({ page }) => {
    let current: any = structuredClone(plan)

    await page.route('**/api/agent/actions**', async (route) => {
      const request = route.request()
      const url = new URL(request.url())
      const path = url.pathname
      if (request.method() === 'GET' && path === '/api/agent/actions') {
        await respond(route, [current])
      } else if (request.method() === 'GET' && path.endsWith(`/${plan.id}`)) {
        await respond(route, current)
      } else if (request.method() === 'POST' && path.endsWith(`/${plan.id}/execute`)) {
        current = {
          ...current,
          status: 'executed',
          attempt_count: 1,
          executed_at: '2026-09-05T08:05:00Z',
          result: {
            album_id: '44444444-4444-4444-8444-444444444444',
            album_url: '/album/44444444-4444-4444-8444-444444444444',
            album_name: '西安秋日',
            added_photo_count: 3,
            artifact_id: plan.preview.artifact_id,
            artifact_url: plan.preview.artifact_url,
          },
        }
        await respond(route, current)
      } else if (request.method() === 'POST' && path.endsWith(`/${plan.id}/undo`)) {
        current = { ...current, status: 'undone', undone_at: '2026-09-05T08:06:00Z' }
        await respond(route, current)
      } else {
        await route.fallback()
      }
    })

    await page.goto('/agent/actions')
    await expect(page.getByRole('heading', { name: '操作记录' })).toBeVisible()
    await expect(page.getByText('整理相册：西安秋日')).toBeVisible()
    await expect(page.getByRole('button', { name: '查看旅行日志' })).toBeVisible()

    await page.getByRole('button', { name: '确认执行' }).click()
    await page.locator('.el-message-box').getByRole('button', { name: '确认执行' }).click()
    await expect(page.getByText('已执行', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: '打开相册' })).toBeVisible()
    await expect(page.getByRole('button', { name: '撤销操作' })).toBeVisible()

    await page.getByRole('button', { name: '撤销操作' }).click()
    await page.locator('.el-message-box').getByRole('button', { name: '确认撤销' }).click()
    await expect(page.getByText('修改已撤销')).toBeVisible()
    await expect(page.getByRole('button', { name: '查看旅行日志' })).toBeVisible()
  })

  test('相册页可一键启动只读相册体检', async ({ page }) => {
    await page.route('**/api/agent/proactive**', route => respond(route, { messages: [], unread: 0 }))
    await page.route('**/api/settings/models**', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ connections: [] }),
    }))
    await page.route('**/api/agent/sessions**', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    }))
    await page.route('**/api/agent/chat', route => route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: 'data: {"content":"体检已启动"}\n\ndata: [DONE]\n\n',
    }))

    await page.goto('/album')
    const chatRequest = page.waitForRequest(request => request.url().endsWith('/api/agent/chat') && request.method() === 'POST')
    await page.getByRole('button', { name: 'AI 相册体检' }).click()
    const payload = JSON.parse((await chatRequest).postData() || '{}')

    await expect(page.locator('.agent-chat-overlay')).toBeVisible()
    expect(payload.message).toContain('album-doctor')
    expect(payload.message).toContain('只读体检')
    expect(payload.message).toContain('不要删除')
  })
})
