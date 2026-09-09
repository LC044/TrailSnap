import { expect, test, type Route } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

const planId = '44444444-4444-4444-8444-444444444444'

const actionPlan = {
  id: planId,
  plan_type: 'organize_album',
  title: '整理杭州旅行照片',
  summary: '把西湖和灵隐寺照片放进旅行相册。',
  status: 'proposed',
  attempt_count: 1,
  error_message: null,
  preview: {
    mode: 'create',
    album_name: '杭州旅行',
    photo_count: 3,
    tags: ['西湖', '寺庙'],
    sample_photos: [],
    notice: '不会修改原文件',
    artifact_id: null,
  },
  result: {},
  created_at: '2026-09-10T08:00:00Z',
  updated_at: '2026-09-10T08:05:00Z',
  expires_at: '2026-09-11T08:00:00Z',
}

const aiSettings = {
  connections: [
    {
      id: 'builtin',
      provider: 'Built-in AI',
      api_base: 'builtin://ai',
      api_key: '',
      enable: true,
      model_names: ['builtin-vision'],
      models: [
        { model_name: 'builtin-vision', display_name: '内置视觉', context_window: 128000, reasoning_levels: ['none'] },
      ],
    },
  ],
  analysis_connection_id: 'builtin',
  analysis_model_name: 'builtin-vision',
  analysis_reasoning_effort: 'none',
  chat_connection_id: 'builtin',
  chat_model_name: 'builtin-vision',
  chat_reasoning_effort: 'none',
}

function respond(route: Route, data: unknown) {
  return route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ code: 0, message: 'success', data }),
  })
}

test.describe('P1 - ActionPlanDetail / LLMSettings @views-coverage', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo))) return

    await page.route('**/api/agent/proactive**', route => respond(route, { messages: [], unread: 0 }))
  })

  test('ActionPlanDetail 渲染方案卡与有效期', async ({ page }) => {
    await page.route('**/api/agent/actions/**', route => respond(route, actionPlan))

    await page.goto(`/agent/actions/${planId}`)
    await expect(page.getByRole('heading', { name: 'AI 相册操作方案' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '整理杭州旅行照片' })).toBeVisible()
    await expect(page.getByText('方案创建于').first()).toBeVisible()
    await expect(page.getByText('有效期至').first()).toBeVisible()
    await expect(page.getByRole('button', { name: '确认执行' })).toBeVisible()
  })

  test('ActionPlanDetail 加载失败后可重试', async ({ page }) => {
    let requests = 0
    await page.route('**/api/agent/actions/**', route => {
      requests += 1
      return route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ code: 1, message: 'server error' }) })
    })

    await page.goto(`/agent/actions/${planId}`)
    await expect(page.getByText('无法加载该方案')).toBeVisible()
    await page.getByRole('button', { name: '重新加载' }).click()
    await expect.poll(() => requests).toBe(2)
  })

  test('LLMSettings 渲染连接、默认模型与高级提示词', async ({ page }) => {
    await page.route('**/api/settings/ai-models', route => respond(route, { models: [], tasks: {} }))
    await page.route('**/api/settings/', async route => {
      const url = new URL(route.request().url())
      if (url.pathname === '/api/settings/' && route.request().method() === 'GET') return respond(route, { ai: aiSettings })
      return respond(route, {})
    })

    await page.goto('/settings#ai-models')
    await expect(page.getByRole('heading', { name: 'AI 模型管理' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '大模型连接与任务配置' })).toBeVisible()
    await expect(page.getByText('Built-in AI', { exact: true })).toBeVisible()
    await expect(page.getByText('已添加 1 个模型')).toBeVisible()
    await expect(page.getByText('内置视觉 · Built-in AI').first()).toBeVisible()
    await expect(page.getByRole('button', { name: '+ 添加连接' })).toBeVisible()
  })

  test('LLMSettings 可添加 OpenAI 兼容连接并保存模型', async ({ page }) => {
    const savedPayloads: any[] = []
    await page.route('**/api/settings/ai-models', route => respond(route, { models: [], tasks: {} }))
    await page.route('**/api/settings/', async route => {
      const url = new URL(route.request().url())
      if (url.pathname === '/api/settings/' && route.request().method() === 'PUT') {
        savedPayloads.push(route.request().postDataJSON())
        return respond(route, { ai: aiSettings })
      }
      if (url.pathname === '/api/settings/' && route.request().method() === 'GET') return respond(route, { ai: aiSettings })
      return respond(route, {})
    })

    await page.goto('/settings#ai-models')
    await page.getByRole('button', { name: '+ 添加连接' }).click()
    await expect(page.getByRole('dialog')).toContainText('添加大模型连接')

    await page.getByPlaceholder('https://api.openai.com/v1').fill('https://api.example.com/v1')
    await page.getByRole('button', { name: '+ 手动添加模型' }).click()
    const modelInput = page.getByRole('dialog').locator('.el-select input').nth(1)
    await modelInput.click()
    await modelInput.fill('qwen-max')
    await modelInput.press('Enter')
    await page.getByPlaceholder('显示名称（可选）').fill('Qwen Max')
    await page.getByRole('button', { name: '保存', exact: true }).click()

    await expect(page.getByText('大模型配置已保存')).toBeVisible()
    await expect.poll(() => savedPayloads.length).toBeGreaterThan(0)
    const saved = savedPayloads.at(-1)
    const connection = saved.ai.connections.find((item: any) => item.api_base === 'https://api.example.com/v1')
    expect(connection).toBeTruthy()
    expect(connection.provider).toBe('OpenAI')
    expect(connection.model_names).toEqual(['qwen-max'])
    expect(connection.models[0]).toMatchObject({ model_name: 'qwen-max', display_name: 'Qwen Max' })
  })
})
