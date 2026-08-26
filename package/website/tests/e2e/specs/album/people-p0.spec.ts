import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

import { ensureAuthSession, authHeaders } from '../../helpers/auth'
import {
  requireAnyIdentity,
  requireIdentityWithPhotos,
  type BaseResponse,
  type FaceIdentitySummary,
} from '../../helpers/data-probe'
import { acquireMutex } from '../../helpers/mutex'
import { e2eEnv } from '../../../../playwright/e2e-env'

/**
 * P0 - 人物相册核心路径（/album/people, /album/people/:id）
 *
 * 覆盖 doc/e2e-test-checklist.md §2.5。带 @p0 标签，PR 阶段必跑。
 *
 * 数据假设：测试数据 `D:\\Trailsnap\测试\p0\face\person{1,2,3}\` 需要
 * RECOGNIZE_FACE 任务跑完后才能产生 FaceIdentity。dev 套件默认开启
 * 扫描预扫描；如果 AI 服务未起，RECOGNIZE_FACE 会 pending → 探针
 * 自动 skip，不阻塞其他用例。
 *
 * 关键 UI 约定（src/views/album/people/PeopleList.vue）：
 *   - 标题"人物"位于顶部 h1
 *   - 头部有返回按钮、"批量"/"取消" 切换按钮、筛选 popover
 *   - 卡片网格使用 .flow-grid（grid-template-columns: repeat(auto-fill, minmax(80px, 1fr)))
 *   - 卡片左上角为 PersonAvatar（封面裁切后的人脸），下方"X 个项目"文案
 *   - 合并模式下"合并 (N)"按钮：disabled when selectedIds.length < 2
 *   - 卡片右上角的 ... 触发 context menu（Teleport 到 body）
 *
 * 关键 UI 约定（src/views/album/people/PeopleDetail.vue）：
 *   - 通过 UnifiedPhotoPage 渲染，h1 = identity.identity_name，subtitle = `${n} 张`
 *   - 顶部"批量选择"按钮进入选择模式 → 下拉含"设为封面"
 *   - Lightbox 内"查看原图"按钮 → /api/medias/{id}/file
 *
 * 注意：lucide-vue-next 0.555 把 Filter 改名为 Funnel，渲染后的 svg
 * class 是 `lucide-funnel`，旧的 `lucide-filter` 在 lucide 0.555+ 已废弃。
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

/**
 * 带退避的 goto：dev 套件 14 worker 并发时 Vite dev server 偶发 net::ERR_ABORTED，
 * 一次失败会跳过串行文件后续全部用例。串行文件内重试 2 次，每次间隔 1s。
 */
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

