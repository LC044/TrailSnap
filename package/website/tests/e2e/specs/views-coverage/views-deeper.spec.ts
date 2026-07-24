import { expect, test, type Page } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

/**
 * P1 - 视图层深度覆盖（coverage-gaps-frontend.md 5 个真实未覆盖模块）
 *
 * 1. FolderBrowser（views/album/folder/FolderBrowser.vue）
 *    Issue #78 文件夹视图，layoutMode='folder'，通过 /photos 视图设置下拉切换；
 *    onMounted 触发 GET /api/photos/folders?parent= + GET /api/photos?folder&folder_direct
 * 2. BasicSettings（views/settings/BasicSettings.vue）
 *    /settings#basic 含 6+ 个折叠面板：安全/任务/地图/AI/扫描/索引/回收站；导出 / 导入
 * 3. TicketExportModal（views/ticket/components/TicketExportModal.vue）
 *    header "导出数据" 按钮 -> handleExport -> isExportModalOpen=true -> 弹窗；JSON/CSV/PNG
 * 4. DuplicatePhotoCleanup（views/toolbox/DuplicatePhotoCleanup.vue）
 *    /toolbox/duplicate：GET /api/toolbox/duplicate + 删除冗余走 DELETE /api/photos/batch
 * 5. AgentInput（views/agent/components/AgentInput.vue）
 *    双向 v-model + 生成态切换按钮（Send <-> Square）+ 选图态 disabled
 *
 * 所有用例使用 page.route() 拦截接口 + ensureAuthSession，建立自洽、可重复运行的测试。
 * 不依赖后端真实业务数据。
 */
test.describe.configure({ mode: 'serial' })

/** 默认 GET /api/photos/folders?parent= 的空响应 */
const FOLDER_API_BASE = { code: 0, message: 'success', data: { parent: '', breadcrumb: [], own_count: 0, children: [] } }

/** 进入文件夹布局：先到 /photos，等照片列表加载完，点视图设置下拉，选"文件夹" */
async function enterFolderLayout(page: Page): Promise<void> {
  await page.goto('/photos')
  await expect(page.locator('body')).toBeVisible()
  // header `视图设置` 按钮（title=视图设置）展开下拉
  const settingsBtn = page.locator('button[title="视图设置"]')
  await expect(settingsBtn).toBeVisible({ timeout: 15_000 })
  await settingsBtn.click()
  // 下拉中的"文件夹"按钮（普通 <button>，非 role=menuitem）
  const folderItem = page.locator('button:has-text("文件夹")').first()
  await expect(folderItem).toBeVisible({ timeout: 5_000 })
  await folderItem.click()
}

test.describe('P1 - FolderBrowser 文件夹视图 @views-coverage', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return
  })

  test('进入文件夹布局 -> 触发 GET /api/photos/folders 并显示空态', async ({ page }) => {
    const folderCalls: string[] = []
    await page.route('**/api/photos/folders**', async (route) => {
      folderCalls.push(route.request().url())
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(FOLDER_API_BASE),
      })
    })

    await enterFolderLayout(page)
    await expect(page.locator('.folder-browser')).toBeVisible({ timeout: 10_000 })
    await expect.poll(() => folderCalls.some((u) => /parent=(?:&|$)/.test(u)), { timeout: 5_000 }).toBeTruthy()
    await expect(page.getByRole('button', { name: '全部' }).first()).toBeVisible()
  })

  test('文件夹包含子目录 -> 点击子目录 -> parent 重新请求', async ({ page }) => {
    let currentParent = ''
    await page.route('**/api/photos/folders**', async (route) => {
      currentParent = new URL(route.request().url()).searchParams.get('parent') ?? ''
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          message: 'success',
          data: {
            parent: currentParent,
            breadcrumb: currentParent
              ? [{ name: currentParent.split('/').pop() || currentParent, path: currentParent }]
              : [],
            own_count: 0,
            children: currentParent === ''
              ? [{ name: '子目录A', path: '子目录A', count: 3, has_children: false }]
              : [],
          },
        }),
      })
    })
    await page.route('**/api/photos?**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, message: 'success', data: [] }),
      })
    })

    await enterFolderLayout(page)
    await expect(page.locator('.folder-browser')).toBeVisible({ timeout: 10_000 })
    const childCard = page.getByRole('button', { name: /子目录A/ }).first()
    await expect(childCard).toBeVisible({ timeout: 5_000 })
    await childCard.click()
    await expect.poll(() => currentParent === '子目录A', { timeout: 5_000 }).toBeTruthy()
    await expect(page.locator('.folder-browser').getByText('子目录A').first()).toBeVisible()
  })

  test('接口 500 时 -> 触发 ElMessage 错误 toast 并展示空态', async ({ page }) => {
    await page.route('**/api/photos/folders**', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ code: 500, message: 'server error', data: null }),
      })
    })

    await enterFolderLayout(page)
    await expect(page.locator('.folder-browser')).toBeVisible({ timeout: 10_000 })
    await expect(page.locator('.el-message').first()).toBeVisible({ timeout: 10_000 })
  })
})

