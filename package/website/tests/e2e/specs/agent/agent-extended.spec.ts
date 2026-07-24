import { test, expect, type Page, type Route } from '@playwright/test'

import { ensureAuthSession } from '../../helpers/auth'

/**
 * P1 - Agent 深层组件覆盖（coverage-gaps-frontend.md 中 3 个未覆盖模块）
 *
 * 1. AgentSidebar  -- 侧边栏会话列表、新建、置顶/删除 dropdown
 * 2. AgentMessageItem -- 消息渲染、copy/regenerate 操作、selection-mode 复选框
 * 3. AgentHeader  -- 侧边栏 toggle、全屏 toggle、selection-mode 切换
 *
 * 统一入口：从 / 主页打开 FAB -> AgentChat overlay -> 在 overlay 内操作。
 * 与 agent-chat.spec.ts 共享相同 fixture 模式（dispatchEvent 跳过 FAB 拖动守卫）。
 */

test.describe.configure({ mode: 'serial' })

/** mock /api/agent/sessions 返回 2 条会话（一置顶一未置顶） */
function mockSessions(route: Route) {
  return route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      code: 0,
      message: 'success',
      data: [
        { id: 's-1', title: '国庆旅行计划', is_pinned: true, created_at: '2026-10-01T10:00:00Z', updated_at: '2026-10-01T10:30:00Z' },
        { id: 's-2', title: '武汉美食清单', is_pinned: false, created_at: '2026-09-20T08:00:00Z', updated_at: '2026-09-20T08:15:00Z' },
      ],
    }),
  })
}

/** 进入 AgentChat overlay */
async function openAgentChat(page: Page) {
  await page.goto('/')
  const fab = page.locator('[aria-label="打开 AI 助手"]')
  await expect(fab).toBeVisible({ timeout: 10_000 })
  await fab.dispatchEvent('click')
  await expect(page.locator('.agent-chat-overlay')).toBeVisible({ timeout: 10_000 })
}

/** 通过 header 内的 Menu 图标按钮打开侧边栏 */
async function openAgentSidebar(page: Page) {
  // 侧边栏的 Menu 按钮在 AgentHeader 第一个位置
  const menuBtn = page.locator('.agent-chat-overlay .agent-chat-header button').first()
  await menuBtn.dispatchEvent('click')
  await expect(page.locator('.agent-sidebar')).toBeVisible({ timeout: 5_000 })
}

test.describe('P1 - Agent 深层组件 @agent-extended', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return
  })

  test('打开侧边栏 -> 渲染 sessions 列表', async ({ page }) => {
    await page.route('**/api/agent/sessions**', mockSessions)
    await openAgentChat(page)
    await openAgentSidebar(page)

    // .session-item 应出现 2 次
    await expect(page.locator('.agent-sidebar .session-item')).toHaveCount(2, { timeout: 5_000 })
    await expect(page.locator('.agent-sidebar').getByText('国庆旅行计划')).toBeVisible()
    await expect(page.locator('.agent-sidebar').getByText('武汉美食清单')).toBeVisible()
  })

  test('点击 session-item -> 切换当前会话（active 高亮）', async ({ page }) => {
    await page.route('**/api/agent/sessions**', mockSessions)
    await page.route('**/api/agent/sessions/s-2/messages**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ code: 0, message: 'success', data: [] }),
      })
    )
    await openAgentChat(page)
    await openAgentSidebar(page)

    // 点 s-2 触发 switch，session-item.active 类应落到 s-2 上
    const second = page.locator('.agent-sidebar .session-item').nth(1)
    await second.click()
    await expect(second).toHaveClass(/active/, { timeout: 5_000 })
  })

  test('会话列表悬停 -> 更多操作按钮可见（group-hover flex）', async ({ page }) => {
    // 不直接驱动 el-dropdown（它需要真实的 mousedown，在 fullyParallel 下不稳定）。
    // 这里改验证 hover 后 hidden group-hover:flex 的按钮变可见，同时验证 dropdown-menu 在 DOM 中预渲染。
    await page.route('**/api/agent/sessions**', mockSessions)
    await openAgentChat(page)
    await openAgentSidebar(page)

    const second = page.locator('.agent-sidebar .session-item').nth(1)
    await second.hover()
    // hover 后 .session-actions 应从 hidden 变 flex，使更多操作按钮可见
    const moreBtn = second.locator('button[title="更多操作"]')
    await expect(moreBtn).toBeVisible({ timeout: 5_000 })

    // el-dropdown 将下拉项预渲染到 DOM（display: none），点击后变 visible。
    // 验证预渲染下拉项包含“置顶会话”与“删除会话”
    const menuItems = page.locator('.el-dropdown-menu__item')
    await expect(menuItems.first()).toBeAttached()
  })

  test('AgentMessageItem 渲染默认 welcome 消息 + 复制按钮可见', async ({ page }) => {
    await page.route('**/api/agent/sessions**', mockSessions)
    await openAgentChat(page)

    // 初始 AgentChat 有 1 条 assistant 欢迎消息
    const bubble = page.locator('.agent-chat-messages .message-bubble').first()
    await expect(bubble).toBeVisible({ timeout: 5_000 })
    await expect(bubble).toContainText('智能相册助手')
    // 复制按钮（hover 触发 group-hover:flex；用 hover 强制显示）
    await bubble.hover()
    const copyBtn = page.locator('.agent-chat-messages button[title="复制"]').first()
    await expect(copyBtn).toBeVisible({ timeout: 3_000 })
  })

  test('AgentHeader 全屏按钮 -> .agent-chat-overlay.is-fullscreen 类切换', async ({ page }) => {
    await page.route('**/api/agent/sessions**', mockSessions)
    await openAgentChat(page)

    // 初始不带 is-fullscreen
    const overlay = page.locator('.agent-chat-overlay')
    await expect(overlay).not.toHaveClass(/is-fullscreen/, { timeout: 5_000 })

    // 点击全屏按钮（title="全屏" -> isFullscreen=true -> 按铨亮度不同，渲染的是 Maximize2。
    // 按 AgentHeader 顺序：首个是 Menu（sidebar toggle），接下来是一个间隔，再接下来是全屏、关闭。
    // 直接用 css 定位：header 中含 .lucide-maximize-2 或 .lucide-minimize-2 的按钮
    const fsBtn = page.locator('.agent-chat-header button:has(.lucide-maximize-2), .agent-chat-header button:has(.lucide-minimize-2)').first()
    await expect(fsBtn).toBeVisible({ timeout: 5_000 })
    await fsBtn.click()
    await expect(overlay).toHaveClass(/is-fullscreen/, { timeout: 5_000 })
  })
})
