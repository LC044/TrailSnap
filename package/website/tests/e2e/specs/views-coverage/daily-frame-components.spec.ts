import { expect, test, type Page, type Route } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

/**
 * Nightly view coverage —— 一日一帧（daily-frame）子组件。
 *
 * 2026-10-24 的前端盲区扫描按「view 文件名是否被任何 spec 引用」判定，
 * `src/views/daily-frame/` 下只有 DailyFramePage / FilmCreatePage / WorkDetail
 * 被既有 spec 触达，而 WorkList.vue / FillDialog.vue / FrameEditor.vue 三个组件
 * 从未被任何 spec 直接引用过 —— 它们虽然挂在 DailyFramePage 里，但没有任何断言
 * 锁住它们的渲染与交互，属于典型盲区。
 *
 * 本文件把这三个组件各锁一条主链路：
 *   - WorkList     ：切到「我的作品」页签 -> 影片卡片 / 空态
 *   - FillDialog   ：点「填充本月」-> 勾选候选 -> 保存 -> POST /api/daily-frame/fill
 *   - FrameEditor  ：点日历某天 -> 选素材 -> 保存 -> PUT /api/daily-frame/days/{day}
 *
 * 所有接口都用 route stub 成确定形状，断言不依赖容器里的真实相册数据。
 */

const MONTH = '2026-10'
const TODAY = '2026-10-20'
const PENDING_DAY = '2026-10-05'
const EMPTY_DAY = '2026-10-08'

const SETTINGS = {
  initialized: true,
  timezone: 'Asia/Shanghai',
  locked: true,
  revision: 1,
  today: TODAY,
  export: { available: true, reason: null },
}

/** PENDING_DAY 有素材待选（驱动「填充本月」按钮可用），EMPTY_DAY 无素材，另有 today。 */
const CALENDAR = {
  timezone: 'Asia/Shanghai',
  today: TODAY,
  revision: 1,
  days: [
    { day: PENDING_DAY, candidate_count: 2, future: false, frame: null },
    { day: EMPTY_DAY, candidate_count: 0, future: false, frame: null },
    { day: TODAY, candidate_count: 1, future: false, frame: null },
  ],
}

const ASSET = {
  id: 'asset-nightly-1',
  photo_time: '2026-10-05T10:12:00',
  file_type: 'image',
  duration: 0,
  available: true,
  reason: null,
  has_motion: false,
}

const WORK = {
  id: 'df-work-nightly-1',
  status: 'ready',
  is_preview: false,
  settings: {
    start_date: '2026-10-01',
    end_date: '2026-10-05',
    title: '十月旅行',
    orientation: 'landscape',
    fit: 'contain',
    show_date: true,
    show_caption: true,
    background: '#000000',
    skip_invalid: true,
  },
  duration: 5,
  days: [PENDING_DAY],
  processed_items: 5,
  error: null,
  file_available: false,
  calendar_changed: false,
  created_at: '2026-10-06T09:30:00',
}

/**
 * 1x1 透明 PNG。
 *
 * FrameEditor 用 <img :src="source" @error="mediaFailed"> 预览素材，一旦图片无法解码
 * 就会置位 mediaError 并把「保存这一帧」按钮永久禁用 —— 所以必须返回真正可解码的图片。
 */
const PNG_1PX = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64',
)

/** 标准 BaseResponse 包装，request 拦截器会把 data 字段解包给调用方。 */
function ok(data: unknown) {
  return {
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ code: 0, msg: 'success', data }),
  }
}

/**
 * 一日一帧接口总路由。
 *
 * `works` 的返回值由调用方传入，便于同一套 stub 覆盖「有影片」与「空态」两种场景。
 */
async function stubDailyFrame(page: Page, options: { works?: unknown[] } = {}) {
  const works = options.works ?? [WORK]
  await page.route('**/api/daily-frame/**', async (route: Route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    const method = route.request().method()

    if (path.endsWith('/settings')) return route.fulfill(ok(SETTINGS))
    if (path.endsWith('/calendar')) return route.fulfill(ok(CALENDAR))
    if (path.endsWith('/works') && method === 'GET') {
      return route.fulfill(ok({ items: works, total: works.length }))
    }
    if (path.endsWith('/fill') && method === 'GET') {
      return route.fulfill(ok({
        preserved: 1,
        items: [
          {
            day: PENDING_DAY,
            photo_id: ASSET.id,
            mode: 'still',
            start_seconds: 0,
            caption: '晚风刚刚好',
            version: 2,
            photo: ASSET,
          },
        ],
      }))
    }
    if (path.endsWith('/fill') && method === 'POST') {
      const body = JSON.parse(route.request().postData() || '{}')
      const items = (body.items ?? []).map((row: { day: string }) => ({ day: row.day, status: 'saved' }))
      return route.fulfill(ok({ items }))
    }
    if (/\/days\/[^/]+\/candidates$/.test(path)) {
      return route.fulfill(ok({ items: [ASSET], total: 1 }))
    }
    if (/\/days\/[^/]+$/.test(path) && method === 'GET') {
      // removed=true 表示这天尚未选帧（曾被移除），保存按钮文案才是「保存这一帧」。
      return route.fulfill(ok({
        day: PENDING_DAY,
        photo_id: null,
        mode: 'still',
        start_seconds: 0,
        caption: '',
        version: 3,
        removed: true,
        available: false,
        reason: null,
        date_changed: false,
        photo: null,
      }))
    }
    if (/\/days\/[^/]+$/.test(path) && method === 'PUT') {
      return route.fulfill(ok({
        day: PENDING_DAY,
        photo_id: ASSET.id,
        mode: 'still',
        start_seconds: 0,
        caption: '',
        version: 4,
        removed: false,
        available: true,
        reason: null,
        date_changed: false,
        photo: ASSET,
      }))
    }
    if (/\/assets\/[^/]+\/file$/.test(path)) {
      return route.fulfill({ status: 200, contentType: 'image/png', body: PNG_1PX })
    }
    if (/\/assets\/[^/]+$/.test(path)) {
      return route.fulfill(ok(ASSET))
    }
    return route.fulfill(ok(null))
  })
}

