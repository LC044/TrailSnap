import { expect, test, type Page, type Route } from '@playwright/test'

const response = (data: unknown) => ({ code: 0, message: 'success', data })

const searchResult = {
  id: 'r-1',
  total: 2,
  filters: {
    start_date: '2026-01-01',
    end_date: '2026-01-31',
    location: '三亚',
    person_ids: [],
    people_match: 'any',
    description: '海边',
    ocr_text: '',
    tags: [],
    min_people: null,
    max_people: null,
  },
}

const photos = [
  {
    id: 'photo-1',
    owner_id: 'u-e2e',
    file_type: 'image',
    photo_time: '2026-01-15T10:00:00Z',
    upload_time: '2026-01-15T10:05:00Z',
    url: '/api/medias/photo-1/file',
    thumbnail_url: '/api/medias/photo-1/thumbnail',
    width: 1,
    height: 1,
    size: 1,
  },
  {
    id: 'photo-2',
    owner_id: 'u-e2e',
    file_type: 'image',
    photo_time: '2026-01-16T11:00:00Z',
    upload_time: '2026-01-16T11:05:00Z',
    url: '/api/medias/photo-2/file',
    thumbnail_url: '/api/medias/photo-2/thumbnail',
    width: 1,
    height: 1,
    size: 1,
  },
]

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

function mockStaticAgentApis(page: Page) {
  void page.route('**/api/agent/sessions**', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(response([
      { id: 's-search', title: '三亚海边照片', is_pinned: true, created_at: '2026-01-20T10:00:00Z', updated_at: '2026-01-20T10:30:00Z' },
    ])),
  }))
  void page.route('**/api/agent/proactive**', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(response({ messages: [], unread: 0 })),
  }))
  void page.route('**/api/settings/models**', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(response({ connections: [] })),
  }))
  void page.route('**/api/medias/**', route => route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64'),
  }))
}

function mockSearchMessage(page: Page) {
  void page.route('**/api/agent/sessions/s-search/messages**', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(response([
      {
        id: 1,
        role: 'assistant',
        content: '为你找到了 2 张照片。',
        content_ext: { search_results: [searchResult] },
      },
    ])),
  }))
}

async function openSearchResults(page: Page) {
  await page.goto('/')
  const agentEntry = page.locator('.ai-assistant-button')
  await expect(agentEntry).toBeVisible({ timeout: 10_000 })
  await agentEntry.click()
  await expect(page.locator('.agent-chat-overlay')).toBeVisible({ timeout: 10_000 })

  const menuButton = page.locator('.agent-chat-overlay .agent-chat-header button').first()
  await menuButton.dispatchEvent('click')
  await expect(page.locator('.agent-sidebar')).toBeVisible()
  await page.locator('.agent-sidebar .session-item').first().click()

  await expect(page.getByRole('region', { name: '照片搜索结果' })).toBeVisible({ timeout: 10_000 })
}

test.describe('Nightly view coverage — AgentPhotoSearchResults @views-coverage', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test('renders result metadata, filters, photos, and completion state', async ({ page }) => {
    await useFakeSession(page)
    mockStaticAgentApis(page)
    mockSearchMessage(page)
    void page.route('**/api/agent/search-results/r-1/photos**', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(response({ total: 2, next_offset: null, photos })),
    }))

    await openSearchResults(page)

    await expect(page.getByText('搜索结果 · 2 张')).toBeVisible()
    await expect(page.getByText('已加载 2 张')).toBeVisible()
    await expect(page.getByText('2026-01-01 至 2026-01-31 · 三亚 · 海边')).toBeVisible()
    await expect(page.getByText('画面按相似度匹配，结果可能存在偏差')).toBeVisible()
    await expect(page.getByText('已显示全部搜索结果')).toBeVisible()
  })

  test('renders an actionable empty state', async ({ page }) => {
    await useFakeSession(page)
    mockStaticAgentApis(page)
    mockSearchMessage(page)
    void page.route('**/api/agent/search-results/r-1/photos**', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(response({ total: 0, next_offset: null, photos: [] })),
    }))

    await openSearchResults(page)

    await expect(page.getByText('搜索结果 · 0 张')).toBeVisible()
    await expect(page.getByText('未找到符合条件的照片，可以继续补充或调整条件。')).toBeVisible()
  })

  test('shows an error and recovers on retry', async ({ page }) => {
    await useFakeSession(page)
    mockStaticAgentApis(page)
    mockSearchMessage(page)
    let failed = false
    await page.route('**/api/agent/search-results/r-1/photos**', async route => {
      if (!failed) {
        failed = true
        await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ code: 500, message: 'search failed' }) })
        return
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(response({ total: 2, next_offset: null, photos })),
      })
    })

    await openSearchResults(page)
    await expect(page.getByRole('region', { name: '照片搜索结果' }).getByRole('alert')).toContainText('加载搜索结果失败，请重试')
    await page.getByRole('button', { name: '重试' }).click()

    await expect(page.getByText('搜索结果 · 2 张')).toBeVisible()
    await expect(page.getByText('已显示全部搜索结果')).toBeVisible()
  })
})

