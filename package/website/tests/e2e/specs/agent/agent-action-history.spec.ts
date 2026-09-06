import { expect, test, type Route } from '@playwright/test'

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
  test.beforeEach(async ({ page }) => {
    // These UI-contract tests mock every relevant Agent endpoint and only need
    // a token-shaped value to pass the client-side route guard.
    await page.context().addInitScript(() => localStorage.setItem('user_token', 'e2e-mocked-agent-token'))
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
    await expect(page.getByLabel('Agent 操作计划').getByText('已执行', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: '打开相册' })).toBeVisible()
    await expect(page.getByRole('button', { name: '撤销操作' })).toBeVisible()

    await page.getByRole('button', { name: '撤销操作' }).click()
    await page.locator('.el-message-box').getByRole('button', { name: '确认撤销' }).click()
    await expect(page.getByText('修改已撤销')).toBeVisible()
    await expect(page.getByRole('button', { name: '查看旅行日志' })).toBeVisible()
  })

  test('相册医生修复计划可调整范围、确认执行并撤销', async ({ page }) => {
    const repairPlan: any = {
      ...structuredClone(plan),
      id: '77777777-7777-4777-8777-777777777777',
      plan_type: 'album_repair',
      title: '修复相册：西安秋日',
      summary: '准备修复 1 个相册中的 2 项结构问题。',
      preview: {
        mode: 'repair',
        repair_count: 2,
        candidate_count: 2,
        affected_album_count: 1,
        selected_repair_ids: ['album_count:album-1', 'album_cover:album-1'],
        repairs: [
          { id: 'album_count:album-1', kind: 'album_count', album_id: 'album-1', album_name: '西安秋日', before: 9, after: 3, label: '修正“西安秋日”的照片计数：9 → 3' },
          { id: 'album_cover:album-1', kind: 'album_cover', album_id: 'album-1', album_name: '西安秋日', before: null, after: 'photo-1', reason: '当前没有封面', label: '为“西安秋日”设置推荐封面' },
        ],
        notice: '只修正相册计数和封面引用，不修改原始照片。',
      },
    }
    let current = structuredClone(repairPlan)
    let patchedIds: string[] = []
    await page.route('**/api/agent/actions**', async (route) => {
      const request = route.request()
      const path = new URL(request.url()).pathname
      if (request.method() === 'GET' && path === '/api/agent/actions') return respond(route, [current])
      if (request.method() === 'GET' && path.endsWith(`/${repairPlan.id}`)) return respond(route, current)
      if (request.method() === 'PATCH' && path.endsWith(`/${repairPlan.id}`)) {
        patchedIds = JSON.parse(request.postData() || '{}').selected_repair_ids
        current = { ...current, preview: { ...current.preview, selected_repair_ids: patchedIds, repair_count: patchedIds.length } }
        return respond(route, current)
      }
      if (request.method() === 'POST' && path.endsWith(`/${repairPlan.id}/execute`)) {
        current = { ...current, status: 'executed', result: { applied_repair_count: patchedIds.length, affected_album_count: 1 } }
        return respond(route, current)
      }
      if (request.method() === 'POST' && path.endsWith(`/${repairPlan.id}/undo`)) {
        current = { ...current, status: 'undone' }
        return respond(route, current)
      }
      await route.fallback()
    })

    await page.goto('/agent/actions')
    await expect(page.getByText('2 / 2 项')).toBeVisible()
    await page.getByLabel('为“西安秋日”设置推荐封面').uncheck()
    await expect(page.getByRole('button', { name: '保存选择' })).toBeVisible()
    await page.getByRole('button', { name: '确认执行' }).click()
    await page.locator('.el-message-box').getByRole('button', { name: '确认执行' }).click()
    expect(patchedIds).toEqual(['album_count:album-1'])
    await expect(page.getByLabel('Agent 操作计划').getByText('已执行', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: '打开相册' })).toHaveCount(0)

    await page.getByRole('button', { name: '撤销操作' }).click()
    await page.locator('.el-message-box').getByRole('button', { name: '确认撤销' }).click()
    await expect(page.getByText('修改已撤销')).toBeVisible()
  })

  test('相册医生后台补齐计划展示进度与复检且不提供撤销', async ({ page }) => {
    const metadataPlan: any = {
      ...structuredClone(plan),
      id: '88888888-8888-4888-8888-888888888888',
      plan_type: 'album_metadata_repair',
      title: '补齐相册 AI 数据',
      status: 'executed',
      preview: {
        mode: 'metadata_repair',
        repair_count: 2,
        candidate_count: 2,
        photo_count: 5,
        reversible: false,
        selected_repair_ids: ['metadata_description', 'metadata_hash'],
        repairs: [
          { id: 'metadata_description', kind: 'visual_description', label: '生成缺失的 AI 视觉描述', count: 3, queued_count: 3 },
          { id: 'metadata_hash', kind: 'file_hash', label: '计算缺失的文件指纹', count: 2, queued_count: 2 },
        ],
        notice: '确认后创建后台任务，不修改原始文件。',
      },
      result: { queued_item_count: 5, reversible: false },
    }
    await page.route('**/api/agent/actions**', async (route) => {
      const path = new URL(route.request().url()).pathname
      if (path.endsWith(`/${metadataPlan.id}/progress`)) return respond(route, {
        plan_id: metadataPlan.id,
        status: 'completed', total_items: 5, completed_items: 5,
        remaining_items: 0, failed_tasks: 0, progress_percent: 100,
        groups: [
          { kind: 'visual_description', label: '生成缺失的 AI 视觉描述', status: 'completed', total_items: 3, completed_items: 3, remaining_items: 0, active_tasks: 0, failed_tasks: 0 },
          { kind: 'file_hash', label: '计算缺失的文件指纹', status: 'completed', total_items: 2, completed_items: 2, remaining_items: 0, active_tasks: 0, failed_tasks: 0 },
        ],
        recheck: { missing_description: 0, missing_hash: 0 },
      })
      if (route.request().method() === 'GET' && path === '/api/agent/actions') return respond(route, [metadataPlan])
      if (route.request().method() === 'GET' && path.endsWith(`/${metadataPlan.id}`)) return respond(route, metadataPlan)
      await route.fallback()
    })

    await page.goto('/agent/actions')
    await expect(page.getByText('后台补齐')).toBeVisible()
    await expect(page.getByText('复检完成').first()).toBeVisible()
    await expect(page.getByText('5 / 5')).toBeVisible()
    await expect(page.getByRole('button', { name: '撤销操作' })).toHaveCount(0)
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

  test('相册页可启动回忆侦探并先询问线索', async ({ page }) => {
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
      body: 'data: {"content":"你大概记得是什么时间吗？"}\n\ndata: [DONE]\n\n',
    }))

    await page.goto('/album')
    const chatRequest = page.waitForRequest(request => request.url().endsWith('/api/agent/chat') && request.method() === 'POST')
    await page.getByRole('button', { name: '回忆侦探' }).click()
    const payload = JSON.parse((await chatRequest).postData() || '{}')

    await expect(page.locator('.agent-chat-overlay')).toBeVisible()
    expect(payload.message).toContain('memory-detective')
    expect(payload.message).toContain('最有区分度的问题')
    expect(payload.message).toContain('不要把推断当成事实')
  })

  test('人物详情页可启动人物时光机', async ({ page }) => {
    const identityId = '55555555-5555-4555-8555-555555555555'
    const photoId = '66666666-6666-4666-8666-666666666666'
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
      body: `data: {"content":"我先整理跨年份时间线。\\n\\n![代表照片](https://untrusted.example/api/medias/${photoId}/thumbnail)"}\n\ndata: [DONE]\n\n`,
    }))
    await page.route('**/api/faces/identities**', route => {
      const path = new URL(route.request().url()).pathname
      if (path.endsWith(`/${identityId}/photos`)) return respond(route, [])
      return respond(route, [{
        id: identityId,
        identity_name: '小周',
        face_count: 3,
        is_hidden: false,
        is_deleted: false,
      }])
    })

    await page.goto(`/album/people/${identityId}`)
    const chatRequest = page.waitForRequest(request => request.url().endsWith('/api/agent/chat') && request.method() === 'POST')
    await page.getByRole('button', { name: '人物时光机' }).click()
    const payload = JSON.parse((await chatRequest).postData() || '{}')

    await expect(page.locator('.agent-chat-overlay')).toBeVisible()
    expect(payload.message).toContain('person-timeline')
    expect(payload.message).toContain(`identity_id=${identityId}`)
    expect(payload.message).toContain('不要臆测人物关系')
    await expect(page.locator('.agent-chat-overlay img.agent-gallery-image')).toHaveAttribute(
      'src',
      new RegExp(`/api/medias/(?:[^/]+/)?${photoId}/thumbnail`),
    )
    await expect(page.locator('.agent-chat-overlay')).not.toContainText('untrusted.example')
  })
})
