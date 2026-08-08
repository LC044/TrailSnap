import { test, expect, type APIRequestContext, type Page, type Locator } from '@playwright/test'

import { ensureAuthSession, authHeaders } from '../../helpers/auth'
import {
  requireAnyIdentity,
  requireNamedIdentity,
  requireIdentityWithPhotos,
  type BaseResponse,
  type FaceIdentitySummary,
} from '../../helpers/data-probe'
import { acquireMutex } from '../../helpers/mutex'
import { e2eEnv } from '../../../../playwright/e2e-env'

/**
 * P1 - 人物相册业务深度（/album/people, /album/people/:id）
 *
 * 覆盖 doc/e2e-test-checklist.md §2.5 业务深测。Nightly 用例，
 * describe 以 "P1 - " 开头，被 run-e2e.mjs 的 --grep "P1 - " 命中。
 * 也可直接 `-Cover full`（本任务指定）跑全套。
 *
 * 测试域：
 *   - 筛选行为（每个 types 选项都应改变 API 请求）
 *   - 上下文菜单动作（hide / show / rescan / delete）真实落库
 *   - 批量操作（选择 / 批量隐藏 / 批量删除 / 合并）
 *   - 详情页移除照片（从人物中移除 → 关联解除）
 *
 * 数据副作用：
 *   - 隐藏/显示：直接改 DB 不删数据，安全
 *   - 合并/删除：会改动 FaceIdentity，使用 createIdentity + 清理保证隔离
 *   - 移除照片：解除 photo<->face_identity 关联，但 Photo 不删
 */

async function listIdentities(
  request: APIRequestContext,
  token: string,
  types: string[] = ['named', 'unnamed'],
): Promise<FaceIdentitySummary[]> {
  const search = types.map((t) => `types=${encodeURIComponent(t)}`).join('&')
  const res = await request.get(`${e2eEnv.apiBaseUrl}/faces/identities?skip=0&limit=100&${search}`, {
    headers: authHeaders(token),
  })
  if (!res.ok()) return []
  const body = (await res.json()) as FaceIdentitySummary[] | BaseResponse<FaceIdentitySummary[]>
  return Array.isArray(body) ? body : body.data ?? []
}

async function listAllIdentities(
  request: APIRequestContext,
  token: string,
): Promise<FaceIdentitySummary[]> {
  const res = await request.get(`${e2eEnv.apiBaseUrl}/faces/identities?skip=0&limit=100`, {
    headers: authHeaders(token),
  })
  if (!res.ok()) return []
  const body = (await res.json()) as FaceIdentitySummary[] | BaseResponse<FaceIdentitySummary[]>
  return Array.isArray(body) ? body : body.data ?? []
}

async function listIdentityPhotos(
  request: APIRequestContext,
  token: string,
  id: string,
  limit = 100,
): Promise<Array<{ id: string }>> {
  const res = await request.get(
    `${e2eEnv.apiBaseUrl}/faces/identities/${id}/photos?skip=0&limit=${limit}`,
    { headers: authHeaders(token) },
  )
  if (!res.ok()) return []
  const body = (await res.json()) as Array<{ id: string }> | BaseResponse<Array<{ id: string }>>
  return Array.isArray(body) ? body : body.data ?? []
}

async function createIdentity(
  request: APIRequestContext,
  token: string,
  payload: { identity_name: string; description?: string },
): Promise<FaceIdentitySummary | null> {
  const res = await request.post(`${e2eEnv.apiBaseUrl}/faces/identities`, {
    data: payload,
    headers: authHeaders(token),
  })
  if (!res.ok()) return null
  const body = (await res.json()) as BaseResponse<FaceIdentitySummary>
  return body.data ?? null
}

async function deleteIdentity(
  request: APIRequestContext,
  token: string,
  id: string,
): Promise<void> {
  await request
    .delete(`${e2eEnv.apiBaseUrl}/faces/identities/${id}`, { headers: authHeaders(token) })
    .catch(() => undefined)
}

async function gotoRetry(page: Page, url: string, retries = 2): Promise<void> {
  for (let i = 0; ; i++) {
    try {
      await page.goto(url, { waitUntil: 'domcontentloaded' })
      return
    } catch (e) {
      if (i >= retries) throw e
      await page.waitForTimeout(1_000)
    }
  }
}