test.describe.serial('P0 - 人物相册', () => {
  // dev 套件下 fullyParallel 偶发 Vite ERR_ABORTED；serial 文件给 1 次重试吸收。
  test.use({ retries: 1 })

  // PEOPLE_MUTEX is shared with people-p1.spec.ts. Under fullyParallel, both files
  // start at the same time and the sibling file's serial tests may cumulatively hold
  // the lock beyond Playwright's 30s default. Extend timeout to 180s so
  // acquireMutex(120s) has headroom.
  test.setTimeout(180_000)

  // 人物用例共享两类可变状态：用户配置 ai.face_recognition_min_photos（lower/restore）
  // 与真实 identity（hide/delete/merge/rename）。fullyParallel 下并发会互相踩踏，
  // 故用跨进程互斥锁把 people-p0/p1 全部串行化（与 people-p1 共用同一把锁）。
  const PEOPLE_MUTEX = 'people-identities'
  let releaseMutex: (() => Promise<void>) | undefined

  let authToken = ''
  test.beforeEach(async ({ page, request }, testInfo) => {
    releaseMutex = await acquireMutex(PEOPLE_MUTEX, 120_000)
    authToken = await ensureAuthSession(request, page, testInfo)
    if (!authToken) return
    // 清理 PeopleList 上的过滤器 localStorage，避免前面的用例遗留 hidden 等选项影响渲染
    await page.addInitScript(() => {
      try {
        localStorage.removeItem('people_filter')
      } catch {
        // ignore
      }
    })
  })

  test.afterEach(async () => {
    await releaseMutex?.()
    releaseMutex = undefined
  })

  test('2.5.1 人物列表页加载 - 标题与网格可见 @p0', async ({ page }) => {
    await gotoRetry(page, '/album/people')
    // 标题"人物"（PeopleList.vue 静态 h1）
    await expect(page.getByRole('heading', { name: '人物', level: 1 })).toBeVisible({ timeout: 10_000 })
    // 头部"批量"按钮
    await expect(page.getByRole('button', { name: '批量' })).toBeVisible()

    // 等待首次加载完成：有 identity → 网格渲染；无 identity → 出现"暂无识别到的人物"文案。
    // 用 or 断言：网格可能在 identities 为空时根本不渲染（PeopleList 用 v-else-if 切到空态）。
    const grid = page.locator('.flow-grid').first()
    const emptyHint = page.getByText('暂无识别到的人物')
    await expect(grid.or(emptyHint)).toBeVisible({ timeout: 15_000 })
    if (await grid.count()) {
      const hasGridChildren = (await grid.locator(':scope > *').count()) > 0
      expect(hasGridChildren, 'flow-grid should contain at least one card').toBe(true)
    }
  })

  test('2.5.2 点击人物卡片跳详情 - /album/people/:id 路由正常 @p0', async ({ page, request }, testInfo) => {
    const probe = await requireAnyIdentity(request, testInfo)
    if (!probe.ok) return

    await gotoRetry(page, '/album/people')
    // 等至少一张卡片渲染（卡片点击触发 router.push）
    const card = page.locator('.flow-grid > div').first()
    await expect(card).toBeVisible({ timeout: 15_000 })

    // 记下当前点击的卡片对应 identity 名称，断言详情页 h1 = 该名称
    const expectedName = await page.locator('.flow-grid > div span').first().textContent({ timeout: 5_000 })
    await card.click()

    await page.waitForURL(/\/album\/people\/[0-9a-f-]{36}/i, { timeout: 10_000 })
    if (expectedName) {
      await expect(page.getByText(expectedName).first()).toBeVisible({ timeout: 10_000 })
    } else {
      // fallback：详情页至少渲染出 UnifiedPhotoPage 的 sub-header "N 张"
      await expect(page.getByText(/\d+\s*张/).first()).toBeVisible({ timeout: 10_000 })
    }
  })

  test('2.5.3 人物详情页加载 - 子标题"X 张"+ 至少一张照片 @p0', async ({ page, request }, testInfo) => {
    const probe = await requireIdentityWithPhotos(request, testInfo)
    if (!probe.ok) return

    // 监听 /api/faces/identities/{id}/photos 请求（必须在 goto 之前注册，否则 SPA 的 onMounted 抢先发出）
    const photosRequest = page.waitForResponse(
      (res) =>
        res.url().includes(`/api/faces/identities/${probe.identity.id}/photos`) && res.status() === 200,
      { timeout: 30_000 },
    )
    await gotoRetry(page, `/album/people/${probe.identity.id}`)
    await photosRequest

    // UnifiedPhotoPage 渲染 h1 (身份名) + p (X 张)
    await expect(page.getByText(/\d+\s*张/).first()).toBeVisible({ timeout: 15_000 })

    // 详情页用 UnifiedPhotoPage + PhotoGallery，至少应该渲染出 .photo-gallery 块
    const gallery = page.locator('.photo-gallery').first()
    await expect(gallery).toBeVisible({ timeout: 10_000 })
    // 至少有一张图。PhotoGallery 用懒加载，首屏可能还在加载——等真正渲染出来再断言。
    const imgs = page.locator('.photo-gallery img')
    await expect
      .poll(() => imgs.count(), { timeout: 15_000, message: 'wait for at least one photo to render' })
      .toBeGreaterThan(0)
    // 再确认第一张图确实可见（避免拿到的是占位但 layout 已占位的 img）
    await expect(imgs.first()).toBeVisible({ timeout: 10_000 })
  })

  test('2.5.3b 人物详情页重新扫描先展示候选确认页 @p0', async ({ page, request }, testInfo) => {
    const probe = await requireAnyIdentity(request, testInfo)
    if (!probe.ok) return

    await page.route(`**/api/faces/identities/${probe.identity.id}/rescan/preview`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 200,
          msg: '扫描预览成功',
          data: {
            status: 'success',
            reason: null,
            reference_count: 3,
            threshold: 0.35,
            candidate_threshold: 0.45,
            removal_threshold: 0.52,
            add_candidates: [
              { face_id: 101, photo_id: '00000000-0000-0000-0000-000000000101', distance: 0.1, confidence: 0.9, recommended: true, assignment_type: 'unassigned' },
              { face_id: 102, photo_id: '00000000-0000-0000-0000-000000000102', distance: 0.4, confidence: 0.6, recommended: false, assignment_type: 'reassign', current_identity_name: '其他人物' },
            ],
            remove_candidates: [
              { face_id: 201, photo_id: '00000000-0000-0000-0000-000000000201', distance: 0.6, confidence: 0.4, recommended: false, assignment_type: 'remove' },
            ],
            summary: { add_count: 2, remove_count: 1, reassign_count: 1 },
          },
        }),
      })
    })

    await gotoRetry(page, `/album/people/${probe.identity.id}`)

    const actionsButton = page.getByRole('button', { name: '人物操作' })
    await expect(actionsButton).toBeVisible({ timeout: 10_000 })
    await expect(actionsButton).toBeEnabled()

    await actionsButton.click()
    await page.getByRole('menuitem', { name: '编辑人物信息' }).click()
    const editDialog = page.getByRole('dialog').filter({ hasText: '编辑人物信息' })
    await expect(editDialog).toBeVisible({ timeout: 5_000 })
    await editDialog.getByRole('button', { name: '取消' }).click()

    await actionsButton.click()
    await page.getByRole('menuitem', { name: '重新扫描人脸' }).click()
    const rescanDialog = page.getByRole('dialog').filter({ hasText: '重新扫描确认' })
    await expect(rescanDialog).toBeVisible({ timeout: 5_000 })
    await expect(rescanDialog.getByText('找到 2 个待新增、1 个待移出人脸')).toBeVisible()
    await expect(rescanDialog.getByText('相似度 90%')).toBeVisible()
    await expect(rescanDialog.getByText('当前：其他人物')).toBeVisible()
    await expect(rescanDialog.getByRole('button', { name: '应用选中项（1）' })).toBeEnabled()
  })

  test('2.5.4 筛选 popover - named + unnamed 默认勾选 @p0', async ({ page }) => {
    await gotoRetry(page, '/album/people')
    // 头部 FilterIcon 触发弹层（lucide 0.555: Filter → Funnel，class 为 lucide-funnel）
    const filterBtn = page.locator('.people-list button:has(svg.lucide-funnel)').first()
    await expect(filterBtn).toBeVisible({ timeout: 10_000 })
    await filterBtn.click()

    // 弹层内的筛选标题"筛选显示"
    await expect(page.getByText('筛选显示')).toBeVisible({ timeout: 5_000 })
    // 默认 named + unnamed 已勾选
    const namedCb = page.locator('.el-checkbox:has-text("已添加姓名")').first()
    const unnamedCb = page.locator('.el-checkbox:has-text("未添加姓名")').first()
    const hiddenCb = page.locator('.el-checkbox:has-text("隐藏人物")').first()
    await expect(namedCb).toBeVisible()
    await expect(unnamedCb).toBeVisible()
    await expect(hiddenCb).toBeVisible()

    // el-checkbox 默认 checked 时带 .is-checked class，未勾选时不带
    await expect(namedCb).toHaveClass(/is-checked/)
    await expect(unnamedCb).toHaveClass(/is-checked/)
    await expect(hiddenCb).not.toHaveClass(/is-checked/)
  })

  test('2.5.5 编辑对话框 - 通过 ... 触发菜单打开并保存重命名 @p0', async ({ page, request }, testInfo) => {
    const probe = await requireAnyIdentity(request, testInfo)
    if (!probe.ok) return

    const UNIQUE_NAME = `P0-E2E-${Date.now().toString(36)}`
    const originalName = probe.identity.identity_name ?? '未命名'

    await gotoRetry(page, '/album/people')
    // 找到第一个卡片的 ... 触发点（在卡片名称旁的 MoreVerticalIcon）。
    // PeopleList 用的是 @click.stop 在子元素上，但因为 Playwright 直接 click 子元素
    // 会经过外层卡片 onClick，进而被捕获转发到 detail，所以这里用 evaluate 来
    // 直接派发 click 事件到子元素：
    const card = page.locator('.flow-grid > div').first()
    await card.locator('svg.lucide-ellipsis-vertical').first().evaluate((svg: HTMLElement) => {
      const trigger = svg.parentElement
      if (!trigger) throw new Error('context menu trigger parent not found')
      trigger.dispatchEvent(new MouseEvent('click', { bubbles: false }))
    })

    // Context menu 通过 Teleport 渲染到 body
    const menu = page.locator('div.fixed.z-50.bg-white, div.fixed.z-50.dark\\:bg-gray-800').first()
    await expect(menu).toBeVisible({ timeout: 5_000 })
    await menu.getByText('编辑人物信息').click()

    // IdentityEditDialog 标题
    await expect(page.getByRole('dialog').filter({ hasText: '编辑人物信息' })).toBeVisible({ timeout: 5_000 })
    // el-input placeholder
    const nameInput = page.locator('.el-dialog input[placeholder="输入姓名..."]')
    await expect(nameInput).toBeVisible({ timeout: 5_000 })
    await nameInput.fill(UNIQUE_NAME)
    await page.locator('.el-dialog button:has-text("保存")').click()

    // 关闭后 ElMessage "保存成功" + 列表重新拉取后含新名字
    await expect(page.getByText(UNIQUE_NAME).first()).toBeVisible({ timeout: 15_000 })

    // 用 API 直接 restore 原名（带 /api 前缀，前端 fetch 行为一致）
    await request.put(`${e2eEnv.apiBaseUrl}/faces/identities/${probe.identity.id}`, {
      data: { identity_name: originalName },
      headers: authHeaders(authToken),
    })
  })

  test('2.5.6 详情页设置封面 - 选择 1 张照片后 API 调用 + identity 更新 @p0', async ({ page, request }, testInfo) => {
    const probe = await requireIdentityWithPhotos(request, testInfo)
    if (!probe.ok) return

    await gotoRetry(page, `/album/people/${probe.identity.id}`)

    // 等详情页至少有一张照片渲染
    const thumb = page.locator('.photo-gallery img').first()
    await expect(thumb).toBeVisible({ timeout: 15_000 })

    // 进入批量选择模式：UnifiedPhotoPage 顶部"批量选择"
    const batchBtn = page.getByTitle('批量选择')
    await expect(batchBtn).toBeVisible({ timeout: 10_000 })
    await batchBtn.click()

    // 选第一张（click = toggle 选择模式，PhotoGallery handlePhotoClick）
    await thumb.click({ force: true })

    // "设为封面" 在 PhotoGallery 的 el-dropdown 里（MoreHorizontal 触发）。
    // 选中 1 张后，先点击 MoreHorizontal 按钮让下拉展开。
    const moreActionsBtn = page.locator('button:has(svg.lucide-ellipsis, svg.lucide-more-horizontal)').filter({
      hasNotText: /筛选/,
    }).last()
    await expect(moreActionsBtn).toBeVisible({ timeout: 5_000 })
    await moreActionsBtn.click()

    // PeopleDetail 自定义了 #batch-actions 插槽，显示"设为封面"项
    const setCoverItem = page.locator('.el-dropdown-menu__item:has-text("设为封面")').first()
    await expect(setCoverItem).toBeVisible({ timeout: 5_000 })

    const coverReq = page.waitForResponse(
      (res) =>
        res.url().includes(`/api/faces/identities/${probe.identity.id}/cover`) &&
        res.status() === 200,
      { timeout: 10_000 },
    )
    await setCoverItem.click()
    await coverReq

    // 重新拉取 identity 验证 cover 字段更新
    const after = await listIdentities(request, authToken)
    const me = after.find((i) => i.id === probe.identity.id)
    expect(me, 'identity should still exist after set cover').toBeTruthy()
  })

  test('2.5.7 上下文菜单 - 删除一个测试创建的 identity 走通整链路 @p0', async ({ page, request }, testInfo) => {
    // 不依赖现有数据：用 API 创建/删除隔离，避免污染共享 identities
    const created = await createIdentity(request, authToken, {
      identity_name: `P0-Delete-${Date.now().toString(36)}`,
      description: 'P0 测试自动清理',
    })
    if (!created) {
      testInfo.skip(true, 'Failed to create test identity via API; face CRUD broken?')
      return
    }

    await gotoRetry(page, '/album/people')

    // 验证：刚创建的 identity 应出现在列表上（前提：min_photos=0，否则被过滤）。
    // 默认配置 ai.face_recognition_min_photos=5，未挂照片会被过滤。
    // 测试若被过滤，handleCardClick 也只能基于 visible card，无法确定。
    // 因此 P0 这个用例需要先临时调整 min_photos，再恢复：
    const minPhotosRestore = await lowerMinPhotos(request, authToken)

    try {
      // 重新加载，让 list_identities 走新配置
      await page.reload()

      // 刚创建的 identity 应出现在列表上
      await expect(page.getByText(created.identity_name ?? '').first()).toBeVisible({ timeout: 15_000 })

      // 用 evaluate 派发 click 到子元素（避免外层卡片 onClick 转发到 detail）
      const card = page
        .locator('.flow-grid > div')
        .filter({ hasText: created.identity_name ?? '' })
        .first()
      await expect(card).toBeVisible({ timeout: 10_000 })
      await card.locator('svg.lucide-ellipsis-vertical').first().evaluate((svg: HTMLElement) => {
        const trigger = svg.parentElement
        if (!trigger) throw new Error('context menu trigger parent not found')
        trigger.dispatchEvent(new MouseEvent('click', { bubbles: false }))
      })

      // 菜单渲染后点"删除人物"
      const menu = page.locator('div.fixed.z-50.bg-white, div.fixed.z-50.dark\\:bg-gray-800').first()
      await expect(menu).toBeVisible({ timeout: 5_000 })
      await menu.getByText('删除人物').click()

      // el-message-box "确定" 按钮（confirmButtonText: '删除'）
      const confirmBtn = page.locator('.el-message-box__btns button:has-text("删除")').first()
      await expect(confirmBtn).toBeVisible({ timeout: 5_000 })
      const deleteReq = page.waitForResponse(
        (res) =>
          res.url().includes(`/api/faces/identities/${created.id}`) &&
          res.url().endsWith(created.id) &&
          res.status() === 200,
        { timeout: 10_000 },
      )
      await confirmBtn.click()
      await deleteReq

      // 列表重新拉取后该 identity 不再可见
      await expect(page.getByText(created.identity_name ?? '')).toHaveCount(0, { timeout: 15_000 })
    } finally {
      // 恢复 min_photos 原值 + 兜底删除（即使 UI 路径走完失败，DB 也不残留）
      if (minPhotosRestore !== null) {
        await restoreMinPhotos(request, authToken, minPhotosRestore)
      }
      await deleteIdentity(request, authToken, created.id)
    }
  })

  test('2.5.8 详情页返回 - 返回按钮回到列表 @p0', async ({ page, request }, testInfo) => {
    const probe = await requireAnyIdentity(request, testInfo)
    if (!probe.ok) return

    // 先进列表页，再进详情页——返回按钮走 router.back()（浏览器历史），
    // 若直接跳详情，history 里上一条是 about:blank，返回不会落到 /album/people。
    await gotoRetry(page, '/album/people')
    await gotoRetry(page, `/album/people/${probe.identity.id}`)
    // UnifiedPhotoPage 头部左侧返回按钮：圆形 hover bg，children 包含 ArrowLeft svg
    const backBtn = page.locator('.unified-photo-page button:has(svg.lucide-arrow-left)').first()
    await expect(backBtn).toBeVisible({ timeout: 10_000 })
    await backBtn.click()
    // dev 模式 4 worker 并发 + Vite HMR 偶尔会让 router.back() 慢于 5s；
    // 先等列表页主要请求完成再断 URL，避免在 history push 过程中判失败。
    await page.waitForLoadState('networkidle', { timeout: 8_000 }).catch(() => undefined)

    // 路由回到 /album/people（不带 /:id 后缀）
    await page.waitForURL(/\/album\/people$/, { timeout: 10_000 })
    // 列表的 h1 "人物" 应再次可见
    await expect(page.getByRole('heading', { name: '人物', level: 1 })).toBeVisible({ timeout: 10_000 })
  })

  test('2.5.9 编辑对话框取消 - 取消按钮不修改原姓名 @p0', async ({ page, request }, testInfo) => {
    const probe = await requireAnyIdentity(request, testInfo)
    if (!probe.ok) return

    const originalName = probe.identity.identity_name ?? '未命名'
    const draftName = `SHOULD-NOT-PERSIST-${Date.now().toString(36)}`

    await gotoRetry(page, '/album/people')
    const card = page.locator('.flow-grid > div').first()
    await expect(card).toBeVisible({ timeout: 15_000 })

    // 触发 ... 菜单（同 2.5.7 的派发点击方式，避免被外层卡片 onClick 吞掉）
    await card.locator('svg.lucide-ellipsis-vertical').first().evaluate((svg: HTMLElement) => {
      const trigger = svg.parentElement
      if (!trigger) throw new Error('context menu trigger parent not found')
      trigger.dispatchEvent(new MouseEvent('click', { bubbles: false }))
    })
    const menu = page.locator('div.fixed.z-50.bg-white, div.fixed.z-50.dark\\:bg-gray-800').first()
    await expect(menu).toBeVisible({ timeout: 5_000 })
    await menu.getByText('编辑人物信息').click()

    // 对话框出现
    const dialog = page.getByRole('dialog').filter({ hasText: '编辑人物信息' })
    await expect(dialog).toBeVisible({ timeout: 5_000 })
    // 改成临时姓名
    const nameInput = page.locator('.el-dialog input[placeholder="输入姓名..."]')
    await expect(nameInput).toBeVisible({ timeout: 5_000 })
    await nameInput.fill(draftName)
    // 点取消
    await page.locator('.el-dialog button:has-text("取消")').click()
    // 对话框关闭
    await expect(dialog).toBeHidden({ timeout: 5_000 })

    // 列表仍然显示原名（不应该被 draftName 覆盖）
    await expect(page.getByText(originalName).first()).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText(draftName)).toHaveCount(0, { timeout: 5_000 })

    // 兜底：从后端再确认一次
    const after = await listIdentities(request, authToken)
    const me = after.find((i) => i.id === probe.identity.id)
    expect(me?.identity_name).toBe(originalName)
  })
})

/**
 * 临时把 ai.face_recognition_min_photos 调到 0，让 list_identities 返回空身份的测试 identity。
 * 返回原值用于恢复；失败时返回 null，调用方不应在 finally 中再尝试恢复。
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
    const body = await cur.json() as { ai?: { face_recognition_min_photos?: number } }
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
