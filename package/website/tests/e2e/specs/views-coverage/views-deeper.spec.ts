import { expect, test, type Page } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

/**
 * P1 - 视图层深度覆盖（coverage-gaps-frontend.md 5 个真实未覆盖模块）
 *
 * 1. FolderBrowser（views/album/folder/FolderBrowser.vue）
 *    Issue #78 文件夹视图，layoutMode='folder'，通过 /photos 视图设置下拉切换；
 *    onMounted 触发 GET /api/photos/folders?parent= + GET /api/photos?folder&folder_direct
 * 2. BasicSettings（views/settings/BasicSettings.vue）
 *    /settings 各分区页含 6+ 个设置分区（安全/任务/地图/AI/扫描/索引/回收站）；导出 / 导入
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
    // e2e-admin 是首个注册用户（必然 superuser）；#user 是 superuserOnly tab，
    // 且开放注册/后台处理性能等分区按 admin computed 门控（user_info 异步拉取）。
    // 预置 is_superuser，跳过身份回填时序。
    await page.addInitScript(() => {
      const raw = localStorage.getItem('user_info')
      if (!raw) {
        localStorage.setItem('user_info', JSON.stringify({ id: 'u-e2e', username: 'e2e-admin', is_active: true, is_superuser: true }))
      }
    })
  })

  test('设置分区页渲染安全/任务/地图分区', async ({ page }) => {
    // 设置重组后：开放注册 → /settings#user（直渲染 section）；
    // 后台处理性能 → /settings#tasks（TaskManagement 的 <details> 折叠）；
    // 地图设置 → /settings#map（el-collapse 折叠面板）。
    // 后台处理性能收起时内容隐藏，先点开 <details> 的 summary 再断言。
    await page.goto('/settings#user')
    const securityHeader = page.locator('.settings-native-group > header h2').filter({ hasText: '开放注册' }).first()
    await expect(securityHeader, '分区 开放注册 应可见').toBeVisible({ timeout: 15_000 })

    await page.goto('/settings#tasks')
    // 后台处理性能是 <details> 折叠（summary 常显，内容收起）；断言 summary 文本即可。
    await expect(page.locator('.task-performance > summary'), '分区 后台处理性能 应可见').toContainText('后台处理性能')

    await page.goto('/settings#map')
    const mapHeader = page.locator('.el-collapse-item__header, .el-collapse-item .ts-section-title').filter({ hasText: '地图设置' }).first()
    await expect(mapHeader, '分区 地图设置 应可见').toBeVisible({ timeout: 15_000 })
  })

  test('开放注册展开 -> 切换允许注册开关 -> 保存触发 PUT /api/system/config', async ({ page }) => {
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
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 0, message: 'success', data: { security: { allow_registration: true }, task: {}, map: {}, ai: {}, scan: {}, recycle_bin: {}, index: {} } }) })
      }
    })

    await page.goto('/settings#user')
    const sw = page.locator('.settings-native-group', { hasText: '开放注册' }).first().locator('.el-switch').first()
    await expect(sw).toBeVisible({ timeout: 5_000 })
    // 等待服务端配置加载完成：loadData 拿到 getSystemConfig 的结果后会用服务端值覆盖
    // securityForm，若在加载完成前就切换开关，会被异步加载静默重置（见 useBasicSettings.ts 的 loadData）。
    // 开关变为打开状态（表单默认为 false）即代表服务端配置已应用。
    // 注意：Element Plus 的 el-switch 根节点是 div，toBeChecked 只接受
    // checkbox/radio 语义（会报 "Not a checkbox or radio button"），
    // 因此按 Element Plus 自身的契约断言根节点的 is-checked class。
    await expect(sw).toHaveClass(/is-checked/, { timeout: 15_000 })
    await sw.click()
    await page.getByRole('button', { name: '保存注册设置' }).click()

    await expect.poll(() => updateCalls.length).toBeGreaterThan(0)
    expect(updateCalls[0].body).toMatchObject({ security: { allow_registration: false } })
  })

  test('地图设置测试 Key 成功后再保存配置', async ({ page }) => {
    let savedMap: unknown = null

    await page.route('**/api/settings/map/test-key', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ valid: true }),
      })
    })
    await page.route('**/api/settings/', async (route) => {
      if (route.request().method() === 'GET') {
        // GET 返回一个可识别的服务端旧 Key：输入框里出现它就代表 loadData
        // 已用服务端 map 配置覆盖了表单。loadData 拿到服务端 map 配置后会重置 mapForm
        // （api_keys 被覆盖为服务端值），若在加载完成前就填写，刚填好的 Key
        // 会被异步加载静默抹掉，表现为「至少需要填写一个 API Key」、无法保存。
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            code: 0,
            message: 'success',
            data: { map: { provider: 'tianditu', api_keys: ['stale-server-key'] } },
          }),
        })
        return
      }
      savedMap = JSON.parse(route.request().postData() || '{}')
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'success' }),
      })
    })

    // 地图设置分区现位于 /settings#map（el-collapse；BasicSettings 的 activeNames
    // 默认含 'map'，面板初始即展开，无需点击——点击反而会把它收起）。
    await page.goto('/settings#map')
    const keyInput = page.getByLabel('地图 API Key 1')
    await expect(keyInput).toBeVisible({ timeout: 10_000 })
    // 等待服务端 map 配置加载完成后再填写新 Key。
    await expect(keyInput).toHaveValue('stale-server-key', { timeout: 15_000 })
    await keyInput.fill('e2e-valid-map-key')

    await page.getByRole('button', { name: '测试', exact: true }).first().click()
    await expect(page.getByText('连接成功，Key 可用')).toBeVisible()
    await page.getByRole('button', { name: '验证并保存' }).click()

    await expect.poll(() => savedMap).not.toBeNull()
    expect(savedMap).toMatchObject({ map: { provider: 'tianditu', api_keys: ['e2e-valid-map-key'] } })
    await expect(page.locator('.el-message', { hasText: '地图配置已保存' })).toBeVisible()
  })

  test('地图设置拒绝无法完成逆地理编码的 Key', async ({ page }) => {
    await page.route('**/api/settings/map/test-key', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ valid: false, reason: '非法key' }),
      })
    })
    // 同上：等待服务端 map 配置加载完成（输入框出现服务端旧 Key）后再填写，
    // 否则 loadData 会把刚填好的 Key 覆盖掉，预期的「非法key」提示不会出现。
    await page.route('**/api/settings/', async (route) => {
      if (route.request().method() !== 'GET') return route.continue()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          message: 'success',
          data: { map: { provider: 'tianditu', api_keys: ['stale-server-key'] } },
        }),
      })
    })

    // 地图设置分区现位于 /settings#map（el-collapse；BasicSettings 的 activeNames
    // 默认含 'map'，面板初始即展开，无需点击——点击反而会把它收起）。
    await page.goto('/settings#map')
    const invalidKeyInput = page.getByLabel('地图 API Key 1')
    await expect(invalidKeyInput).toHaveValue('stale-server-key', { timeout: 15_000 })
    await invalidKeyInput.fill('invalid-map-key')
    await page.getByRole('button', { name: '测试', exact: true }).first().click()

    await expect(page.getByText('非法key')).toBeVisible()
  })

  test('AI API 地址连通性检查展示服务名和耗时', async ({ page }) => {
    let testedUrl = ''
    let settingsLoaded = false
    await page.route('**/api/settings/', async (route) => {
      if (route.request().method() !== 'GET') return route.continue()
      settingsLoaded = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          message: 'success',
          data: { ai: { ai_api_url: 'http://initial-ai:8001', connections: [] }, runtime: { managedAI: false } },
        }),
      })
    })
    await page.route('**/api/settings/verify-ai-service', async (route) => {
      testedUrl = JSON.parse(route.request().postData() || '{}').api_url
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          msg: 'success',
          data: { success: true, service: 'TrailSnap AI', elapsed_ms: 18 },
        }),
      })
    })

    // AI API 地址输入框现位于 /settings#recognition（本地识别模型页的服务分区）；
    // stub 未带 runtime.managedAI → 默认 true 会隐藏输入框，需显式置 false。
    await page.route('**/api/settings/ai-models', route => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ code: 0, message: 'success', data: { models: [], tasks: {} } }),
    }))
    await page.goto('/settings#recognition')
    const apiInput = page.getByLabel('AI API 地址')
    await expect(apiInput).toBeVisible({ timeout: 10_000 })
    await expect.poll(() => settingsLoaded).toBe(true)
    await expect(apiInput).toHaveValue('http://initial-ai:8001')
    await apiInput.fill('http://ai:8001')
    await page.getByRole('button', { name: '测试连通性' }).click()

    await expect.poll(() => testedUrl).toBe('http://ai:8001')
    await expect(page.getByText('TrailSnap AI 连接正常，耗时 18 ms')).toBeVisible()
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

    // 导出/导入个人配置按钮现位于 /settings#maintenance（高级维护页）。
    await page.goto('/settings#maintenance')
    await page.getByRole('button', { name: '导出个人配置' }).click()

    await expect.poll(() => exportHit, { timeout: 5_000 }).toBeTruthy()
    await expect(page.locator('.el-message', { hasText: '配置导出成功' })).toBeVisible({ timeout: 5_000 })
  })
})