/** 清掉 PeopleList 的筛选 localStorage，保证每次进页面是默认 (named + unnamed) 状态。 */
async function clearPeopleFilter(page: Page): Promise<void> {
  await page.addInitScript(() => {
    try {
      localStorage.removeItem('people_filter')
    } catch {
      // ignore
    }
  })
}

/**
 * 打开 PeopleList 卡片右上角的 "..." 上下文菜单。
 *
 * 替代直接 .click() 外层卡片（会被 @click 转发到详情页）。触发器是包含
 * MoreVerticalIcon (svg.lucide-ellipsis-vertical) 的 div，类标识：
 *   p-1 rounded-full hover:bg-gray-200 dark:hover:bg-gray-800 transition-colors cursor-pointer
 *
 * 这里直接定位到这个 div，比 svg.parentElement 更稳——避免了 lucide-vue-next
 * 未来版本调整包装层级、或在不同浏览器里 SVG 没有 parentElement 等边界情况。
 */
async function dispatchContextMenuOnFirstMatch(card: ReturnType<Page['locator']>): Promise<void> {
  const trigger = card
    .locator('div.cursor-pointer:has(svg.lucide-ellipsis-vertical)')
    .first()
  // force: true 跳过 actionability 检查（hover 后立即点击，避免 hover 状态消失）
  await trigger.click({ force: true })
}

/**
 * 临时降低 ai.face_recognition_min_photos 到 0，让 list_identities 返回空身份的测试 identity。
 * 返回原值用于恢复。失败返回 null。
 */
async function lowerMinPhotos(
  request: APIRequestContext,
  token: string,
): Promise<number | null> {
  try {
    const cur = await request.get(`${e2eEnv.apiBaseUrl}/settings/`, {
      headers: authHeaders(token),
    })
    if (!cur.ok()) return null
    const body = (await cur.json() as { ai?: { face_recognition_min_photos?: number } })
    const original = body.ai?.face_recognition_min_photos ?? 5
    if (original === 0) return original
    const merged = {
      ...body,
      ai: { ...(body.ai ?? {}), face_recognition_min_photos: 0 },
    }
    const put = await request.put(`${e2eEnv.apiBaseUrl}/settings/`, {
      data: merged,
      headers: authHeaders(token),
    })
    return put.ok() ? original : null
  } catch {
    return null
  }
}

async function restoreMinPhotos(
  request: APIRequestContext,
  token: string,
  original: number,
): Promise<void> {
  try {
    const cur = await request.get(`${e2eEnv.apiBaseUrl}/settings/`, {
      headers: authHeaders(token),
    })
    if (!cur.ok()) return
    const body = await cur.json() as { ai?: { face_recognition_min_photos?: number } }
    const merged = {
      ...body,
      ai: { ...(body.ai ?? {}), face_recognition_min_photos: original },
    }
    await request.put(`${e2eEnv.apiBaseUrl}/settings/`, {
      data: merged,
      headers: authHeaders(token),
    })
  } catch {
    // ignore
  }
}

