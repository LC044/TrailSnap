import { expect, test, type Page, type Route } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

/**
 * Nightly view coverage — memories / daily-frame / chapter / location sub-pages.
 *
 * The 2026-10-22 frontend gap scan (route-table reverse lookup, not a blind
 * substring match) found these routed views that no existing spec touched:
 *
 *   explore/RelationsPage            /explore/relations
 *   daily-frame/DailyFramePage       /daily-frame
 *   daily-frame/FilmCreatePage       /daily-frame/create
 *   daily-frame/WorkDetail           /daily-frame/works/:id
 *   chapter/ChapterEditor            /chapters/new, /chapters/:id/edit
 *   chapter/ChapterDetail            /chapters/:id
 *   memory/MemoryCreate              /memories/new
 *   memory/MemoryDetail              /memories/:id
 *   album/location/FootprintPage     /footprint
 *   album/location/LocationTimeCompare  /time-compare/:sceneId
 *
 * Every case here asserts that the routed view actually mounts and renders its
 * own primary heading -- a page that silently renders nothing is exactly the
 * regression this file exists to catch.
 */

const ok = (data: unknown) => ({ code: 0, message: 'success', data })

const chapter = {
  id: 'ch-nightly-1',
  status: 'confirmed',
  origin: 'manual',
  is_hidden: false,
  title: '夜影随笔',
  summary: '夜影随笔的摘要',
  start_date: '2024-01-01',
  end_date: '2024-12-31',
  cover_photo_id: null,
  evidence: [],
  photo_count: 0,
  event_count: 0,
  version: 1,
  source_ids: [],
  years: [2024],
  people: [],
  places: [],
  events: [],
  diary_entries: {},
}

const memory = {
  id: 'mem-nightly-1',
  status: 'confirmed',
  origin: 'manual',
  title: '秋日杭州三日行',
  title_source: 'user',
  story: null,
  story_source: 'system',
  story_generation_status: 'idle',
  story_generation_started_at: null,
  story_generation_error: null,
  cover_photo_id: null,
  start_time: '2024-10-01T09:00:00',
  end_time: '2024-10-03T18:00:00',
  time_source: 'confirmed',
  confidence_level: 'strong',
  photo_count: 0,
  places: [],
  people: [],
  evidence: [],
  photos: [],
  tickets: [],
  created_at: '2024-10-03T18:00:00',
  updated_at: '2024-10-03T18:00:00',
  confirmed_at: '2024-10-03T18:00:00',
}

const dailyWork = {
  id: 'df-work-nightly-1',
  status: 'ready',
  is_preview: false,
  settings: {
    start_date: '2024-10-01',
    end_date: '2024-10-03',
    title: '十月三日',
    orientation: 'portrait',
    fit: 'contain',
    show_date: true,
    show_caption: true,
    background: '#111827',
    skip_invalid: false,
  },
  duration: 3,
  days: ['2024-10-01', '2024-10-02', '2024-10-03'],
  processed_items: 3,
  error: null,
  file_available: false,
  calendar_changed: false,
  created_at: '2024-10-03T18:00:00',
}

async function mockChapter(page: Page) {
  await page.route('**/api/chapters/ch-nightly-1**', async (route: Route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ok(chapter)) })
  })
}

async function mockMemory(page: Page) {
  await page.route('**/api/memories/mem-nightly-1**', async (route: Route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ok(memory)) })
  })
}

async function mockDailyWork(page: Page) {
  await page.route('**/api/daily-frame/works/df-work-nightly-1**', async (route: Route) => {
    const url = route.request().url()
    if (url.includes('/poster') || url.includes('/file')) {
      await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ code: 404, msg: 'not found' }) })
      return
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ok(dailyWork)) })
  })
}

test.describe('Nightly view coverage — memories / frame / chapter @views-coverage', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo))) return
  })

  test('RelationsPage 渲染关联探索首页', async ({ page }) => {
    await page.route('**/api/relations/**', async (route: Route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ok({ nodes: [], edges: [] })) })
    })

    await page.goto('/explore/relations')

    await expect(page.locator('h1.cover-title')).toBeVisible({ timeout: 15_000 })
    await expect(page.locator('h1.cover-title')).toHaveText(/沿着记忆|遇见更多故事/)
    expect(new URL(page.url()).pathname).toBe('/explore/relations')
  })

  test('DailyFramePage 渲染一日一帧日历', async ({ page }) => {
    await page.goto('/daily-frame')

    await expect(page.getByRole('heading', { name: '一日一帧', level: 1 })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('link', { name: '制作影片' })).toBeVisible()
  })

  test('FilmCreatePage 渲染影片制作页', async ({ page }) => {
    await page.goto('/daily-frame/create')

    await expect(page.getByRole('heading', { name: '制作一日一帧影片', level: 1 })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('link', { name: '返回日历' })).toBeVisible()
  })

  test('WorkDetail 渲染影片详情标题', async ({ page }) => {
    await mockDailyWork(page)

    await page.goto('/daily-frame/works/df-work-nightly-1')

    await expect(page.getByRole('heading', { name: '十月三日', level: 1 })).toBeVisible({ timeout: 15_000 })
  })

  test('ChapterEditor 新建页渲染装订表单', async ({ page }) => {
    await page.goto('/chapters/new')

    await expect(page.getByRole('heading', { name: '把这些年的照片，装订成日记', level: 1 })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('button', { name: '创建并翻开日记' })).toBeVisible()
  })

  test('ChapterEditor 编辑页载入已有章节', async ({ page }) => {
    await mockChapter(page)

    await page.goto('/chapters/ch-nightly-1/edit')

    await expect(page.getByRole('heading', { name: '整理这本影像日记', level: 1 })).toBeVisible({ timeout: 15_000 })
  })

  test('ChapterDetail 渲染章节阅读视图', async ({ page }) => {
    await mockChapter(page)

    await page.goto('/chapters/ch-nightly-1')

    await expect(page.getByRole('link', { name: '编辑' })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('button', { name: '每日日记' })).toBeVisible()
  })

  test('MemoryCreate 渲染新建记忆页', async ({ page }) => {
    await page.goto('/memories/new')

    await expect(page.getByRole('heading', { name: '新建记忆', level: 1 })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText('已选择 0 张').first()).toBeVisible()
  })

  test('MemoryDetail 渲染记忆标题与时间线', async ({ page }) => {
    await mockMemory(page)

    await page.goto('/memories/mem-nightly-1')

    await expect(page.getByRole('heading', { name: '秋日杭州三日行', level: 1 })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('heading', { name: '照片时间线' })).toBeVisible()
  })

  test('FootprintPage 渲染足迹地图入口', async ({ page }) => {
    await page.goto('/footprint')

    await expect(page.getByRole('heading', { name: '去过的地方' })).toBeVisible({ timeout: 15_000 })
  })

  test('LocationTimeCompare 渲染时光对照页头', async ({ page }) => {
    await page.route('**/api/locations/time-compare**', async (route: Route) => {
      const url = route.request().url()
      if (url.includes('/photos')) {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ok([])) })
        return
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(ok({ eligible: false, location_name: '杭州', match_type: 'same_place', radius_m: 100 })),
      })
    })

    await page.goto('/time-compare/scene-nightly-1')

    await expect(page.getByText('杭州').first()).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText('时光对照').first()).toBeVisible()
  })
})
