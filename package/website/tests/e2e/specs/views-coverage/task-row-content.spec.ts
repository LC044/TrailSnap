import { expect, test, type Page, type Route } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

/**
 * Nightly view coverage — TaskRowContent.vue。
 *
 * 2026-11-07 的 §4.3 扫描发现 `settings/components/TaskRowContent.vue`
 * 是唯一未被任意 spec 引用的前端 view 文件。该组件没有独立路由，
 * 由 TaskManagement.vue 在 /settings#tasks 中按类目行挂载。
 *
 * 本文件用 /settings#tasks + route mock 驱动三种行状态：
 * 等待条件（attention）、空闲（idle）、接口错误（load failed）。
 */
const response = <T,>(data: T) => ({ code: 0, message: 'success', data })

const waitingTask = {
  task_name: '照片识别',
  category: 'RECOGNIZE_FACE',
  pending: 3,
  completed: 120,
  failed: 0,
  status: 'running',
  priority: 4,
  description: '为照片生成识别结果并归档到人物相册。',
  waiting_reason: '等待 AI 服务恢复',
}

const idleTask = {
  task_name: '车票识别',
  category: 'RECOGNIZE_TICKET',
  pending: 0,
  completed: 45,
  failed: 0,
  status: 'idle',
  priority: 7,
  description: '从火车票与机票照片中提取行程信息。',
}

function fulfillJson(route: Route, status: number, payload: unknown) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(payload),
  })
}

async function mockTaskApis(page: Page, groups: unknown[], fail = false) {
  await page.route('**/api/tasks/grouped-status', route => {
    if (fail) return fulfillJson(route, 500, { code: 500, message: 'forced failure', data: null })
    return fulfillJson(route, 200, response(groups))
  })
  await page.route('**/api/tasks/status', route => fulfillJson(route, 200, response({ fast_mode: false })))
  await page.route('**/api/system/config', route => fulfillJson(route, 200, response({
    security: { allow_registration: true },
    task: { concurrency_level: 'balanced' },
    map: {},
    ai: {},
    scan: {},
    recycle_bin: {},
    index: {},
  })))
}

async function openTaskManagement(page: Page) {
  await page.goto('/settings#tasks')
  await expect(page.getByRole('heading', { name: '后台任务' })).toBeVisible({ timeout: 15_000 })
}

test.describe('P1 - TaskRowContent 后台任务行 @views-coverage', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo))) return
    await page.addInitScript(() => {
      const raw = localStorage.getItem('user_info')
      if (!raw) {
        localStorage.setItem('user_info', JSON.stringify({ id: 'u-e2e', username: 'e2e-admin', is_active: true, is_superuser: true }))
      }
    })
  })

  test('等待条件行渲染状态与可展开详情', async ({ page }) => {
    await mockTaskApis(page, [waitingTask])
    await openTaskManagement(page)

    const row = page.locator('.task-row', { hasText: '照片识别' }).first()
    await expect(row).toBeVisible()
    await expect(row).toContainText('等待条件')
    await expect(row).toContainText('等待 AI 服务恢复')
    await expect(row).toContainText('剩余 3 项')

    await row.getByRole('button', { name: '照片识别详情' }).click()
    await expect(page.locator('#task-details-RECOGNIZE_FACE')).toContainText('调度优先级 4 · 待处理 3 项 · 失败 0 项')
    await expect(page.locator('#task-details-RECOGNIZE_FACE')).toContainText('为照片生成识别结果并归档到人物相册。')
  })

  test('空闲行收纳在暂无任务分组且展开不显示积压', async ({ page }) => {
    await mockTaskApis(page, [idleTask])
    await openTaskManagement(page)

    await page.getByRole('button', { name: /暂无任务（1 类）/ }).click()
    const row = page.locator('.task-row', { hasText: '车票识别' }).first()
    await expect(row).toBeVisible()
    await expect(row).toContainText('无待处理')
    await expect(row).not.toContainText('剩余')
    await expect(row).not.toContainText('失败')

    await row.getByRole('button', { name: '车票识别详情' }).click()
    await expect(page.locator('#task-details-RECOGNIZE_TICKET')).toContainText('调度优先级 7 · 待处理 0 项 · 失败 0 项')
  })

  test('任务接口失败时显示错误态且可重新加载恢复', async ({ page }) => {
    await mockTaskApis(page, [], true)
    await openTaskManagement(page)

    const alert = page.getByRole('alert').filter({ hasText: '暂时无法获取任务状态' })
    await expect(alert).toBeVisible()

    await page.route('**/api/tasks/grouped-status', route => fulfillJson(route, 200, response([waitingTask])))
    await page.getByRole('button', { name: '重新加载' }).click()
    await expect(page.locator('.task-row', { hasText: '照片识别' })).toBeVisible({ timeout: 10_000 })
    await expect(alert).toHaveCount(0)
  })
})
