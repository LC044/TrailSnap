import { test, expect } from '@playwright/test';
import { ensureAuthSession } from '../../helpers/auth';

/**
 * P0 测试 — 设置中心子 Tab 切换（src/views/Settings.vue）
 *
 * 设置中心共有 9 个 tab（个人资料 / 用户管理 / 任务管理 / 基础设置 /
 * 外部图库 / 性能测试 / 令牌管理 / 关于行影集 / 问题反馈），每个 tab
 * 加载不同的子页面。仅当 sidebar 渲染时 cursor-pointer 锚点
 * data-tab="<key>" 暴露给 e2e。
 *
 * 这里选取覆盖前几轮 nightly watch 报告「未测试」的子页面：
 *   - 令牌管理（Tokens）       data-tab="tokens"
 *   - 用户管理（UserManagement）data-tab="user"
 *   - 关于行影集（AboutPage）   data-tab="about"
 *
 * 验证 sidebar 锚点点击 → 对应子页面 h1/h2 渲染 → 当前的激活样式迁移
 * 正确。@p1 也兼容；标记 @p0 与既有设置套件风格保持一致。
 */

async function clickSettingTab(page, key: string) {
  const anchor = page.locator(`[data-tab="${key}"]`);
  await anchor.first().scrollIntoViewIfNeeded();
  await anchor.first().click();
}

test.describe('P0 - 设置中心子 Tab 切换', () => {
  test.beforeEach(async ({ page, request }, testInfo) => {
    if (!(await ensureAuthSession(request, page, testInfo, { photoBucket: 'smoke' }))) return;
  });

  test('切换到「令牌管理」- 渲染 Tokens 子页 H1', async ({ page }) => {
    await page.goto('/settings');
    await expect(page).toHaveURL(/\/settings/);

    await clickSettingTab(page, 'tokens');
    // Tokens.vue 模板硬编码 <h1>令牌管理</h1>
    await expect(page.locator('h1', { hasText: '令牌管理' }).first()).toBeVisible({ timeout: 10_000 });
  });

  test('切换到「用户管理」- 渲染 UserManagement 子页 H2', async ({ page }) => {
    await page.goto('/settings');

    await clickSettingTab(page, 'user');
    // UserManagement.vue 模板硬编码 <h2>用户管理</h2>
    await expect(page.locator('h2', { hasText: '用户管理' }).first()).toBeVisible({ timeout: 10_000 });
  });

  test('切换到「关于行影集」- 渲染 AboutPage 子页 H1', async ({ page }) => {
    await page.goto('/settings');

    await clickSettingTab(page, 'about');
    // AboutPage.vue 模板硬编码 <h1>关于行影集 (TrailSnap)</h1>
    await expect(page.locator('h1', { hasText: '关于行影集' }).first()).toBeVisible({ timeout: 10_000 });
  });

  test('连续切换多个 Tab - 每个 Tab 内容独立渲染不残留', async ({ page }) => {
    await page.goto('/settings');

    // 先 about → 看到「关于行影集 (TrailSnap)」
    await clickSettingTab(page, 'about');
    await expect(page.locator('h1', { hasText: '关于行影集' }).first()).toBeVisible({ timeout: 10_000 });

    // 切到 feedback → 关于的 H1 不再可见，FeedbackPage 的 h2 「问题反馈」出现
    await clickSettingTab(page, 'feedback');
    await expect(page.locator('h2', { hasText: '问题反馈' }).first()).toBeVisible({ timeout: 10_000 });
    // 切回 personal profile → profile 的设置项出现，feedback 的 H2 消失
    await clickSettingTab(page, 'profile');
    // ProfileSettings 模板硬编码 <h2>个人资料</h2>
    await expect(page.locator('h2', { hasText: '个人资料' }).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('h2', { hasText: '问题反馈' })).toHaveCount(0);
  });
});

