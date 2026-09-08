import { expect, test, type Page, type Route } from '@playwright/test'

const response = (data: unknown) => ({ code: 0, message: 'success', data })

async function useFakeSession(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('user_token', 'fake-e2e-token')
    localStorage.setItem('username', 'e2e-mock')
    localStorage.setItem(
      'user_info',
      JSON.stringify({ id: 'u-e2e', username: 'e2e-mock', is_active: true, is_superuser: true }),
    )
  })
  await page.route('**/api/auth/me**', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 'u-e2e', username: 'e2e-mock', is_active: true, is_superuser: true }),
    })
  })
}

async function clickTab(page: Page, key: string) {
  await page.locator(`[data-tab="${key}"]`).first().click()
}

test.describe('AI desktop view contracts @views-coverage', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test('DesktopAIExtensions renders the unavailable desktop state', async ({ page }) => {
    await useFakeSession(page)
    await page.goto('/settings?tab=ai-extensions')
    await clickTab(page, 'ai-extensions')

    await expect(page.getByRole('heading', { name: 'AI 扩展包' })).toBeVisible()
    await expect(page.getByText('仅 TrailSnap 桌面版支持扩展包管理')).toBeVisible()
    await expect(page.getByText('当前页面未连接到桌面扩展管理接口。')).toBeVisible()
  })

  test('AIModelManagement renders models and the download action', async ({ page }) => {
    await useFakeSession(page)
    await page.route('**/api/settings/ai-models**', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(response({
          models: [{
            id: 'clip-test', name: '测试向量模型', status: 'pending',
            description: 'Nightly view contract', requirements: { memoryMB: 128 },
          }],
          tasks: {
            embedding: {
              name: '语义向量与搜索', selected: 'clip-test', available: ['clip-test'],
            },
          },
        })),
      })
    })
    await page.goto('/settings?tab=ai-models')
    await clickTab(page, 'ai-models')

    await expect(page.getByRole('heading', { name: 'AI 模型管理' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '语义向量与搜索' })).toBeVisible()
    await expect(page.getByRole('button', { name: '下载', exact: true })).toBeEnabled()
  })

  test('saved LLM connection can be opened for editing', async ({ page }) => {
    await useFakeSession(page)
    await page.route('**/api/settings/ai-models**', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(response({ models: [], tasks: {} })),
      })
    })
    await page.route('**/api/settings/', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(response({
          ai: {
            connections: [{
              id: 'saved-connection', provider: 'OpenAI', api_base: 'https://llm.example.com/v1',
              api_key: 'test-key', enable: true, model_names: ['test-model'],
              models: [{ model_name: 'test-model', display_name: 'Test Model', context_window: 128000, reasoning_levels: ['none', 'high'] }],
            }],
            analysis_connection_id: 'saved-connection', analysis_model_name: 'test-model', analysis_reasoning_effort: 'none',
            chat_connection_id: 'saved-connection', chat_model_name: 'test-model', chat_reasoning_effort: 'none',
          },
        })),
      })
    })

    await page.goto('/settings?tab=ai-models')
    await clickTab(page, 'ai-models')
    const connectionCard = page.locator('article', { hasText: 'https://llm.example.com/v1' })
    await expect(connectionCard).toBeVisible()
    await connectionCard.getByRole('button', { name: '编辑' }).click()

    const dialog = page.getByRole('dialog', { name: '编辑大模型连接' })
    await expect(dialog).toBeVisible()
    await expect(dialog.getByPlaceholder('https://api.openai.com/v1')).toHaveValue('https://llm.example.com/v1')
    await expect(dialog.getByText('test-model', { exact: true })).toBeVisible()
  })
})
