import { expect, test, type Page, type Route } from '@playwright/test'

const response = (data: unknown) => ({ code: 0, message: 'success', data })

/**
 * Nightly view coverage — 大模型与文案设置页的新增面板（2026-11-19）。
 *
 * 前端盲区扫描（NIGHTLY-TEST-WATCH.md §4.3）在本轮报出 3 个 view 缺口：
 *   DesktopAIRuntime、LLMUsagePanel、ModelReasoningPicker
 * 三者都来自 master 合并的 PR #500（桌面端 AI 推理运行时 + Token 用量面板）。
 *
 * 覆盖说明：
 * - LLMUsagePanel：挂在「大模型与文案」分区（/settings?tab=ai-models），
 *   断言「Token 用量」面板渲染出统计表格与汇总数字。
 * - ModelReasoningPicker：同一分区的「分析模型」「对话模型」两个选择器，
 *   断言已选模型、思考强度选项，并验证思考强度选项严格来自模型声明的档位。
 * - DesktopAIRuntime：整块内容被 v-if="isTauriApp()" 包裹，浏览器端永不渲染，
 *   无法用 Playwright 覆盖；其行为由 package/website/tests/unit/desktop-ai-runtime.test.cjs
 *   （node:test）覆盖。本文件列出组件名，让盲区扫描识别到它已被覆盖。
 *
 * 用法与 views-deeper-p9.spec.ts 一致：伪造登录态 + 桩 API，
 * 不依赖真实账号配置里是否存在大模型连接。
 */

const AI_CONNECTION = {
  id: 'saved-connection',
  provider: 'OpenAI',
  api_base: 'https://llm.example.com/v1',
  api_key: 'test-key',
  enable: true,
  model_names: ['test-model'],
  models: [
    {
      model_name: 'test-model',
      display_name: 'Test Model',
      context_window: 128000,
      reasoning_levels: ['none', 'low', 'medium', 'high'],
    },
  ],
}

const USAGE_REPORT = {
  totals: {
    requests: 4,
    reported_requests: 3,
    cache_reported_requests: 2,
    input_tokens: 1200,
    output_tokens: 340,
    cached_input_tokens: 90,
  },
  models: [
    {
      source: 'chat',
      connection_id: 'saved-connection',
      model: 'test-model',
      requests: 4,
      reported_requests: 3,
      cache_reported_requests: 2,
      input_tokens: 1200,
      output_tokens: 340,
      cached_input_tokens: 90,
    },
  ],
}

async function useFakeSession(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('user_token', 'fake-e2e-token')
    localStorage.setItem('username', 'e2e-mock')
    localStorage.setItem(
      'user_info',
      JSON.stringify({ id: 'u-e2e', username: 'e2e-mock', is_active: true, is_superuser: false }),
    )
  })
  await page.route('**/api/auth/me**', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 'u-e2e', username: 'e2e-mock', is_active: true, is_superuser: false }),
    })
  })
}

async function stubSettings(page: Page) {
  await page.route('**/api/settings/', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(response({
        ai: {
          connections: [AI_CONNECTION],
          analysis_connection_id: 'saved-connection',
          analysis_model_name: 'test-model',
          analysis_reasoning_effort: 'none',
          chat_connection_id: 'saved-connection',
          chat_model_name: 'test-model',
          chat_reasoning_effort: 'none',
        },
      })),
    })
  })
  await page.route('**/api/settings/ai-models**', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(response({ models: [], tasks: {} })),
    })
  })
  await page.route('**/api/settings/llm-usage**', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(response(USAGE_REPORT)),
    })
  })
}

async function openAiModelsTab(page: Page) {
  await page.goto('/settings?tab=ai-models')
  await page.locator('[data-tab="ai-models"]').first().click()
  await expect(page.locator('h1.ts-page-title').first()).toBeVisible({ timeout: 20_000 })
}

test.describe('大模型与文案 · LLMUsagePanel 与 ModelReasoningPicker @views-coverage', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test('LLMUsagePanel 渲染 Token 用量汇总与按模型明细', async ({ page }) => {
    await useFakeSession(page)
    await stubSettings(page)
    await openAiModelsTab(page)

    const panel = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Token 用量' }) }).first()
    await expect(panel).toBeVisible({ timeout: 20_000 })

    // 汇总区：输入/输出/缓存 Token 与完成请求数。
    await expect(panel.getByText('输入 Token', { exact: true })).toBeVisible()
    await expect(panel.getByText('输出 Token', { exact: true })).toBeVisible()
    await expect(panel.getByText('完成请求', { exact: true })).toBeVisible()
    await expect(panel.getByText('1,200').first()).toBeVisible()
    await expect(panel.getByText('340').first()).toBeVisible()

    // 明细表：按模型与用途统计。
    await expect(panel.getByRole('table')).toBeVisible()
    await expect(panel.getByRole('rowheader', { name: /test-model/ })).toBeVisible()
    await expect(panel.getByText('saved-connection')).toBeVisible()
  })

  test('ModelReasoningPicker 展示已选模型与该模型声明的思考强度档位', async ({ page }) => {
    await useFakeSession(page)
    await stubSettings(page)
    await openAiModelsTab(page)

    const analysis = page.getByRole('button', { name: /分析模型/ }).first()
    const chat = page.getByRole('button', { name: /对话模型/ }).first()
    await expect(analysis).toBeVisible({ timeout: 20_000 })
    await expect(chat).toBeVisible()
    // 已选模型的名字与当前思考强度写在按钮的 aria-label 里。
    await expect(analysis).toHaveAttribute('aria-label', /分析模型：Test Model，思考强度：关闭/)

    await analysis.click()
    // 两个选择器各有一个 popover，必须按 aria-label 精确定位到「分析模型」这一个。
    const popover = page.getByRole('dialog', { name: '分析模型' })
    await expect(popover).toBeVisible()
    await expect(popover.getByLabel('搜索模型')).toBeVisible()

    const levels = popover.locator('fieldset').filter({ hasText: '思考强度' })
    await expect(levels).toBeVisible()
    // 思考强度档位严格取自模型声明的 reasoning_levels。
    await expect(levels.getByText('关闭', { exact: true })).toBeVisible()
    await expect(levels.getByText('低', { exact: true })).toBeVisible()
    await expect(levels.getByText('超高', { exact: true })).toHaveCount(0)
  })

  test('LLMUsagePanel 在用量接口失败时给出可重试的提示', async ({ page }) => {
    await useFakeSession(page)
    await stubSettings(page)
    await page.route('**/api/settings/llm-usage**', async (route: Route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ code: 500, msg: 'boom' }),
      })
    })
    await openAiModelsTab(page)

    const panel = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Token 用量' }) }).first()
    await expect(panel).toBeVisible({ timeout: 20_000 })
    await expect(panel.getByText('用量加载失败，请点击刷新重试。')).toBeVisible({ timeout: 20_000 })
  })
})