test.describe('Nightly view coverage —— 一日一帧子组件 @views-coverage', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo))) return
  })

  test('WorkList 在「我的作品」页签渲染影片卡片并可跳转到详情', async ({ page }) => {
    await stubDailyFrame(page)
    await page.goto('/daily-frame')

    await page.getByRole('button', { name: '我的作品' }).click()

    await expect(page.getByRole('heading', { name: '我的影片' })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('heading', { name: '十月旅行' })).toBeVisible()
    await expect(page.getByText('2026-10-01 — 2026-10-05')).toBeVisible()
    // workStatus() 把 ready 映射成「已完成」
    await expect(page.getByText('已完成')).toBeVisible()
    await expect(page.locator('a[href="/daily-frame/works/df-work-nightly-1"]')).toHaveCount(1)
  })

  test('WorkList 没有影片时展示空态提示', async ({ page }) => {
    await stubDailyFrame(page, { works: [] })
    await page.goto('/daily-frame')

    await page.getByRole('button', { name: '我的作品' }).click()

    await expect(page.getByRole('heading', { name: '我的影片' })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText('还没有影片，先为几天选帧，再制作一部回忆影片。')).toBeVisible()
  })

  test('FillDialog 打开后勾选候选并保存，提交填充请求', async ({ page }) => {
    const savedBodies: unknown[] = []
    await stubDailyFrame(page)
    page.on('request', request => {
      if (request.method() === 'POST' && request.url().endsWith('/api/daily-frame/fill')) {
        savedBodies.push(JSON.parse(request.postData() || '{}'))
      }
    })
    await page.goto('/daily-frame')

    const fillButton = page.getByRole('button', { name: '填充本月' })
    await expect(fillButton).toBeEnabled({ timeout: 15_000 })
    await fillButton.click()

    const dialog = page.locator('section[role="dialog"]')
    await expect(dialog.getByRole('heading', { name: '填充本月' })).toBeVisible()
    await expect(dialog.getByText('将填充 1 天，保留已有 1 天')).toBeVisible()

    const checkbox = dialog.getByRole('checkbox', { name: `填充 ${PENDING_DAY}` })
    await expect(checkbox).toBeChecked()
    await expect(dialog.getByRole('button', { name: '保存所选 1 天' })).toBeEnabled()

    await dialog.getByRole('button', { name: '保存所选 1 天' }).click()

    await expect.poll(() => savedBodies.length).toBeGreaterThan(0)
    expect(savedBodies[0]).toMatchObject({
      items: [{ day: PENDING_DAY, photo_id: ASSET.id, mode: 'still' }],
    })
    await expect(page.getByText('已保存 1 天，跳过 0 天，失败 0 天')).toBeVisible()
  })

  test('FrameEditor 打开某天后可选素材并保存该日选帧', async ({ page }) => {
    const savedBodies: unknown[] = []
    await stubDailyFrame(page)
    page.on('request', request => {
      if (request.method() === 'PUT' && request.url().includes(`/api/daily-frame/days/${PENDING_DAY}`)) {
        savedBodies.push(JSON.parse(request.postData() || '{}'))
      }
    })
    await page.goto('/daily-frame')

    await page.locator(`button.df-cell[aria-label^="${PENDING_DAY}"]`).click()

    const dialog = page.locator('section[role="dialog"]')
    await expect(dialog.getByRole('heading', { name: `${PENDING_DAY} · 选择这一帧` })).toBeVisible({ timeout: 15_000 })
    await expect(dialog.getByText('当天素材 · 1 个')).toBeVisible()

    // 素材按钮的 aria-label 是 `${photo_time}，${file_type}`
    await dialog.getByRole('button', { name: /2026-10-05T10:12:00/ }).click()
    await dialog.getByLabel('一句话（可选）').fill('晚风刚刚好')

    const saveButton = dialog.getByRole('button', { name: '保存这一帧' })
    await expect(saveButton).toBeEnabled()
    await saveButton.click()

    await expect.poll(() => savedBodies.length).toBeGreaterThan(0)
    expect(savedBodies[0]).toMatchObject({
      photo_id: ASSET.id,
      mode: 'still',
      caption: '晚风刚刚好',
    })
    await expect(page.getByText('已保存这一天的瞬间')).toBeVisible()
  })
})
