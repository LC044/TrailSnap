import { test, expect } from '@playwright/test';
import { ensureAuthSession } from '../../helpers/auth';

/**
 * Smoke 测试 — AgentChat 弹窗交互（src/views/agent/AgentChat.vue）
 *
 * AgentChat 是 MainLayout 内置的浮层组件，通过桌面侧边栏的「AI 助手」入口触发。
 * 移动端改由「照片搜索 / AI 助手」双模式页进入，悬浮按钮已移除以避免遮挡内容。
 * 本文件只验证弹窗可开可关，不验证依赖 LLM 子进程的 SSE 流式消息。
 *
 * 只验证弹窗可开可关，不验证 SSE 流式消息（依赖 LLM 子进程，dev 环境下默认未启动）。
 */

test.describe('Smoke - AgentChat 弹窗交互 @smoke', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return;
  });

  test('点击侧边栏 AI 助手打开 AgentChat 弹窗 - 出现 agent-chat-overlay', async ({ page }) => {
    await page.goto('/');

    const agentEntry = page.getByRole('button', { name: 'AI 助手', exact: true });
    await expect(agentEntry).toBeVisible({ timeout: 10_000 });
    await agentEntry.click();

    // AgentChat.vue 模板根元素 class="agent-chat-overlay"，modelValue=true 时 v-if 挂载
    await expect(page.locator('.agent-chat-overlay')).toBeVisible({ timeout: 10_000 });
  });

  test('AgentChat 弹窗可通过 Header 关闭按钮关闭 - overlay 消失', async ({ page }) => {
    await page.goto('/');

    const agentEntry = page.getByRole('button', { name: 'AI 助手', exact: true });
    await expect(agentEntry).toBeVisible({ timeout: 10_000 });
    await agentEntry.click();
    await expect(page.locator('.agent-chat-overlay')).toBeVisible({ timeout: 10_000 });

    // AgentHeader 末尾的关闭按钮 —— 含 lucide-vue-next 的 <X> 图标
    // 源码未设置 aria-label，用 X 图标的 svg class 锁定。
    const closeBtn = page.locator('.agent-chat-overlay .agent-chat-header button:has(.lucide-x)');
    await expect(closeBtn).toBeVisible();
    await closeBtn.dispatchEvent('click');

    // overlay 通过 v-if 卸载，DOM 中应彻底消失
    await expect(page.locator('.agent-chat-overlay')).toHaveCount(0, { timeout: 5_000 });
    // 侧边栏入口仍可用，证明 modelValue 已回退
    await expect(page.getByRole('button', { name: 'AI 助手', exact: true })).toBeVisible();
  });
});