test.describe('P1 - 票夹导出弹窗 @views-coverage', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return
    const items = ['train', 'flight'].map((type, index) => ({
      id: `export-${index}`, type, key: `${type}:export-${index}`, title: '上海 → 成都', code: index ? 'MU1234' : 'G1234',
      from: '上海', to: '成都', date_time: '2026-08-09T10:30:00', price: 680, name: '测试乘客', distance: 1700,
      duration: 180, comments: '', photo_id: null, albums: [], memories: [], candidates: [],
    }))
    await page.route('**/api/ticket-wallet?**', route => route.fulfill({ json: { code: 200, msg: 'success', data: { items, total: items.length } } }))
    await page.route('**/api/railway/stats/batch', route => route.fulfill({ json: { code: 200, msg: 'success', data: [] } }))
  })
  async function openExport(page: Page) {
    await page.goto('/ticket')
    await expect(page.locator('main article')).toHaveCount(2)
    await page.getByRole('button', { name: '更多票夹操作', exact: true }).click()
    await page.getByRole('button', { name: '导出票据', exact: true }).click()
    return page.getByRole('dialog', { name: '导出票据', exact: true })
  }
  test('导出弹窗显示JSON、CSV和火车票纪念PNG', async ({ page }) => {
    const dialog = await openExport(page)
    await expect(dialog.getByRole('button', { name: '票据备份（JSON）', exact: true })).toBeVisible()
    await expect(dialog.getByRole('button', { name: '表格数据（CSV）', exact: true })).toBeVisible()
    await expect(dialog.getByRole('button', { name: '火车票纪念票面（PNG）', exact: true })).toBeEnabled()
    await expect(dialog).toContainText('1 张火车票')
    await expect(dialog).toContainText('1 张将跳过')
  })
  test('空票夹禁用PNG，不创建下载', async ({ page }) => {
    await page.route('**/api/ticket-wallet?**', route => route.fulfill({ json: { code: 200, msg: 'success', data: { items: [], total: 0 } } }))
    await page.goto('/ticket')
    await expect(page.getByRole('heading', { name: '还没有票据', exact: true })).toBeVisible()
    await page.getByRole('button', { name: '更多票夹操作', exact: true }).click()
    await page.getByRole('button', { name: '导出票据', exact: true }).click()
    await expect(page.getByRole('dialog', { name: '导出票据', exact: true }).getByRole('button', { name: '火车票纪念票面（PNG）', exact: true })).toBeDisabled()
  })
  test('JSON下载包含版本和混合票据类型，导出后关闭弹窗', async ({ page }) => {
    const dialog = await openExport(page)
    const pending = page.waitForEvent('download')
    await dialog.getByRole('button', { name: '票据备份（JSON）', exact: true }).click()
    const download = await pending
    const stream = await download.createReadStream()
    if (!stream) throw Error('Missing export stream')
    const chunks: Buffer[] = []
    for await (const chunk of stream) chunks.push(Buffer.from(chunk))
    const backup = JSON.parse(Buffer.concat(chunks).toString('utf8'))
    expect(backup.version).toBe(1)
    expect(backup.items).toHaveLength(2)
    expect(backup.items.map((item: { type: string }) => item.type).sort()).toEqual(['flight', 'train'])
    await expect(dialog).toBeHidden()
  })
})
test.describe('P1 - DuplicatePhotoCleanup 重复照片清理 @views-coverage', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return
  })

  // REQ-238 后 /toolbox/duplicate 由 ToolWorkflowPage 承载：不再直连
  // /api/toolbox/duplicate 聚类结果，也不再直接 DELETE /api/photos/batch；
  // 删除候选改由持久化预览计划逐项确认后执行。
  test('重复照片入口加载预览计划工作流，首屏不触发删除', async ({ page }) => {
    await page.goto('/toolbox/duplicate')

    await expect(page.locator('h1.ts-page-title', { hasText: '照片清理' })).toBeVisible({ timeout: 10_000 })
    await expect(page.getByRole('list', { name: '操作步骤' })).toBeVisible()
    await expect(page.getByRole('group', { name: '范围来源' })).toBeVisible()
    await expect(page.getByRole('button', { name: '下一步：设置规则' })).toBeDisabled()
    await expect(page.getByRole('button', { name: '选择冗余项' })).toHaveCount(0)
  })
})