test.describe.serial('P1 - 人物相册', () => {

  // PEOPLE_MUTEX is shared with people-p0.spec.ts. Under fullyParallel, both files
  // start at the same time and the sibling file's serial tests may cumulatively hold
  // the lock beyond Playwright's 30s default. Extend timeout to 180s so
  // acquireMutex(120s) has headroom.
  test.setTimeout(180_000)
  // 人物用例共享两类可变状态：用户配置 ai.face_recognition_min_photos（lower/restore）
  // 与真实 identity（hide/delete/merge/rename）。fullyParallel 下并发会互相踩踏，
  // 故用跨进程互斥锁把 people-p0/p1 全部串行化（与 people-p0 共用同一把锁）。
  const PEOPLE_MUTEX = 'people-identities'
  let releaseMutex: (() => Promise<void>) | undefined

  let authToken = ''
  test.beforeEach(async ({ page, request }, testInfo) => {
    releaseMutex = await acquireMutex(PEOPLE_MUTEX, 120_000)
    authToken = await ensureAuthSession(request, page, testInfo)
    if (!authToken) return
    await clearPeopleFilter(page)
  })

  test.afterEach(async () => {
    await releaseMutex?.()
    releaseMutex = undefined
  })

  test('2.5.10 筛选 named - 关闭 unnamed 后 API 调用只带 types=named', async ({ page, request }, testInfo) => {
    // 本用例会把筛选切到 types=named 并断言列表渲染，必须有「已命名」身份；
    // requireAnyIdentity 接受 unnamed，named 列表为空时 .flow-grid 不渲染会误报。
    const probe = await requireNamedIdentity(request, testInfo)
    if (!probe.ok) return

    await gotoRetry(page, '/album/people')

    // 监听下一次 /api/faces/identities 请求，必须包含 types=named
    const identitiesReq = page.waitForResponse(
      (res) =>
        /\/api\/faces\/identities/.test(res.url()) &&
        /types=named/.test(res.url()) &&
        res.status() === 200,
      { timeout: 10_000 },
    )
    // lucide 0.555: Filter → Funnel. PeopleList root container has .people-list class,
    // which scopes the button away from the global NavBar filter (also lucide-funnel).
    await page.locator('.people-list button:has(svg.lucide-funnel)').first().click()
    // 取消 unnamed，保留 named → API 应只发 types=named
    const unnamedCb = page.locator('.el-checkbox:has-text("未添加姓名")').first()
    await unnamedCb.click()
    await identitiesReq

    // 列表依然能渲染
    await expect(page.locator('.flow-grid').first()).toBeVisible({ timeout: 10_000 })
  })

  test('2.5.11 隐藏/显示 - 上下文菜单触发后 is_hidden 切换落库', async ({ page, request }, testInfo) => {
    const probe = await requireAnyIdentity(request, testInfo)
    if (!probe.ok) return

    await gotoRetry(page, '/album/people')
    const card = page.locator('.flow-grid > div').first()
    await expect(card).toBeVisible({ timeout: 15_000 })

    await dispatchContextMenuOnFirstMatch(card)

    const menu = page.locator('div.fixed.z-50.bg-white, div.fixed.z-50.dark\\:bg-gray-800').first()
    await expect(menu).toBeVisible({ timeout: 5_000 })
    await menu.getByText('隐藏人物').click()

    // el-message-box 确认按钮（type=warning）→ "确定"
    const confirmBtn = page.locator('.el-message-box__btns button:has-text("确定")').first()
    await expect(confirmBtn).toBeVisible({ timeout: 5_000 })
    // 监听 PUT /faces/identities/{id}（用 URL 唯一过滤，因 method() 在某些 Playwright 版本上是字符串属性）
    const hideReq = page.waitForResponse(
      (res) =>
        res.url().includes(`/api/faces/identities/${probe.identity.id}`) &&
        !res.url().includes('/cover') &&
        !res.url().includes('/rescan') &&
        !res.url().includes('/remove-photos') &&
        !res.url().includes('/photos') &&
        !res.url().includes('/merge') &&
        !res.url().includes('/add-photos') &&
        res.status() === 200,
      { timeout: 10_000 },
    )
    await confirmBtn.click()
    await hideReq

    // 重新拉取（不带 hidden filter，但默认 named+unnamed）→ 该 identity 应 is_hidden=true
    // → 重新拉"含 hidden"才能看到
    const listWithHidden = await request.get(
      `${e2eEnv.apiBaseUrl}/faces/identities?skip=0&limit=100&types=named&types=unnamed&types=hidden`,
      { headers: authHeaders(authToken) },
    )
    const allBody = (await listWithHidden.json()) as FaceIdentitySummary[] | BaseResponse<FaceIdentitySummary[]>
    const allAfter = Array.isArray(allBody) ? allBody : allBody.data ?? []
    const me = allAfter.find((i) => i.id === probe.identity.id)
    expect(me, 'identity should still exist after hide').toBeTruthy()
    expect(me!.is_hidden).toBeTruthy()

    // 还原
    await request.put(`${e2eEnv.apiBaseUrl}/faces/identities/${probe.identity.id}`, {
      data: { is_hidden: false },
      headers: authHeaders(authToken),
    })
  })

  test('2.5.12 批量模式 - 选中 2 个后"合并"按钮启用 + 成功合并', async ({ page, request }, testInfo) => {
    // 创建 2 个临时 identity 做合并：min_photos 默认 5，未挂照片会被过滤，
    // 因此先临时把 min_photos 调到 0 再创建、合并、还原。
    const restoreMin = await lowerMinPhotos(request, authToken)
    if (restoreMin === null) {
      testInfo.skip(true, 'Failed to lower min_photos for merge test; settings API not available?')
      return
    }
    const t1 = await createIdentity(request, authToken, {
      identity_name: `P1-MergeT-${Date.now().toString(36)}`,
    })
    const t2 = await createIdentity(request, authToken, {
      identity_name: `P1-MergeS-${Date.now().toString(36)}`,
    })
    if (!t1 || !t2) {
      await restoreMinPhotos(request, authToken, restoreMin)
      if (t1) await deleteIdentity(request, authToken, t1.id)
      if (t2) await deleteIdentity(request, authToken, t2.id)
      testInfo.skip(true, 'Failed to create temp identities for merge test.')
      return
    }

    try {
      await gotoRetry(page, '/album/people')
      // 重新加载让 list_identities 走新配置（与 2.5.7 同款：min_photos 调整后需要重发请求）
      await page.reload()
      // 等待列表把刚创建的两个加载出来（默认 named+unnamed）
      await expect(page.getByText(t1.identity_name ?? '').first()).toBeVisible({ timeout: 15_000 })
      await expect(page.getByText(t2.identity_name ?? '').first()).toBeVisible({ timeout: 15_000 })

      // 进入批量模式（PeopleList toggleMergeMode）
      await page.getByRole('button', { name: '批量' }).click()

      // 找到两张对应卡片并点击（合并模式下 click = toggle 选中）
      const card1 = page.locator('.flow-grid > div').filter({ hasText: t1.identity_name ?? '' }).first()
      const card2 = page.locator('.flow-grid > div').filter({ hasText: t2.identity_name ?? '' }).first()
      await card1.click()
      await card2.click()

      // 顶部按钮显示"合并 (2)"
      const mergeBtn = page.getByRole('button', { name: /合并\s*\(2\)/ })
      await expect(mergeBtn).toBeVisible({ timeout: 5_000 })

      // 触合并
      const mergeReq = page.waitForResponse(
        (res) =>
          res.url().includes('/api/faces/identities/merge') &&
          res.status() === 200,
        { timeout: 15_000 },
      )
      await mergeBtn.click()

      // 二次确认（confirmMerge → ElMessageBox.confirm）
      const confirmBtn = page.locator('.el-message-box__btns button:has-text("确定")').first()
      await expect(confirmBtn).toBeVisible({ timeout: 5_000 })
      await confirmBtn.click()
      await mergeReq

      // 验证合并结果：t2 应不再存在
      await page.waitForTimeout(1_000)
      const after = await listIdentities(request, authToken)
      expect(
        after.find((i) => i.id === t2.id),
        'merged source identity should no longer be in the list',
      ).toBeUndefined()
      expect(after.find((i) => i.id === t1.id), 'merge target identity should remain').toBeTruthy()
    } finally {
      // 兜底：DB 残留下清理
      await deleteIdentity(request, authToken, t1.id)
      await deleteIdentity(request, authToken, t2.id)
      await restoreMinPhotos(request, authToken, restoreMin)
    }
  })
  test('2.5.13 详情页移除照片 - "从人物中移除" 删除 photo<->face 关联', async ({ page, request }, testInfo) => {
    const probe = await requireIdentityWithPhotos(request, testInfo)
    if (!probe.ok) return

    // 必须有 >=2 张照片，否则删除测试无意义（删完空集合）
    const before = await listIdentityPhotos(request, authToken, probe.identity.id)
    if (before.length < 2) {
      testInfo.skip(
        true,
        `Identity "${probe.identity.identity_name}" has only ${before.length} photo(s); need >=2 to safely remove one.`,
      )
      return
    }

    await gotoRetry(page, `/album/people/${probe.identity.id}`)
    const gallery = page.locator('.photo-gallery')
    await expect(gallery).toBeVisible({ timeout: 15_000 })

    // 进入批量 → 选第 0 张图
    const batchBtn = page.getByTitle('批量选择')
    await expect(batchBtn).toBeVisible({ timeout: 10_000 })
    await batchBtn.click()

    const imgs = gallery.locator('img')
    await expect
      .poll(() => imgs.count(), { timeout: 15_000 })
      .toBeGreaterThan(0)
    await imgs.first().click({ force: true })

    // PhotoGallery 的 trash 按钮 title = deleteLabel prop = "从人物中移除"
    const removeBtn = page.locator('button[title="从人物中移除"]').first()
    await expect(removeBtn).toBeVisible({ timeout: 5_000 })

    // 同时监听：waitForRequest 拿 photo_ids，waitForResponse 等请求完成
    const removeUrl = `/api/faces/identities/${probe.identity.id}/remove-photos`
    const removeReq = page.waitForRequest(
      (r) => r.url().includes(removeUrl) && r.method() === 'POST',
      { timeout: 30_000 },
    )
    const removeRes = page.waitForResponse(
      (r) => r.url().includes(removeUrl) && r.status() === 200,
      { timeout: 30_000 },
    )
    await removeBtn.click()

    // PeopleDetail 启用 confirm-remove=true：走两次确认 ——
    // 1) UnifiedPhotoPage.handleBatchRemoveFromAlbum 弹 ElMessageBox.confirm
    // 2) confirmRemove=true 进入 handleBatchDelete → 弹 ConfirmDialog（z-100）
    // ElMessageBox z-index:2000 的 overlay 在淡出中可能仍盖住 ConfirmDialog，
    // 因此先 click ElMessageBox 确定，再 detached 等待。
    const firstConfirm = page.locator('.el-message-box__btns button:has-text("确定")').first()
    await expect(firstConfirm).toBeVisible({ timeout: 5_000 })
    await firstConfirm.click()

    await page.locator('.el-message-box').waitFor({ state: 'detached', timeout: 5_000 }).catch(async () => {
      await expect(firstConfirm).toBeHidden({ timeout: 5_000 })
      await page.waitForTimeout(400)
    })

    const secondConfirm = page.locator('div.fixed.inset-0 button:has-text("确定")').first()
    await expect(secondConfirm).toBeVisible({ timeout: 5_000 })
    await secondConfirm.click()

    // 等请求与响应都完成，并从请求 body 提取真正移除的 photo_ids（DOM 与 API
    // 排序不同，不能依赖 before 列表下标）
    const req = await removeReq
    await removeRes
    let removedIds: string[] = []
    try {
      const body = req.postData() ? JSON.parse(req.postData()!) : {}
      removedIds = Array.isArray(body.photo_ids) ? body.photo_ids : []
    } catch {
      removedIds = []
    }
    expect(removedIds.length, 'remove-photos request should carry at least one photo_id').toBeGreaterThan(0)

    // 验证：被移除的 photo_ids 应不再出现在该 identity 的照片列表里
    await page.waitForTimeout(1_500)
    const after = await listIdentityPhotos(request, authToken, probe.identity.id, 500)
    const afterIds = new Set(after.map((p) => p.id))
    for (const id of removedIds) {
      expect(afterIds.has(id), `photo ${id} should be removed from identity`).toBe(false)
    }
  })

  test('2.5.14 重新扫描人脸 - 上下文菜单先调用预览 API', async ({ page, request }, testInfo) => {
    const probe = await requireAnyIdentity(request, testInfo)
    if (!probe.ok) return

    await gotoRetry(page, '/album/people')
    const card = page.locator('.flow-grid > div').first()
    await expect(card).toBeVisible({ timeout: 15_000 })

    await dispatchContextMenuOnFirstMatch(card)
    const menu = page.locator('div.fixed.z-50.bg-white, div.fixed.z-50.dark\\:bg-gray-800').first()
    await expect(menu).toBeVisible({ timeout: 5_000 })

    // 用 URL 唯一过滤（避免 .method() 在不同 Playwright 版本上有歧义）
    const rescanReq = page.waitForResponse(
      (res) =>
        res.url().includes(`/api/faces/identities/${probe.identity.id}/rescan/preview`) &&
        (res.status() === 200 || res.status() >= 400),
      { timeout: 30_000 },
    )
    await menu.getByText('重新扫描人脸').click()
    const res = await rescanReq
    // 后端可能 200（成功）或 4xx/5xx（AI 服务未起），都视为流程到达端点
    expect([200, 400, 500, 502, 503]).toContain(res.status())
  })

  test('2.5.15 详情页 "从人物中移除" 已移除的照片 - 接口幂等', async ({ request }, testInfo) => {
    const probe = await requireAnyIdentity(request, testInfo)
    if (!probe.ok) return
    const res = await request.post(
      `${e2eEnv.apiBaseUrl}/faces/identities/${probe.identity.id}/remove-photos`,
      {
        data: { photo_ids: ['00000000-0000-0000-0000-000000000000'] },
        headers: authHeaders(authToken),
      },
    )
    // 不强制要求 200（后端实现可能返回 200 + count=0），只要不抛 5xx
    expect([200, 400, 404]).toContain(res.status())
  })

  test('2.5.16 合并按钮 disabled 状态 - 选中 0/1 时合并按钮不可用 @p1', async ({ page, request }, testInfo) => {
    // 准备：临时降低 min_photos 以让空身份也能进列表，再创建 1 个临时 identity
    const restoreMin = await lowerMinPhotos(request, authToken)
    if (restoreMin === null) {
      testInfo.skip(true, 'Failed to lower min_photos; settings API unavailable?')
      return
    }
    const t = await createIdentity(request, authToken, {
      identity_name: `P1-Disabled-${Date.now().toString(36)}`,
    })
    if (!t) {
      await restoreMinPhotos(request, authToken, restoreMin)
      testInfo.skip(true, 'Failed to create temp identity for disabled-button test.')
      return
    }
    try {
      await gotoRetry(page, '/album/people')
      await page.reload() // 重新加载让 list_identities 走新配置

      // 找到刚创建的卡片
      const card = page
        .locator('.flow-grid > div')
        .filter({ hasText: t.identity_name ?? '' })
        .first()
      await expect(card).toBeVisible({ timeout: 15_000 })

      // 进入批量模式
      await page.getByRole('button', { name: '批量' }).click()

      // 此时未选中任何卡片 → "合并" 按钮文本为 "合并 (0)"，应处于 disabled
      const mergeBtn0 = page.getByRole('button', { name: /合并\s*\(0\)/ })
      await expect(mergeBtn0).toBeVisible({ timeout: 5_000 })
      await expect(mergeBtn0).toBeDisabled()

      // 选中 1 张 → 仍 disabled（合并需要 >=2）
      await card.click()
      const mergeBtn1 = page.getByRole('button', { name: /合并\s*\(1\)/ })
      await expect(mergeBtn1).toBeVisible({ timeout: 5_000 })
      await expect(mergeBtn1).toBeDisabled()

      // 取消选中后再选一次（同一卡片再点一次会取消），确保 1 选不触发合并按钮启用
      await card.click()
      await expect(page.getByRole('button', { name: /合并\s*\(0\)/ })).toBeVisible({ timeout: 5_000 })
    } finally {
      await deleteIdentity(request, authToken, t.id)
      await restoreMinPhotos(request, authToken, restoreMin)
    }
  })

  test('2.5.17 批量隐藏 → 批量显示 round-trip @p1', async ({ page, request }, testInfo) => {
    // 用 lowerMinPhotos 创建临时 identities（避开默认 5 张过滤）
    const restoreMin = await lowerMinPhotos(request, authToken)
    if (restoreMin === null) {
      testInfo.skip(true, 'Failed to lower min_photos for batch hide/show test.')
      return
    }
    const ids: string[] = []
    try {
      // 创建 2 个临时 identity
      for (let i = 0; i < 2; i++) {
        const c = await createIdentity(request, authToken, {
          identity_name: `P1-BatchHS-${i}-${Date.now().toString(36)}`,
        })
        if (!c) throw new Error('create identity failed')
        ids.push(c.id)
      }

      // 并行用例（people-p0 也调 lowerMinPhotos/restoreMinPhotos）可能在此时已把
      // 共享的 min_photos 还原成 5；进页面前再压一次，缩小 UI 渲染窗口的竞态。
      await lowerMinPhotos(request, authToken)

      await gotoRetry(page, '/album/people')
      await page.reload() // 让新配置生效

      // 默认 named+unnamed 筛选；临时 identity 应可见。reload 后 API 可能仍在
      // 处理，等待两张卡片都出现再继续。并行用例若再次还原 min_photos，空身份会被
      // 过滤——poll 失败时重新 lower + reload 再试一轮。
      const waitCards = async (): Promise<Locator> => {
        const cards = page.locator('.flow-grid > div').filter({ hasText: /P1-BatchHS-/ })
        await expect
          .poll(() => cards.count(), { timeout: 15_000, message: 'wait for both batch-hs identities to render' })
          .toBeGreaterThanOrEqual(2)
        return cards
      }
      let visibleCards: Locator
      try {
        visibleCards = await waitCards()
      } catch {
        await lowerMinPhotos(request, authToken)
        await page.reload()
        visibleCards = await waitCards()
      }

      // 进入批量模式（在卡片可见后进入，避免按钮被弹层遮挡）
      await page.getByRole('button', { name: '批量' }).click()

      // 选中我们刚创建的两张卡片
      await visibleCards.nth(0).click()
      await visibleCards.nth(1).click()

      // 点 "隐藏" 按钮
      const hideBtn = page.getByRole('button', { name: '隐藏' }).first()
      await expect(hideBtn).toBeEnabled()
      await hideBtn.click()

      // ElMessageBox 确认
      const confirm = page.locator('.el-message-box__btns button:has-text("确定")').first()
      await expect(confirm).toBeVisible({ timeout: 5_000 })
      await confirm.click()

      // 等 ElMessageBox 完全消失（handleBulkHide 内部在 then 里把 isMergeMode 置 false 并刷新，
      // 所以不需要再手动点 "取消"）
      await page.locator('.el-message-box').waitFor({ state: 'detached', timeout: 5_000 }).catch(async () => {
        await page.waitForTimeout(400)
      })

      // 等 PeopleList 重新拉取。handleBulkHide 里的 fetchIdentities() 是
      // fire-and-forget（不 await），固定 waitForTimeout 在负载下来不及等它完成，
      // 会读到残留卡片 → 误报 "should be hidden"。默认筛选（named+unnamed）会排除
      // hidden，故隐藏落库 + 重拉后卡片必然从 DOM 消失；用 expect.poll 等到 0。
      for (const name of ids.map((_, i) => `P1-BatchHS-${i}-`)) {
        // 用 regex 而不是精确字符串（Date.now() 部分动态）
        const hiddenCard = page.locator('.flow-grid > div').filter({ hasText: new RegExp(name) })
        await expect
          .poll(async () => hiddenCard.count(), { timeout: 15_000, message: `identity ${name} should be hidden after batch hide` })
          .toBe(0)
      }

      // 验证后端：拿含 hidden 的列表，应能看到这些 identity 已 is_hidden=true。
      // 显式传 min_photos=0，绕过用户配置——并行用例可能已把共享的
      // face_recognition_min_photos 还原成 5，否则 0 照片的临时身份会被过滤掉。
      const listWithHidden = await request.get(
        `${e2eEnv.apiBaseUrl}/faces/identities?skip=0&limit=100&min_photos=0&types=named&types=unnamed&types=hidden`,
        { headers: authHeaders(authToken) },
      )
      const allBody = await listWithHidden.json() as FaceIdentitySummary[] | BaseResponse<FaceIdentitySummary[]>
      const allAfter = Array.isArray(allBody) ? allBody : allBody.data ?? []
      for (const id of ids) {
        const me = allAfter.find((i) => i.id === id)
        expect(me, `identity ${id} should still exist after hide`).toBeTruthy()
        expect(me!.is_hidden, `identity ${id} should be hidden`).toBeTruthy()
      }

      // 还原：把这两个临时 identity 直接显示回来（避免 UI 路径又触发批量操作）
      for (const id of ids) {
        await request.put(`${e2eEnv.apiBaseUrl}/faces/identities/${id}`, {
          data: { is_hidden: false },
          headers: authHeaders(authToken),
        })
      }
    } finally {
      // 兜底清理
      for (const id of ids) {
        await deleteIdentity(request, authToken, id)
      }
      await restoreMinPhotos(request, authToken, restoreMin)
    }
  })
})