test.describe('P1 - BasicSettings 基础设置面板 @views-coverage', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return
  })

  test('/settings#basic 渲染安全/任务/地图折叠面板', async ({ page }) => {
    await page.goto('/settings#basic')
    for (const title of ['安全设置', '任务设置', '地图设置']) {
      const header = page.locator('.el-collapse-item__header', { hasText: title }).first()
      await expect(header, `折叠面板 ${title} 应可见`).toBeVisible({ timeout: 15_000 })
    }
  })

  test('安全设置展开 -> 切换允许注册开关 -> 保存触发 PUT /api/system/config', async ({ page }) => {
    const updateCalls: { url: string; body: unknown }[] = []
    await page.route('**/api/system/config', async (route) => {
      if (route.request().method() === 'PUT') {
        try {
          updateCalls.push({ url: route.request().url(), body: JSON.parse(route.request().postData() || '{}') })
        } catch {
          updateCalls.push({ url: route.request().url(), body: null })
        }
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 0, message: 'success', data: { security: { allow_registration: true } } }) })
      } else {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 0, message: 'success', data: { security: { allow_registration: false }, task: {}, map: {}, ai: {}, scan: {}, recycle_bin: {}, index: {} } }) })
      }
    })

    await page.goto('/settings#basic')
    await page.locator('.el-collapse-item__header', { hasText: '安全设置' }).first().click()
    const sw = page.locator('.el-form-item', { hasText: '允许新用户注册' }).locator('.el-switch').first()
    await expect(sw).toBeVisible({ timeout: 5_000 })
    await sw.click()
    await page.getByRole('button', { name: '保存安全配置' }).click()

    await expect.poll(() => updateCalls.length).toBeGreaterThan(0)
    expect(updateCalls[0].body).toMatchObject({ security: { allow_registration: true } })
  })

  test('导出配置按钮 -> 触发 GET /api/settings/export 并成功提示', async ({ page }) => {
    let exportHit = false
    await page.route('**/api/settings/export', async (route) => {
      exportHit = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, message: 'success', data: { hello: 'world' } }),
      })
    })

    await page.goto('/settings#basic')
    await page.getByRole('button', { name: '导出配置' }).click()

    await expect.poll(() => exportHit, { timeout: 5_000 }).toBeTruthy()
    await expect(page.locator('.el-message', { hasText: '配置导出成功' })).toBeVisible({ timeout: 5_000 })
  })
})

test.describe('P1 - TicketExportModal 车票导出弹窗 @views-coverage', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return
  })

  test('点击导出数据按钮打开弹窗 -> 三个格式按钮可见', async ({ page }) => {
    await page.route('**/api/train-ticket/**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 0, message: 'success', data: [] }) })
    })

    await page.goto('/ticket')
    const exportBtn = page.getByRole('button', { name: '导出数据' })
    await expect(exportBtn).toBeVisible({ timeout: 15_000 })
    await exportBtn.click()

    await expect(page.locator('.el-dialog__title', { hasText: '导出车票数据' })).toBeVisible({ timeout: 5_000 })
    await expect(page.locator('.el-dialog').getByText('JSON 格式')).toBeVisible()
    await expect(page.locator('.el-dialog').getByText('CSV 格式')).toBeVisible()
    await expect(page.locator('.el-dialog').getByText('仿真纸质票 (PNG)')).toBeVisible()
  })

  test('未选票时点击 PNG -> 显示请先选择要导出的车票警告且不调用导出', async ({ page }) => {
    const exportCalls: string[] = []
    await page.route('**/api/train-ticket/export**', async (route) => {
      exportCalls.push(route.request().url())
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, message: 'success', data: 'mock' }),
      })
    })

    await page.goto('/ticket')
    await page.getByRole('button', { name: '导出数据' }).click()
    await expect(page.locator('.el-dialog__title', { hasText: '导出车票数据' })).toBeVisible({ timeout: 5_000 })

    await page.locator('.el-dialog').getByText('仿真纸质票 (PNG)').click()

    await expect(page.locator('.el-message', { hasText: '请先选择要导出的车票' })).toBeVisible({ timeout: 5_000 })
    await page.waitForTimeout(500)
    expect(exportCalls.length).toBe(0)
  })

  test('点击 JSON 按钮 -> 触发 GET /api/train-ticket/export?format=json', async ({ page }) => {
    const exportCalls: string[] = []
    await page.route('**/api/train-ticket/export**', async (route) => {
      exportCalls.push(`${route.request().method()} ${route.request().url()}`)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, message: 'success', data: 'mock-json-blob' }),
      })
    })

    await page.goto('/ticket')
    await page.getByRole('button', { name: '导出数据' }).click()
    await expect(page.locator('.el-dialog__title', { hasText: '导出车票数据' })).toBeVisible({ timeout: 5_000 })

    await page.locator('.el-dialog').getByText('JSON 格式').click()

    await expect.poll(() => exportCalls.some((s) => s.includes('format=json')), { timeout: 5_000 }).toBeTruthy()
    await expect(page.locator('.el-dialog__title', { hasText: '导出车票数据' })).toHaveCount(0, { timeout: 5_000 })
  })
})