test.describe('P1 - AgentInput 输入区交互 @views-coverage', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return
  })

  test('打开 AgentChat -> 输入文字 -> update:modelValue 触发 send', async ({ page }) => {
    await page.goto('/')
    const agentEntry = page.locator('.ai-assistant-button')
    await expect(agentEntry).toBeVisible({ timeout: 10_000 })
    await agentEntry.click()
    await expect(page.locator('.agent-chat-overlay')).toBeVisible({ timeout: 10_000 })

    // 选择器不带标签限定（.agent-input 现为 textarea），避免与实现细节耦合
    const input = page.locator('.agent-chat-overlay .agent-input')
    await expect(input).toBeVisible()
    await input.fill('帮我找一下今天拍的照片')
    await expect(input).toHaveValue('帮我找一下今天拍的照片')

    await input.press('Enter')
    await expect(page.locator('.agent-chat-overlay')).toBeVisible({ timeout: 3_000 })
  })

  test('Shift+Enter 换行而不发送 -> 输入框保留换行内容', async ({ page }) => {
    await page.goto('/')
    const agentEntry = page.locator('.ai-assistant-button')
    await expect(agentEntry).toBeVisible({ timeout: 10_000 })
    await agentEntry.click()
    await expect(page.locator('.agent-chat-overlay')).toBeVisible({ timeout: 10_000 })

    const input = page.locator('.agent-chat-overlay .agent-input')
    await expect(input).toBeVisible()
    await input.fill('第一行')
    await input.press('Shift+Enter')
    await input.pressSequentially('第二行')

    // Shift+Enter 不应触发发送，内容仍留在输入框内且包含换行
    await expect(input).toHaveValue('第一行\n第二行')
  })

  test('生成态 isGenerating=true -> 按钮切到 agent-stop-btn', async ({ page }) => {
    await page.goto('/')
    const agentEntry = page.locator('.ai-assistant-button')
    await expect(agentEntry).toBeVisible({ timeout: 10_000 })
    await agentEntry.click()
    await expect(page.locator('.agent-chat-overlay')).toBeVisible({ timeout: 10_000 })

    const input = page.locator('.agent-chat-overlay .agent-input')
    await input.fill('查询照片')
    await input.press('Enter')

    await expect.poll(
      async () =>
        (await page.locator('.agent-chat-overlay .agent-stop-btn').count()) > 0 ||
        (await page.locator('.agent-chat-overlay .agent-send-btn').count()) === 0,
      { timeout: 3_000 },
    ).toBe(true)
  })
})
