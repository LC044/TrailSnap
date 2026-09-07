import { expect, test, type Route } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

const artifactId = '33333333-3333-4333-8333-333333333333'

const artifact = {
  id: artifactId,
  user_id: '22222222-2222-4222-8222-222222222222',
  artifact_type: 'travel_story',
  title: '西安秋日旅行日志',
  content_json: {
    summary: '三天两夜的西安旅行。',
    sections: [
      {
        heading: '城墙黄昏',
        body: '傍晚沿着城墙走过一段安静的旅程。',
        photo_ids: ['11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222'],
      },
    ],
  },
  html_content: '<!doctype html><html><head><title>西安秋日</title></head><body><main><h1>HTML artifact works</h1></main></body></html>',
  html_config: { style_name: 'editorial', custom_style: '夏日公路电影', server_api_access: false },
  source_photo_ids: [],
  source_ticket_ids: [],
  status: 'draft',
  version: 2,
  created_by_session_id: null,
  created_at: '2026-09-05T08:00:00Z',
  updated_at: '2026-09-05T09:00:00Z',
}

function respond(route: Route, data: unknown) {
  return route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ code: 0, message: 'success', data }),
  })
}

test.describe('P1 - Agent ArtifactDetail / HtmlArtifactPreview @views-coverage', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo))) return

    await page.route('**/api/agent/proactive**', route => respond(route, { messages: [], unread: 0 }))
    await page.route('**/api/agent/artifacts/**', route => respond(route, artifact))
  })

  test('结构化草稿渲染并打开个性化页面设计器', async ({ page }) => {
    await page.goto(`/agent/artifacts/${artifactId}`)

    await expect(page.getByRole('heading', { name: '西安秋日旅行日志' })).toBeVisible()
    await expect(page.getByText('三天两夜的西安旅行。')).toBeVisible()
    await expect(page.getByRole('heading', { name: '城墙黄昏' })).toBeVisible()
    await expect(page.getByAltText('旅行照片')).toHaveCount(2)

    await page.getByRole('button', { name: '重新设计' }).click()
    await expect(page.getByRole('heading', { name: '让 Agent 设计这篇旅行日志' })).toBeVisible()
    await expect(page.getByRole('combobox')).toHaveValue('editorial')
    await expect(page.getByText('允许页面只读访问 Server API')).toBeVisible()
    await expect(page.getByRole('button', { name: '在 Agent 中生成' })).toBeVisible()
  })

  test('个性页面在沙箱 iframe 中渲染且源码可编辑', async ({ page }) => {
    await page.goto(`/agent/artifacts/${artifactId}?view=html`)

    const frame = page.frameLocator('iframe[title="西安秋日旅行日志 个性化页面"]')
    await expect(frame.getByRole('heading', { name: 'HTML artifact works' })).toBeVisible()
    await expect(page.locator('iframe[title="西安秋日旅行日志 个性化页面"]')).toHaveAttribute('sandbox', 'allow-scripts')

    await page.getByRole('button', { name: 'HTML 源码' }).click()
    await expect(page.locator('textarea')).toHaveValue(/HTML artifact works/)
  })

  test('没有 HTML 内容时提供空态且不显示源码入口', async ({ page }) => {
    await page.route('**/api/agent/artifacts/**', route => respond(route, { ...artifact, html_content: null }))

    await page.goto(`/agent/artifacts/${artifactId}`)
    await expect(page.getByRole('button', { name: '生成个性页面' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'HTML 源码' })).toHaveCount(0)

    await page.getByRole('button', { name: '个性页面', exact: true }).click()
    await expect(page.getByText('还没有个性化 HTML 页面')).toBeVisible()
  })

  test('作品加载失败时提示错误且不渲染编辑工具', async ({ page }) => {
    await page.route('**/api/agent/artifacts/**', route => route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ code: 1, message: 'server error' }),
    }))

    await page.goto(`/agent/artifacts/${artifactId}`)
    await expect(page.getByText('旅行日志加载失败')).toBeVisible()
    await expect(page.getByRole('button', { name: '编辑内容' })).toHaveCount(0)
  })
})