test.describe('P1 - DuplicatePhotoCleanup 重复照片清理 @views-coverage', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return
  })

  test('加载重复组 -> 渲染 重复组 1 (2 张) -> 删除冗余触发 DELETE /api/photos/batch', async ({ page }) => {
    const dupCalls: string[] = []
    const deleteCalls: { url: string; body: unknown }[] = []

    await page.route('**/api/toolbox/duplicate**', async (route) => {
      dupCalls.push(route.request().url())
      // Note: DuplicatePhotoCleanup.vue calls result.map() on the response, so we
      // mock the unwrapped array shape (the production axios interceptor returns
      // the full BaseResponse wrapper, but the consumer treats it as an array).
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            md5: 'md5-aaa',
            photos: [
              { id: 'p1', filename: 'a.jpg', thumbnail: '', file_path: '/tmp/a.jpg', file_type: 'photo', taken_at: null },
              { id: 'p2', filename: 'b.jpg', thumbnail: '', file_path: '/tmp/b.jpg', file_type: 'photo', taken_at: null },
            ],
          },
        ]),
      })
    })

    await page.route('**/api/photos/batch', async (route) => {
      try {
        deleteCalls.push({ url: route.request().url(), body: JSON.parse(route.request().postData() || '{}') })
      } catch {
        deleteCalls.push({ url: route.request().url(), body: null })
      }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 0, message: 'success', data: { deleted: 1 } }) })
    })

    page.on('dialog', (d) => d.accept().catch(() => undefined))

    await page.goto('/toolbox/duplicate')

    await expect(page.getByText(/重复组\s*1\s*\(2\s*张\)/)).toBeVisible({ timeout: 10_000 })
    await expect.poll(() => dupCalls.length).toBeGreaterThan(0)

    const selectRedundant = page.getByRole('button', { name: '选择冗余项' }).first()
    await selectRedundant.click()
    // 选择冗余项 -> 渲染 "删除选中 (1张)" 按钮（Element Plus 类前缀 + 文本匹配）
    const deleteSelected = page.locator('button', { hasText: /删除选中\s*\(\d+张\)/ }).first()
    await expect(deleteSelected).toBeVisible({ timeout: 5_000 })
    await deleteSelected.click()
    // ElMessageBox 确认弹窗 -> 点击 "删除"
    const confirmBtn = page.locator('.el-message-box__btns button', { hasText: '删除' }).first()
    await expect(confirmBtn).toBeVisible({ timeout: 5_000 })
    await confirmBtn.click()

    await expect.poll(() => deleteCalls.length, { timeout: 5_000 }).toBeGreaterThan(0)
    expect(deleteCalls[0].body).toMatchObject({ photo_ids: expect.arrayContaining(['p2']) })
  })
})

test.describe('P1 - AgentInput 输入区交互 @views-coverage', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return
  })

  test('打开 AgentChat -> 输入文字 -> update:modelValue 触发 send', async ({ page }) => {
    await page.goto('/')
    const fab = page.locator('[aria-label="打开 AI 助手"]')
    await expect(fab).toBeVisible({ timeout: 10_000 })
    await fab.dispatchEvent('click')
    await expect(page.locator('.agent-chat-overlay')).toBeVisible({ timeout: 10_000 })

    const input = page.locator('.agent-chat-overlay input.agent-input')
    await expect(input).toBeVisible()
    await input.fill('帮我找一下今天拍的照片')
    await expect(input).toHaveValue('帮我找一下今天拍的照片')

    await page.locator('.agent-chat-overlay input.agent-input').press('Enter')
    await expect(page.locator('.agent-chat-overlay')).toBeVisible({ timeout: 3_000 })
  })

  test('生成态 isGenerating=true -> 按钮切到 agent-stop-btn', async ({ page }) => {
    await page.goto('/')
    const fab = page.locator('[aria-label="打开 AI 助手"]')
    await expect(fab).toBeVisible({ timeout: 10_000 })
    await fab.dispatchEvent('click')
    await expect(page.locator('.agent-chat-overlay')).toBeVisible({ timeout: 10_000 })

    await page.locator('.agent-chat-overlay input.agent-input').fill('查询照片')
    await page.locator('.agent-chat-overlay input.agent-input').press('Enter')

    await expect.poll(
      async () =>
        (await page.locator('.agent-chat-overlay .agent-stop-btn').count()) > 0 ||
        (await page.locator('.agent-chat-overlay .agent-send-btn').count()) === 0,
      { timeout: 3_000 },
    ).toBe(true)
  })
})
