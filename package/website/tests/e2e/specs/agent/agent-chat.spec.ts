import { test, expect } from '@playwright/test';
import { ensureAuthSession } from '../../helpers/auth';

/**
 * Smoke 测试 — AgentChat 弹窗交互（src/views/agent/AgentChat.vue）
 *
 * AgentChat 是 MainLayout 内置的浮层组件，通过悬浮按钮 (aria-label="打开 AI 助手")
 * 触发；只显示在非 blank 布局页面（即登录 / 年度报告 / 注册页等不渲染 MainLayout，
 * 也没有 FAB）。本文件补齐前几轮夜间测试报告标记为「未覆盖」的 agent 视图。
 *
 * FAB 自带 pointerdown/pointerup 拖动位移检测，Playwright .click() 在 hover 期间
 * 可能产生微小位移，被识别为「拖动」导致 onFabClick 被 dragMoved 守卫拦截。
 * 因此直接用 element.dispatchEvent(\'click\') 走 Vue 的 @click 绑定，避免模拟
 * pointer 序列。也因此关闭按钮走 JS 事件触发即可，不模拟真实鼠标移动。
 *
 * 只验证弹窗可开可关，不验证 SSE 流式消息（依赖 LLM 子进程，dev 环境下默认未启动）。
 */

test.describe('Smoke - AgentChat 弹窗交互 @smoke', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return;
  });

  test('点击 FAB 打开 AgentChat 弹窗 - 出现 agent-chat-overlay', async ({ page }) => {
    await page.goto('/');

    // FAB 必须在 MainLayout 渲染后才出现；首页 layout 是 main，所以 FAB 应可见
    const fab = page.locator('[aria-label="打开 AI 助手"]');
    await expect(fab).toBeVisible({ timeout: 10_000 });

    // 走 JS 事件触发 click，绕过 FAB 自带的 pointerdown 位移检测（避免被识别为拖动）
    await fab.dispatchEvent('click');

    // AgentChat.vue 模板根元素 class="agent-chat-overlay"，modelValue=true 时 v-if 挂载
    await expect(page.locator('.agent-chat-overlay')).toBeVisible({ timeout: 10_000 });
  });

  test('AgentChat 弹窗可通过 Header 关闭按钮关闭 - overlay 消失', async ({ page }) => {
    await page.goto('/');

    const fab = page.locator('[aria-label="打开 AI 助手"]');
    await expect(fab).toBeVisible({ timeout: 10_000 });
    await fab.dispatchEvent('click');
    await expect(page.locator('.agent-chat-overlay')).toBeVisible({ timeout: 10_000 });

    // AgentHeader 末尾的关闭按钮 —— 含 lucide-vue-next 的 <X> 图标
    // 源码未设置 aria-label，用 X 图标的 svg class 锁定。
    const closeBtn = page.locator('.agent-chat-overlay .agent-chat-header button:has(.lucide-x)');
    await expect(closeBtn).toBeVisible();
    await closeBtn.dispatchEvent('click');

    // overlay 通过 v-if 卸载，DOM 中应彻底消失
    await expect(page.locator('.agent-chat-overlay')).toHaveCount(0, { timeout: 5_000 });
    // FAB 再次出现，证明 modelValue 已回退
    await expect(page.locator('[aria-label="打开 AI 助手"]')).toBeVisible();
  });
});
